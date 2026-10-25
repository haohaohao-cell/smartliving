"""
用户认证路由模块
=====================================
提供用户登录、注册和用户管理的API接口

URL前缀: /api/auth

安全特性：
- 密码使用werkzeug.security进行哈希存储
- 返回用户信息时不包含密码字段
- 使用标准HTTP状态码进行错误处理
- 使用JWT令牌管理登录状态（支持互斥登录）

性能优化：
- 高频只读接口内存缓存
- print替换为logging
"""

from flask import Blueprint, request, jsonify, g
import datetime
import time
import logging
from models import db, User
from werkzeug.security import generate_password_hash, check_password_hash
from utils import login_required, generate_token

logger = logging.getLogger(__name__)

# 创建认证模块的Blueprint
auth_bp = Blueprint('auth', __name__)

# 用户信息内存缓存：{user_id: {'data': dict, 'expires': float}}
_user_info_cache = {}
_USER_CACHE_TTL = 300  # 缓存有效期（秒）

# 用户角色常量
ROLE_ADMIN = 'admin'
ROLE_USER = 'user'
VALID_ROLES = (ROLE_ADMIN, ROLE_USER)


def invalidate_user_cache(user_id):
    """清除指定用户的缓存"""
    _user_info_cache.pop(user_id, None)


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    用户登录接口
    
    请求方法: POST
    请求URL: /api/auth/login
    
    请求参数（JSON格式）:
    {
        "username": "string, 必填, 用户名",
        "password": "string, 必填, 密码"
    }
    
    成功响应（200 OK）:
    {
        "success": true,
        "message": "登录成功",
        "user": {
            "id": 1,
            "username": "admin",
            "name": "管理员",
            "created_at": "2026-07-06 14:58:16"
        },
        "note": "已登录，可访问人脸识别和设备控制功能"
    }
    
    失败响应:
    - 400: 缺少必要参数
    - 404: 账号不存在
    - 401: 密码错误
    """
    data = request.get_json()
    
    # 参数校验：检查是否包含必要字段
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400
    
    username = data['username']
    password = data['password']
    
    # 查询数据库中是否存在该用户
    user = db.session.query(User).filter_by(username=username).first()
    
    # 用户不存在，返回404
    if not user:
        return jsonify({'success': False, 'message': '账号不存在'}), 404
    
    # 密码验证：使用check_password_hash验证哈希密码
    if check_password_hash(user.password, password):
        # 生成JWT token
        token = generate_token(user.id, user.username)
        
        # 更新数据库中的session_token（互斥登录：新登录覆盖旧token）
        user.session_token = token
        user.last_login_time = datetime.datetime.utcnow()
        db.session.commit()
        
        # 清除该用户的缓存，确保下次查询获取最新数据
        invalidate_user_cache(user.id)
        
        # 登录成功，返回用户信息和token（不包含密码）
        return jsonify({
            'success': True,
            'message': '登录成功',
            'user': user.to_dict(),
            'token': token,
            'note': '已登录，可访问人脸识别和设备控制功能'
        }), 200
    else:
        # 密码错误，返回401
        return jsonify({'success': False, 'message': '密码错误'}), 401


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    用户登出接口（JWT版本，支持互斥登录）
    
    请求方法: POST
    请求URL: /api/auth/logout
    
    成功响应（200 OK）:
    {
        "success": true,
        "message": "登出成功"
    }
    
    说明：清除数据库中的session_token，使该token失效
    """
    # 清除数据库中的session_token
    user = db.session.get(User, g.user_id)
    if user:
        user.session_token = None
        db.session.commit()
        invalidate_user_cache(user.id)
    
    return jsonify({
        'success': True,
        'message': '登出成功，请前端清除token'
    }), 200


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    用户注册接口
    
    请求方法: POST
    请求URL: /api/auth/register
    
    请求参数（JSON格式）:
    {
        "username": "string, 必填, 用户名",
        "password": "string, 必填, 密码",
        "password2": "string, 必填, 确认密码",
        "name": "string, 必填, 用户姓名"
    }
    
    成功响应（201 Created）:
    {
        "success": true,
        "message": "注册成功",
        "user": {
            "id": 1,
            "username": "admin",
            "name": "管理员",
            "created_at": "2026-07-06 14:58:16"
        },
        "note": "注册成功，请登录后使用系统功能"
    }
    
    失败响应:
    - 400: 缺少必要参数 / 两次密码不一致 / 密码长度不足6位
    - 409: 账号已存在
    - 500: 注册失败（数据库错误）
    """
    data = request.get_json()
    
    # 参数校验：检查是否包含所有必要字段
    if not data or 'username' not in data or 'password' not in data or 'password2' not in data or 'name' not in data:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400
    
    username = data['username']
    password = data['password']
    password2 = data['password2']
    name = data['name']
    
    # 验证两次输入的密码是否一致
    if password != password2:
        return jsonify({'success': False, 'message': '两次输入的密码不一致'}), 400
    
    # 验证密码长度至少6位
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少6位'}), 400
    
    # 检查用户名是否已存在
    existing_user = db.session.query(User).filter_by(username=username).first()
    if existing_user:
        return jsonify({'success': False, 'message': '账号已存在'}), 409
    
    # 使用generate_password_hash对密码进行哈希处理
    hashed_password = generate_password_hash(password)
    
    # 判断是否是第一个用户，如果是则自动设为管理员
    user_count = db.session.query(User).count()
    role = ROLE_ADMIN if user_count == 0 else ROLE_USER
    
    # 创建新用户对象
    new_user = User(username=username, password=hashed_password, name=name, role=role)
    
    try:
        # 将新用户添加到数据库会话
        db.session.add(new_user)
        # 提交数据库事务
        db.session.commit()
        # 返回成功响应，包含用户信息
        return jsonify({
            'success': True,
            'message': '注册成功',
            'user': new_user.to_dict(),
            'note': '注册成功，请登录后使用系统功能'
        }), 201
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"用户注册失败: {e}")
        return jsonify({'success': False, 'message': f'注册失败: {e}'}), 500


@auth_bp.route('/users', methods=['GET'])
@login_required
def get_users():
    """
    获取所有用户列表接口
    
    请求方法: GET
    请求URL: /api/auth/users
    
    权限要求:
    - 必须登录
    - 只有管理员可以调用
    
    成功响应（200 OK）:
    {
        "success": true,
        "users": [
            {
                "id": 1,
                "username": "admin",
                "name": "管理员",
                "created_at": "2026-07-06 14:58:16"
            }
        ]
    }
    
    失败响应:
    - 401: 未登录，请先登录
    - 403: 无权访问，只有管理员可以查看用户列表
    """
    # 权限检查：只有管理员可以查看用户列表
    if g.role != ROLE_ADMIN:
        return jsonify({
            'success': False,
            'message': '无权访问，只有管理员可以查看用户列表'
        }), 403
    
    # 查询所有用户
    users = db.session.query(User).all()
    # 返回用户列表（不包含密码）
    return jsonify({'success': True, 'users': [user.to_dict() for user in users]}), 200


@auth_bp.route('/users/<int:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    """
    获取单个用户信息接口（带内存缓存）
    
    请求方法: GET
    请求URL: /api/auth/users/<user_id>
    
    路径参数:
    - user_id: int, 用户ID
    
    权限要求:
    - 必须登录
    - 只有管理员可以调用
    
    成功响应（200 OK）:
    {
        "success": true,
        "user": {
            "id": 1,
            "username": "admin",
            "name": "管理员",
            "created_at": "2026-07-06 14:58:16"
        }
    }
    
    失败响应:
    - 401: 未登录，请先登录
    - 403: 无权访问，只有管理员可以查看用户信息
    - 404: 用户不存在
    """
    # 权限检查：只有管理员可以查看用户信息
    if g.role != ROLE_ADMIN:
        return jsonify({
            'success': False,
            'message': '无权访问，只有管理员可以查看用户信息'
        }), 403
    
    # 检查内存缓存
    cached = _user_info_cache.get(user_id)
    if cached and cached['expires'] > time.time():
        return jsonify({'success': True, 'user': cached['data']}), 200
    
    # 缓存未命中，查询数据库
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    
    user_data = user.to_dict()
    # 写入缓存
    _user_info_cache[user_id] = {
        'data': user_data,
        'expires': time.time() + _USER_CACHE_TTL
    }
    return jsonify({'success': True, 'user': user_data}), 200


@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    """
    更新用户信息接口
    
    请求方法: PUT
    请求URL: /api/auth/users/<user_id>
    
    路径参数:
    - user_id: int, 用户ID
    
    权限要求:
    - 必须登录
    - 只能更新自己或管理员可以更新任何用户
    
    请求参数（JSON格式，可选）:
    {
        "name": "string, 可选, 用户姓名",
        "password": "string, 可选, 新密码",
        "password2": "string, 可选, 确认新密码"
    }
    
    成功响应（200 OK）:
    {
        "success": true,
        "message": "更新成功",
        "user": {
            "id": 1,
            "username": "admin",
            "name": "新姓名",
            "created_at": "2026-07-06 14:58:16"
        }
    }
    
    失败响应:
    - 401: 未登录，请先登录
    - 403: 无权更新该用户（非本人且非管理员）
    - 400: 两次密码不一致
    - 404: 用户不存在
    - 500: 更新失败（数据库错误）
    """
    # 获取当前登录用户信息（从JWT解析）
    current_user_id = g.user_id
    
    data = request.get_json()
    # 根据用户ID查询用户
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    
    # 权限检查：只有本人或管理员可以更新用户信息
    is_admin = g.role == ROLE_ADMIN
    is_self = current_user_id == user_id
    
    if not is_admin and not is_self:
        return jsonify({
            'success': False,
            'message': '无权更新该用户，只有本人或管理员可以更新用户信息'
        }), 403
    
    # 更新用户姓名（如果提供）
    if 'name' in data:
        user.name = data['name']
    
    # 更新角色（仅管理员可操作）
    if 'role' in data and is_admin:
        role = data['role']
        if role not in VALID_ROLES:
            return jsonify({'success': False, 'message': '角色只能是 admin 或 user'}), 400
        user.role = role
    
    # 更新密码（如果提供）
    if 'password' in data and 'password2' in data:
        if data['password'] != data['password2']:
            return jsonify({'success': False, 'message': '两次输入的密码不一致'}), 400
        if len(data['password']) < 6:
            return jsonify({'success': False, 'message': '密码长度至少6位'}), 400
        user.password = generate_password_hash(data['password'])
    
    try:
        # 提交数据库事务
        db.session.commit()
        # 清除该用户的缓存
        invalidate_user_cache(user_id)
        return jsonify({'success': True, 'message': '更新成功', 'user': user.to_dict()}), 200
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"更新用户信息失败: {e}")
        return jsonify({'success': False, 'message': f'更新失败: {e}'}), 500


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    """
    删除用户接口
    
    请求方法: DELETE
    请求URL: /api/auth/users/<user_id>
    
    路径参数:
    - user_id: int, 用户ID
    
    权限要求:
    - 必须登录
    - 只能删除自己或管理员可以删除任何用户
    
    成功响应（200 OK）:
    {
        "success": true,
        "message": "删除成功"
    }
    
    失败响应:
    - 401: 未登录，请先登录
    - 403: 无权删除该用户（非本人且非管理员）
    - 404: 用户不存在
    - 500: 删除失败（数据库错误）
    """
    # 获取当前登录用户信息（从JWT解析）
    current_user_id = g.user_id
    
    # 根据用户ID查询要删除的用户
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    
    # 权限检查：只有本人或管理员可以删除用户
    is_admin = g.role == ROLE_ADMIN
    is_self = current_user_id == user_id
    
    if not is_admin and not is_self:
        return jsonify({
            'success': False,
            'message': '无权删除该用户，只有本人或管理员可以删除用户'
        }), 403
    
    try:
        # 删除用户
        db.session.delete(user)
        # 提交数据库事务
        db.session.commit()
        # 清除该用户的缓存
        invalidate_user_cache(user_id)
        return jsonify({'success': True, 'message': '删除成功'}), 200
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"删除用户失败: {e}")
        return jsonify({'success': False, 'message': f'删除失败: {e}'}), 500
