from collections import deque
import random
from typing import List, Set
from django.db import DatabaseError, connection
from django.http import HttpRequest
from redis import RedisError
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


def get_sorter_sql(body, valid_columns_with_alias={}):
    """
    多表查询的动态 ORDER BY 生成器
    :param body: 请求参数，包含排序字段
    :param valid_columns_with_alias: 允许排序的字段及表别名映射，格式为 {"字段名": "表别名"}
                                    例如 {"create_time": "p", "role_name": "rr"}
    :return: 安全的 SQL ORDER BY 子句
    """
    # 默认排序规则（明确指定表别名）
    ordering = ["-p.create_time"]
    sorter = body.get("sorter", {})

    for camel_field, direction in sorter.items():
        # 驼峰转下划线
        snake_field = camel_to_snake(camel_field)

        # 校验字段合法性
        if snake_field not in valid_columns_with_alias:
            continue  # 忽略非法字段

        # 获取字段对应的表别名
        table_alias = valid_columns_with_alias[snake_field]
        qualified_field = f"{table_alias}.{snake_field}"

        # 如果操作字段是 create_time，移除默认排序
        if snake_field == "create_time" and "-p.create_time" in ordering:
            ordering.remove("-p.create_time")

        # 添加带表别名的排序标记
        if direction == 1:
            ordering.append(qualified_field)
        elif direction == -1:
            ordering.append(f"-{qualified_field}")

    # 转换为 SQL 语法
    order_clauses = []
    for field in ordering:
        if field.startswith("-"):
            column = field[1:]
            order_clauses.append(f"{column} DESC")
        else:
            order_clauses.append(f"{field} ASC")

    return f"ORDER BY {', '.join(order_clauses)}" if order_clauses else ""


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


def get_user_organizations(org_id: int) -> Set[int]:
    """
    获取用户所在机构及其所有子机构的ID集合（SQL优化版）
    优化点：
    1. 使用SQL递归查询替代Python递归
    2. 改进缓存机制
    3. 防御性编程
    4. 性能优化
    """
    redis_key = f"auth_org_ids:{org_id}"

    # ========================== 1. 尝试从缓存获取 ==========================
    if cached := get_redis_cli().smembers(redis_key):
        logger.info(f"[缓存命中] 机构{org_id}子机构列表")
        return {int(org_id_str) for org_id_str in cached}

    logger.info(f"[缓存未命中] 开始查询机构{org_id}层级数据")

    # ========================== 2. 数据库递归查询 ==========================
    org_set = set()
    try:
        with connection.cursor() as cursor:
            # MySQL 8.0+ 递归查询语法
            recursive_sql = f"""
            WITH RECURSIVE org_tree AS (
                SELECT id, org_id
                FROM {Org._meta.db_table}
                WHERE id = %s
                UNION ALL
                SELECT o.id, o.org_id
                FROM {Org._meta.db_table} o
                INNER JOIN org_tree ot ON o.org_id = ot.id
            )
            SELECT id FROM org_tree
            """
            cursor.execute(recursive_sql, [org_id])
            org_set = {row[0] for row in cursor.fetchall()}

    except DatabaseError as e:
        # 数据库不支持递归查询时降级处理
        if "syntax" in str(e).lower():
            return _fallback_org_query(org_id)
        logger.error(f"数据库查询失败: {str(e)}")
        raise

    # ========================== 3. 缓存处理 ==========================
    if org_set:
        # 转换为字符串列表存储
        org_str_list = [str(org_id) for org_id in org_set]
        try:
            # 设置缓存过期时间(1小时)和随机抖动防止雪崩
            ex_time = 3600 + random.randint(0, 300)
            get_redis_cli().sadd(redis_key, *org_str_list)
            get_redis_cli().expire(redis_key, ex_time)
        except RedisError as e:
            logger.warning(f"Redis操作失败: {str(e)}")

    return org_set


def _fallback_org_query(root_id: int) -> Set[int]:
    """递归查询降级方案"""
    org_set = set()
    queue = deque([root_id])
    max_depth = 20  # 防止恶意数据导致无限循环

    with connection.cursor() as cursor:
        for _ in range(max_depth):
            if not queue:
                break

            current_id = queue.popleft()
            if current_id in org_set:
                continue

            org_set.add(current_id)

            # 查询直接子机构
            cursor.execute(
                f"SELECT id FROM {Org._meta.db_table} WHERE org_id = %s", [current_id]
            )
            children = [row[0] for row in cursor.fetchall()]
            queue.extend(children)

    return org_set


def get_all_parent_orgs(org_id) -> List[int]:
    """
    获取机构及所有父机构ID（优化版）
    优化点：
    1. 使用递归SQL查询替代循环查询
    2. 添加缓存机制
    3. 防御性编程增强
    4. 数据库兼容性处理
    """
    # ==================== 缓存检查 ====================
    redis_key = f"org_parent:{org_id}"
    if cached := get_redis_cli().lrange(redis_key, 0, -1):
        logger.info(f"[缓存命中] 机构{org_id}父机构链")
        return [id_str for id_str in cached]

    # ==================== 数据库查询 ====================
    org_ids = []
    try:
        with connection.cursor() as cursor:
            # MySQL 8.0+/PostgreSQL 递归查询
            recursive_sql = f"""
            WITH RECURSIVE org_chain AS (
                SELECT id, org_id
                FROM {Org._meta.db_table}
                WHERE id = %s AND is_delete IS NULL
                UNION ALL
                SELECT so.id, so.org_id
                FROM {Org._meta.db_table} so
                INNER JOIN org_chain oc ON so.id = oc.org_id
                WHERE so.is_delete IS NULL
            )
            SELECT id FROM org_chain
            """
            cursor.execute(recursive_sql, [org_id])
            org_ids = [row[0] for row in cursor.fetchall()]

    except DatabaseError as e:
        if "syntax" in str(e).lower():
            return _fallback_parent_query(org_id)
        logger.error(f"递归查询失败: {str(e)}")
        raise

    # ==================== 缓存处理 ====================
    if org_ids:
        try:
            # 设置缓存带随机过期时间（30分钟±5分钟）
            ex_time = 1800 + random.randint(-300, 300)
            get_redis_cli().rpush(redis_key, *map(str, org_ids))
            get_redis_cli().expire(redis_key, ex_time)
        except Exception as e:
            logger.warning(f"缓存写入失败: {str(e)}")

    return org_ids


def _fallback_parent_query(org_id: int) -> List[int]:
    """降级方案：迭代查询"""
    org_chain = []
    current_id = org_id
    max_depth = 20  # 防止死循环

    with connection.cursor() as cursor:
        for _ in range(max_depth):
            cursor.execute(
                f"SELECT org_id FROM {Org._meta.db_table} WHERE id = %s AND is_delete IS NULL",
                [current_id],
            )
            row = cursor.fetchone()

            if not row or row[0] is None:
                org_chain.append(current_id)
                break

            if current_id in org_chain:  # 循环检测
                logger.warning(f"检测到机构循环引用: {org_chain}")
                break

            org_chain.append(current_id)
            current_id = row[0]

    return org_chain[::-1]  # 反转保证根节点在前


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
