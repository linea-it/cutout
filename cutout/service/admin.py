from django.contrib import admin

from cutout.service.models import JobRequest


@admin.register(JobRequest)
class JobRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "status")
