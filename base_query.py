from django.http import HttpRequest
from .org import Org
from django.db.models import Q
from rest_framework.parsers import JSONParser

from .utils import camel_to_snake, get_redis_cli
from .log import logger


def get_sorter(body):
    """
    处理排序数据
    """

    ordering = ["-create_time"]
    if body.get("sorter"):
        for field, direction in body.get("sorter").items():
            field = camel_to_snake(field)
            if field == "create_time":
                ordering.remove("-create_time")

            if direction == 1:
                ordering.append(field)
            elif direction == -1:
                ordering.append(f"-{field}")
    return ordering


def is_valid_time_range(key, value):
    if "Time" in key and isinstance(value, list) and len(value) == 2:
        return True
    return False


def get_filter(body, keyword_fields=[]):
    """
    解析请求体中的过滤条件，并生成 Django ORM 的 Q 对象。

    :param body: dict 包含过滤条件的字典
    :param keyword_fields: list 包含需要进行关键字模糊查询的字段名
    :return: Q 对象，用于过滤查询
    """
    filter_conditions = Q()

    if "keywords" in body:
        keywords = body.pop("keywords", None)

        if keywords and keyword_fields:
            keyword_condition = Q()
            for field in keyword_fields:
                field = camel_to_snake(field)
                keyword_condition |= Q(**{f"{field}__icontains": keywords})
            filter_conditions &= keyword_condition

    for k, v in body.items():
        if is_valid_time_range(k, v):
            start_time, end_time = v
            k = camel_to_snake(k)
            filter_conditions &= Q(**{f"{k}__range": (start_time, end_time)})
            continue
        k = camel_to_snake(k)
        filter_conditions &= Q(**{f"{k}__icontains": v})

    return filter_conditions


def delete_user_organizations():
    """
    删除所有机构缓存
    """
    keys = get_redis_cli().scan_iter("auth_org_ids_*")
    for key in keys:
        get_redis_cli().delete(key)


# 查询权限
def get_user_organizations(org_id):
    """
    获取用户所在机构及其所有子机构的ID列表
    """
    organizations = {org_id}
    redis_list = get_redis_cli().smembers(f"auth_org_ids_:{org_id}")
    if redis_list:
        while redis_list:
            ele = redis_list.pop()
            str_ele = str(ele, encoding="utf-8")
            organizations.add(str_ele)
        return organizations

    logger.info(
        f"====================== {org_id} 机构没有缓存 需要查询数据库 ==================="
    )

    # 递归函数来查找所有子机构
    def get_children(org_id):
        children = Org.objects.filter(org_id=org_id)
        for child in children:
            organizations.add(child.id)
            get_children(child.id)

    get_children(org_id)

    get_redis_cli().sadd(f"auth_org_ids_:{org_id}", *organizations)
    return organizations


def getBaseParams(
    request: HttpRequest, keyword_fields=[], allowed_org_ids=None, no_is_delete=False
):
    """
    获取基础参数
    """
    # 获取查询参数
    body = JSONParser().parse(request)
    logger.info(f"获取到的参数: {body}")

    # 处理分页参数
    limit = body.get("limit", 10)
    page = body.get("page", 1)

    # 排序
    sorter = get_sorter(body)

    if body.get("body") != None:
        logger.info(f"body = {body.get('body')}")
        query_data = get_filter(body.get("body"), keyword_fields)
    else:
        query_data = Q()

    if not allowed_org_ids and allowed_org_ids != False:
        if request.user:
            org_id = request.user.get("orgId")
            allowed_org_ids = get_user_organizations(org_id)

    if allowed_org_ids != False:
        query_data &= Q(org_id__in=allowed_org_ids)

    # id 不等于 "-1"
    # query_data &= ~Q(id="-1")
    if no_is_delete is False:
        query_data &= ~Q(is_delete="1")

    logger.info(f"查询条件 = {query_data}")
    return (query_data, sorter, limit, page)
