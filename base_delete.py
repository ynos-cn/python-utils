from django.db import models
from typing import TypeVar, Type

T = TypeVar("T", bound=models.Model)


def delete_model_instances(
    model_class: Type[T],
    instance_ids: list[int],
    db: str = "default",
    soft_delete: bool = True,
) -> None:
    """
    删除指定模型的多个实例，可以选择物理删除或逻辑删除。

    :param model_class: 要删除的模型类，例如 Org 或 User
    :param instance_ids: 要删除的实例的 ID 列表
    :param db: 指定数据库 ，默认为 default
    :param soft_delete: 是否执行逻辑删除，默认为 True
    """
    if soft_delete:
        # 逻辑删除
        model_class.objects.using(db).filter(id__in=instance_ids).update(is_delete=1)
    else:
        # 物理删除
        model_class.objects.using(db).filter(id__in=instance_ids).delete()
