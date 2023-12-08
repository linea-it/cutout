from rest_framework import serializers

from cutout.service.models import Job


class JobRequestSerializer(serializers.ModelSerializer[Job]):
    class Meta:
        model = Job
        fields = "__all__"
        read_only_fields = ("owner",)
