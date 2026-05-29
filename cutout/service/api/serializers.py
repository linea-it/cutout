from django.urls import reverse
from rest_framework import serializers

from cutout.service.models import Job, JobParameter, JobResult


class JobParameterSerializer(serializers.ModelSerializer[JobParameter]):
    class Meta:
        model = JobParameter
        fields = ("parameter", "value", "is_post")


class JobResultSerializer(serializers.ModelSerializer[JobResult]):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = JobResult
        fields = ("result_id", "sequence", "mime_type", "size", "url", "download_url")

    def get_download_url(self, obj: JobResult) -> str:
        request = self.context.get("request")
        path = reverse("api:async_job_result", kwargs={"job_id": obj.job_id, "result_id": obj.result_id})
        return request.build_absolute_uri(path) if request else path


class AsyncJobSummarySerializer(serializers.ModelSerializer[Job]):
    job_id = serializers.IntegerField(source="id", read_only=True)
    phase_url = serializers.SerializerMethodField()
    parameters_url = serializers.SerializerMethodField()
    results_url = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = (
            "job_id",
            "phase",
            "run_id",
            "message_id",
            "creation_time",
            "start_time",
            "end_time",
            "destruction_time",
            "quote",
            "phase_url",
            "parameters_url",
            "results_url",
        )

    def _build_url(self, route_name: str, job: Job) -> str:
        request = self.context.get("request")
        path = reverse(route_name, kwargs={"job_id": job.id})
        return request.build_absolute_uri(path) if request else path

    def get_phase_url(self, obj: Job) -> str:
        return self._build_url("api:async_job_phase", obj)

    def get_parameters_url(self, obj: Job) -> str:
        return self._build_url("api:async_job_parameters", obj)

    def get_results_url(self, obj: Job) -> str:
        return self._build_url("api:async_job_results", obj)


class AsyncJobDetailSerializer(AsyncJobSummarySerializer):
    parameters = JobParameterSerializer(many=True, read_only=True)
    results = JobResultSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = AsyncJobSummarySerializer.Meta.fields + ("parameters", "results")
