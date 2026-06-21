from django.contrib import admin

from cutout.service.models import Job, JobParameter, JobResult, Task


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    readonly_fields = (
        "sequence",
        "status",
        "stencil_type",
        "survey_id",
        "band",
        "output_format",
        "engine",
        "color",
        "persist",
        "output_path",
        "start_time",
        "end_time",
        "error_message",
    )
    fields = readonly_fields
    can_delete = False
    show_change_link = True


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Job._meta.fields]
    inlines = [TaskInline]


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


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "sequence", "status", "stencil_type", "survey_id", "band", "engine", "start_time", "end_time")
    list_filter = ("status", "stencil_type", "engine")
    readonly_fields = (
        "job",
        "sequence",
        "survey_id",
        "stencil",
        "stencil_type",
        "band",
        "output_format",
        "engine",
        "color",
        "rgb_bands",
        "persist",
        "output_path",
        "status",
        "start_time",
        "end_time",
        "error_message",
    )
