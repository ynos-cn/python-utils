from datetime import datetime, timezone
from django.db import models
from rest_framework import serializers


def format_datetime(dt, fmt="%Y-%m-%d %H:%M:%S"):
    """
    格式化时间
    """
    if isinstance(dt, datetime):
        return dt.strftime(fmt)
    return dt


# 基础字段
class BaseModel(models.Model):
    id = models.AutoField(primary_key=True, editable=False)

    create_time = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    update_time = models.DateTimeField(verbose_name="更新时间", auto_now_add=True)
    creator = models.CharField(verbose_name="创建人", max_length=128)
    updater = models.CharField(verbose_name="更新人", max_length=128)
    org_id = models.IntegerField(verbose_name="所属机构")
    is_delete = models.IntegerField(
        verbose_name="是否删除 1.删除 0.未删除",
        blank=True,
        null=True,
    )

    class Meta:
        # 抽象类， 用于继承，迁移的时候不创建
        abstract = True


class BaseModelSerializer(serializers.ModelSerializer):
    create_time = serializers.SerializerMethodField(default=timezone.utc)
    update_time = serializers.SerializerMethodField(default=timezone.utc)
    orgId = serializers.IntegerField(source="org_id", read_only=True)
    isDelete = serializers.IntegerField(source="is_delete", read_only=True)

    class Meta:
        # 抽象类， 用于继承，迁移的时候不创建
        abstract = True

    def get_create_time(self, obj):
        return format_datetime(obj.create_time)

    def get_update_time(self, obj):
        return format_datetime(obj.update_time)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["createTime"] = representation.pop("create_time")
        representation["updateTime"] = representation.pop("update_time")
        representation["orgId"] = representation.pop("org_id")
        representation["isDelete"] = representation.pop("is_delete")
        return representation
