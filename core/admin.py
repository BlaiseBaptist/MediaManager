from django.contrib import admin

from .models import MediaSource, TranscodeJob


@admin.register(MediaSource)
class MediaSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "path", "created_at")
    search_fields = ("name", "path")


@admin.register(TranscodeJob)
class TranscodeJobAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("source__name", "command")
