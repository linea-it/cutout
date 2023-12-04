from rest_framework import serializers

from cutout.service.models import JobRequest


class JobRequestSerializer(serializers.ModelSerializer[JobRequest]):
    class Meta:
        model = JobRequest
        fields = "__all__"
        read_only_fields = ("owner",)
