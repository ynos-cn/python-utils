from django.db import models
from typing import TypeVar, Type
from django.db.models import Q
from .base_query import get_user_organizations

T = TypeVar("T", bound=models.Model)


def delete_model_instances(
    model_class: Type[T],
    instance_ids: list[int],
    db: str = "default",
    soft_delete: bool = True,
    org_id: str = None,
) -> int:
    """
    删除指定模型的多个实例，可以选择物理删除或逻辑删除。

    :param model_class: 要删除的模型类，例如 Org 或 User
    :param instance_ids: 要删除的实例的 ID 列表
    :param db: 指定数据库 ，默认为 default
    :param soft_delete: 是否执行逻辑删除，默认为 True
    :param org_id: 用户所在机构
    """
    length = 0

    query_data = Q()
    if org_id:
        allowed_org_ids = get_user_organizations(org_id)
        query_data &= Q(org_id__in=allowed_org_ids)

    query_data &= Q(id__in=instance_ids)

    if soft_delete:
        # 逻辑删除
        length = model_class.objects.using(db).filter(query_data).update(is_delete=1)
    else:
        # 物理删除
        length = model_class.objects.using(db).filter(query_data).delete()
    return length
