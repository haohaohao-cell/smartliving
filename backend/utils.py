"""
工具函数模块
=====================================
提供通用的工具函数和装饰器

包含：
- login_required装饰器：用于保护需要登录才能访问的接口
- JWT相关函数：生成和验证token

性能优化：
- JWT解码结果内存缓存，减少重复解码开销
- login_required装饰器减少重复的header访问
"""

from flask import jsonify, g, request
import jwt
import datetime
import os
import random
import string
import time
import logging

logger = logging.getLogger(__name__)

JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'smart_home_jwt_secret_key_2026')

# JWT解码结果缓存：{token: {'payload': dict, 'expires': float}}
_jwt_cache = {}
_JWT_CACHE_TTL = 3600  # 缓存有效期（秒）


def generate_token(user_id, username):
    """生成JWT token（带有随机nonce确保每次不同）"""
    payload = {
        'user_id': user_id,
        'username': username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        'nonce': ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')


def decode_token(token):
    """解码JWT token（带缓存）
    
    性能优化：先检查缓存，命中则直接返回，未命中才执行解码
    """
    # 检查缓存
    cached = _jwt_cache.get(token)
    if cached and cached['expires'] > time.time():
        return cached['payload']

    # 缓存未命中，执行解码
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        # 解码成功，写入缓存
        _jwt_cache[token] = {
            'payload': payload,
            'expires': time.time() + _JWT_CACHE_TTL
        }
        return payload
    except jwt.ExpiredSignatureError:
        # 过期token从缓存中删除
        _jwt_cache.pop(token, None)
        return None
    except jwt.InvalidTokenError:
        # 无效token从缓存中删除
        _jwt_cache.pop(token, None)
        return None


def login_required(f):
    """
    登录验证装饰器（JWT版本，支持互斥登录）
    用于保护需要登录才能访问的接口
    
    使用方法：
    @app.route('/protected')
    @login_required
    def protected():
        pass
    
    如果用户未登录或token已失效（在其他设备登录），返回401未授权错误
    
    性能优化：仅读取一次Authorization请求头，直接使用g.token_valid判断
    """
    def decorated_function(*args, **kwargs):
        # 直接检查g.token_valid（由before_request设置）
        if not g.token_valid:
            # 仅读取一次请求头，判断是token失效还是未提供
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                return jsonify({
                    'success': False,
                    'message': '您的账号已在其他设备登录，请重新登录',
                    'redirect': '/api/auth/login',
                    'code': 'logged_in_elsewhere'
                }), 401
            return jsonify({
                'success': False,
                'message': '未登录，请先登录',
                'redirect': '/api/auth/login'
            }), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


def get_current_user():
    """获取当前登录用户的信息（JWT版本）"""
    return g.user_id
