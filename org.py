from django.db import models
from rest_framework import serializers
from .base_models import BaseModel, BaseModelSerializer


# 企业/机构
class Org(BaseModel):
    name = models.CharField(verbose_name="名称", max_length=255)
    code = models.CharField(verbose_name="代码", unique=True, max_length=255)
    controller_name = models.CharField(verbose_name="负责人姓名", max_length=255)
    controller_tel = models.CharField(verbose_name="负责人联系电话", max_length=255)
    org_name = models.CharField(verbose_name="所属机构名称", max_length=255)

    class Meta:
        db_table = "sys_org"  # 数据库表名
        verbose_name = "企业/机构"
        app_label = "*"
        verbose_name_plural = verbose_name
        ordering = ["-create_time"]  # 按照创建时间倒序排列


class OrgSerializer(BaseModelSerializer):
    controllerName = serializers.CharField(source="controller_name", read_only=True)
    controllerTel = serializers.CharField(source="controller_tel", read_only=True)
    orgName = serializers.CharField(source="org_name", read_only=True)

    class Meta:
        model = Org
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["controllerName"] = representation.pop("controller_name")
        representation["controllerTel"] = representation.pop("controller_tel")
        representation["orgName"] = representation.pop("org_name")
        return representation
