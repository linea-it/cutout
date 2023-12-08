from django.contrib import admin

from cutout.service.models import Job, JobParameter, JobResult


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Job._meta.fields]


@admin.register(JobParameter)
class JobParameterAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "parameter", "value")


@admin.register(JobResult)
class JobResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "result_id",
        "sequence",
        "size",
        "mime_type",
    )
