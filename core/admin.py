from django.contrib import admin

from .models import MediaSource, TranscodeJob


@admin.register(MediaSource)
class MediaSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "path", "created_at")
    search_fields = ("name", "path")


@admin.register(TranscodeJob)
class TranscodeJobAdmin(admin.ModelAdmin):
    list_display = ("source", "input_path", "priority", "status", "created_at", "updated_at")
    list_filter = ("status", "priority")
    search_fields = ("source__name", "source__path", "input_path", "command", "error_message")
    ordering = ("status", "priority", "-created_at")
