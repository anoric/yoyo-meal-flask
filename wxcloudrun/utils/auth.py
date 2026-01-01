"""
JWT Token 认证工具
"""
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, g

from wxcloudrun import dao
from wxcloudrun.response import make_err_response

# JWT 配置
JWT_SECRET = os.environ.get('JWT_SECRET', 'yoyo-meal-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRES_DAYS = 7


def generate_token(user_id: int) -> str:
    """生成JWT Token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=JWT_EXPIRES_DAYS),
        'iat': datetime.utcnow(),
        'jti': secrets.token_hex(16)  # 唯一标识符
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_token(token: str) -> dict:
    """解码JWT Token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_token_from_header() -> str:
    """从请求头获取Token"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header()

        if not token:
            return make_err_response('需要登录', code=-1, error_code='AUTH_REQUIRED')

        payload = decode_token(token)
        if not payload:
            return make_err_response('Token已过期或无效', code=-1, error_code='TOKEN_EXPIRED')

        user_id = payload.get('user_id')
        user = dao.get_user_by_id(user_id)

        if not user:
            return make_err_response('用户不存在', code=-1, error_code='USER_NOT_FOUND')

        # 将用户信息存储到 g 对象中
        g.current_user = user
        g.user_id = user_id

        return f(*args, **kwargs)

    return decorated_function


def get_current_user():
    """获取当前登录用户"""
    return getattr(g, 'current_user', None)


def get_current_user_id() -> int:
    """获取当前登录用户ID"""
    return getattr(g, 'user_id', None)


def generate_invite_code() -> str:
    """生成邀请码"""
    return secrets.token_urlsafe(16)[:16]


def check_baby_permission(baby_id: int, user_id: int = None, require_owner: bool = False) -> bool:
    """检查用户是否有权限管理宝宝

    Args:
        baby_id: 宝宝ID
        user_id: 用户ID，如果不传则使用当前登录用户
        require_owner: 是否要求必须是创建者

    Returns:
        bool: 是否有权限
    """
    if user_id is None:
        user_id = get_current_user_id()

    if not user_id:
        return False

    manager = dao.get_baby_manager(baby_id, user_id)
    if not manager:
        return False

    if require_owner and manager.role != 'owner':
        return False

    return True
