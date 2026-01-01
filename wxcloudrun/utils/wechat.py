"""
微信小程序 API 封装
"""
import os
import logging
import requests

logger = logging.getLogger('log')

# 微信小程序配置
APPID = os.environ.get('WX_APPID', '')
APP_SECRET = os.environ.get('WX_APP_SECRET', '')


def code2session(code: str) -> dict:
    """使用登录凭证code换取session_key和openid

    微信官方接口：https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html

    Args:
        code: 微信登录时获取的code

    Returns:
        dict: 包含openid, session_key等信息
            - openid: 用户唯一标识
            - session_key: 会话密钥
            - unionid: 用户在开放平台的唯一标识符（需要绑定开放平台）
            - errcode: 错误码（成功时不存在）
            - errmsg: 错误信息（成功时不存在）
    """
    if not APPID or not APP_SECRET:
        logger.warning("微信小程序配置缺失，使用模拟模式")
        # 开发环境模拟返回
        return {
            'openid': f'mock_openid_{code[:8]}',
            'session_key': 'mock_session_key'
        }

    url = 'https://api.weixin.qq.com/sns/jscode2session'
    params = {
        'appid': APPID,
        'secret': APP_SECRET,
        'js_code': code,
        'grant_type': 'authorization_code'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        result = response.json()

        if 'errcode' in result and result['errcode'] != 0:
            logger.error(f"微信登录失败: {result}")
            return None

        return result
    except Exception as e:
        logger.error(f"微信登录请求异常: {e}")
        return None


def get_access_token() -> str:
    """获取小程序全局唯一后台接口调用凭据（access_token）

    注意：此接口有调用频率限制，生产环境应该缓存token

    Returns:
        str: access_token，失败返回None
    """
    if not APPID or not APP_SECRET:
        logger.warning("微信小程序配置缺失")
        return None

    url = 'https://api.weixin.qq.com/cgi-bin/token'
    params = {
        'grant_type': 'client_credential',
        'appid': APPID,
        'secret': APP_SECRET
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        result = response.json()

        if 'errcode' in result and result['errcode'] != 0:
            logger.error(f"获取access_token失败: {result}")
            return None

        return result.get('access_token')
    except Exception as e:
        logger.error(f"获取access_token请求异常: {e}")
        return None


def generate_scheme(path: str = None, query: str = None) -> str:
    """生成小程序URL Scheme（用于分享链接）

    Args:
        path: 跳转的小程序页面路径
        query: 页面参数

    Returns:
        str: URL Scheme，失败返回None
    """
    access_token = get_access_token()
    if not access_token:
        return None

    url = f'https://api.weixin.qq.com/wxa/generatescheme?access_token={access_token}'
    data = {
        'jump_wxa': {
            'path': path or '',
            'query': query or ''
        },
        'expire_type': 1,
        'expire_interval': 30  # 30天有效期
    }

    try:
        response = requests.post(url, json=data, timeout=10)
        result = response.json()

        if result.get('errcode', 0) != 0:
            logger.error(f"生成URL Scheme失败: {result}")
            return None

        return result.get('openlink')
    except Exception as e:
        logger.error(f"生成URL Scheme请求异常: {e}")
        return None
