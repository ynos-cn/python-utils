import uuid
import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.core.cache import caches
from redis import Redis
from django.urls import path
from .log import logger


def generate_token(user):
    """
    生成token
    """
    payload = {
        "userId": user.get("id"),
        "phone": user.get("phone"),
        "orgId": user.get("orgId"),
        "exp": datetime.now()
        + timedelta(seconds=settings.JWT_AUTH["JWT_EXP_DELTA_SECONDS"]),
    }
    token = jwt.encode(
        payload,
        settings.JWT_AUTH["JWT_SECRET_KEY"],
        algorithm=settings.JWT_AUTH["JWT_ALGORITHM"],
    )
    return token


def decode_token(token):
    """
    解析token
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_AUTH["JWT_SECRET_KEY"],
            algorithms=[settings.JWT_AUTH["JWT_ALGORITHM"]],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token has expired
    except jwt.InvalidTokenError:
        return None  # Invalid token


def new_call_id(replace=""):
    return str(uuid.uuid4()).replace("-", replace)


def get_redis_cli(alias="default", write=True):
    """
    Helper used for obtaining a raw redis client.
    """

    cache = caches[alias]

    if not hasattr(cache, "client"):
        raise NotImplementedError("This backend does not support this feature")

    if not hasattr(cache.client, "get_client"):
        raise NotImplementedError("This backend does not support this feature")

    client: Redis = cache.client.get_client(write)
    return client


# 定义json返回内容
# 格式：{"code": 0, "msg": "", "success": true "data": {}}
def json_response(code=200, msg="", success=True, data=None, total=None, **kwargs):
    r_d = {}
    r_d["code"] = code
    r_d["msg"] = msg
    r_d["success"] = success

    if data is not None:
        r_d["data"] = data
    if total is not None:
        r_d["total"] = total

    for k, v in kwargs.items():
        r_d[k] = v

    logger.debug(f"json响应内容: {r_d}")
    logger.info(f"json响应状态码: {code}, msg: {msg}, success: {success}")
    return r_d


def format_datetime(dt=datetime.now(), fmt="%Y-%m-%d %H:%M:%S"):
    """
    格式化时间
    """
    if isinstance(dt, datetime):
        return dt.strftime(fmt)
    return dt


def generate_urls(view_module):
    """
    生成url
    """
    url_patterns = []
    for attr in dir(view_module):
        view_func = getattr(view_module, attr)
        if callable(view_func) and hasattr(view_func, "url_pattern"):
            url_patterns.append(path(view_func.url_pattern, view_func))
    return url_patterns


def camel_to_snake(s):
    """
    将驼峰命名法的字符串转换为下划线命名法

    snake_str = "updateTime"
    camel_str = camel_to_snake(snake_str)
    print(camel_str)  # 输出：update_time
    """
    # 将驼峰命名法的字符串转换为下划线命名法
    return "".join(["_" + c.lower() if c.isupper() else c for c in s]).lstrip("_")


def snake_to_camel(s):
    """
    将下划线命名法的字符串转换为小驼峰命名法

    snake_str = "update_ime"
    camel_str = snake_to_camel(snake_str)
    print(camel_str)  # 输出：updateTime
    """
    # 将下划线命名法的字符串转换为小驼峰命名法
    words = s.split("_")
    return words[0] + "".join(word.capitalize() for word in words[1:])
