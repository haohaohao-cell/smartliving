"""
智能家居系统后端主应用入口
=====================================
负责初始化Flask应用、配置数据库、注册路由蓝图

技术栈：
- Flask 3.x - Web框架
- SQLAlchemy - ORM数据库操作
- SQLite/MySQL - 数据库存储
- Flask-CORS - 跨域支持
- JWT - 跨域认证

安全特性：
- JWT Token认证
- 登录验证装饰器
- 人脸识别和设备控制接口需要登录后才能访问

性能优化：
- Token内存缓存，减少数据库查询
- SQLite WAL模式，提升并发写入
- 预加载YOLO模型，消除首次请求阻塞
"""

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from models import db, User
from routes.auth import auth_bp
from routes.yolo import yolo_bp
from routes.device import device_bp
from utils import decode_token
import os
import time
import threading
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Token内存缓存：{token: {'user_id': int, 'username': str, 'role': str, 'expires': float}}
token_user_cache = {}
cache_lock = threading.Lock()
TOKEN_CACHE_TTL = 3600  # 缓存有效期（秒）
CACHE_CLEANUP_INTERVAL = 100  # 每100次请求清理一次过期缓存
_request_counter = 0

# 创建Flask应用实例
app = Flask(__name__)

# CORS配置：允许前端跨域访问，缓存预检结果
CORS(app,
     origins='*',
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization'],
     supports_credentials=False,
     max_age=86400)

# 配置数据库连接 - 使用绝对路径确保数据持久化到 instance 目录
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
os.makedirs(instance_dir, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(instance_dir, "smart_home.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# SQLite连接优化：增加超时、允许跨线程、连接回收
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'timeout': 15,
        'check_same_thread': False
    },
    'pool_recycle': 1800
}
# 限制上传文件大小（16MB）
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 初始化SQLAlchemy数据库实例
db.init_app(app)

# 注册路由蓝图
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(yolo_bp, url_prefix='/api/yolo')
app.register_blueprint(device_bp, url_prefix='/api/device')


@app.before_request
def before_request():
    """请求前处理：解析JWT token并验证session_token（互斥登录）
    
    性能优化：优先从内存缓存读取用户信息，缓存未命中才查数据库
    """
    global _request_counter
    
    g.user_id = None
    g.username = None
    g.role = None
    g.token_valid = False

    _request_counter += 1
    if _request_counter % CACHE_CLEANUP_INTERVAL == 0:
        with cache_lock:
            now = time.time()
            expired_tokens = [token for token, data in token_user_cache.items() 
                            if data['expires'] <= now]
            for token in expired_tokens:
                del token_user_cache[token]

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return

    token = auth_header[7:]

    # 优先从缓存读取
    with cache_lock:
        cached = token_user_cache.get(token)
        if cached and cached['expires'] > time.time():
            g.user_id = cached['user_id']
            g.username = cached['username']
            g.role = cached['role']
            g.token_valid = True
            return

    # 缓存未命中，解码JWT并查询数据库
    payload = decode_token(token)
    if not payload:
        return

    user_id = payload.get('user_id')
    username = payload.get('username')

    user = db.session.get(User, user_id)
    if user and user.session_token == token:
        g.user_id = user_id
        g.username = username
        g.role = user.role
        g.token_valid = True
        # 写入缓存
        with cache_lock:
            token_user_cache[token] = {
                'user_id': user_id,
                'username': username,
                'role': user.role,
                'expires': time.time() + TOKEN_CACHE_TTL
            }


@app.route('/')
def index():
    """首页接口"""
    if g.user_id:
        return jsonify({
            'success': True,
            'message': f'欢迎回来，用户ID: {g.user_id}',
            'status': 'logged_in',
            'user_id': g.user_id,
            'username': g.username,
            'role': g.role,
            'endpoints': {
                'auth': {'logout': 'POST /api/auth/logout'},
                'yolo': {
                    'detect': 'POST /api/yolo/detect',
                    'verify_access': 'POST /api/yolo/access/verify',
                    'access_records': 'GET /api/yolo/access/records'
                },
                'device': {
                    'devices': 'GET/POST /api/device/devices',
                    'device': 'GET/PUT/DELETE /api/device/devices/<id>',
                    'control': 'POST /api/device/devices/<id>/control',
                    'toggle': 'POST /api/device/devices/<id>/toggle'
                }
            }
        })
    else:
        return jsonify({
            'success': True,
            'message': '智能家居系统 - 请先登录',
            'status': 'not_logged_in',
            'endpoints': {
                'auth': {
                    'login': 'POST /api/auth/login',
                    'register': 'POST /api/auth/register'
                }
            },
            'note': '人脸识别和设备控制功能需要登录后才能访问'
        })


def init_sqlite_wal():
    """初始化SQLite WAL模式，提升并发写入性能"""
    try:
        with app.app_context():
            db.session.execute(db.text('PRAGMA journal_mode=WAL'))
            db.session.commit()
            logger.info("SQLite WAL模式已启用")
    except Exception as e:
        logger.warning(f"启用WAL模式失败: {e}")


if __name__ == '__main__':
    # 初始化数据库表结构（仅在首次运行时创建）
    with app.app_context():
        db.create_all()
        init_sqlite_wal()

    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    # 预加载模型，消除首次请求阻塞并避免懒加载竞态条件
    try:
        from yolo_model import load_model
        load_model()
        logger.info("YOLO模型预加载成功")
    except Exception as e:
        logger.warning(f"预加载YOLO模型失败: {e}")
    
    try:
        from face_recognition import load_features_from_db
        with app.app_context():
            load_features_from_db()
        logger.info("人脸特征预加载成功")
    except Exception as e:
        logger.warning(f"预加载人脸特征失败: {e}")

    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
