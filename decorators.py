from functools import wraps
from django.http import JsonResponse
from .utils import decode_token, get_redis_cli
from .log import logger


def auth_user():
    """
    验证用户授权
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            token = None
            if request.COOKIES.get("token"):
                token = request.COOKIES.get("token")
            if request.headers.get("token"):
                token = request.headers.get("token")
            if token is None:
                return JsonResponse({"code": 401, "msg": "未登录"}, status=401)
            else:
                # 从数据库中获取用户信息
                payload = decode_token(token)
                if payload is None:
                    return JsonResponse({"code": 401, "msg": "未登录"}, status=401)
                else:
                    id = payload.get("userId")
                    org_id = payload.get("orgId")
                    keys = [
                        "id",
                        "createById",
                        "updateById",
                        "username",
                        "joinTime",
                        "orgName",
                        "orgId",
                        "phone",
                        "name",
                        "email",
                        "position",
                        "sex",
                        "status",
                        "createTime",
                        "updateTime",
                        "lastLoginTime",
                    ]
                    data = get_redis_cli().hmget(f"user:{org_id}_{id}", keys)
                    if data[0] is None:
                        return JsonResponse({"code": 401, "msg": "未登录"}, status=401)
                    user = {}
                    for i in range(len(keys)):
                        user[keys[i]] = data[i].decode() if data[i] else None
                    request.user = user
                    request.token = token
                    pass

            request.cookie_value = token
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def method_decorator(http_method, url_pattern):
    """
    装饰器，用于装饰视图函数，使其只能处理指定的 http 方法
    """

    def decorator(view_func):
        if not hasattr(view_func, "http_methods"):
            view_func.http_methods = []

        view_func.http_methods.append(http_method)

        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.method not in view_func.http_methods:
                return JsonResponse({"code": 405, "msg": "请求出错"}, status=405)
                # return HttpResponseNotAllowed(view_func.http_methods)
            return view_func(request, *args, **kwargs)

        _wrapped_view.url_pattern = url_pattern
        _wrapped_view.http_methods = view_func.http_methods
        return _wrapped_view

    return decorator


GET = lambda url_pattern: method_decorator("GET", url_pattern)
POST = lambda url_pattern: method_decorator("POST", url_pattern)
DELETE = lambda url_pattern: method_decorator("DELETE", url_pattern)
