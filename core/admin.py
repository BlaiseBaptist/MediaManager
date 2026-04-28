from django.contrib import admin

from .models import (
    MediaSource,
    DataSource,
    MediaFile,
    MediaMetadata,
    TranscodeProfile,
    TranscodeJob,
)


@admin.register(MediaSource)
class MediaSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "path", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name",)
    date_hierarchy = "created_at"


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "location")
    search_fields = ("name",)


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "data_source",
        "absolute_path",
        "relative_path",
        "file_name",
        "size_bytes",
        "modified_at",
        "stage",
        "is_present",
        "last_seen_at",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "modified_at",
        "is_present",
        "last_seen_at",
        "created_at",
        "updated_at",
        "stage",
        "data_source__name",
    )
    raw_id_fields = ("source", "data_source")
    date_hierarchy = "created_at"


@admin.register(MediaMetadata)
class MediaMetadataAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "media_file",
        "container_format",
        "duration_seconds",
        "bitrate",
        "video_codecs",
        "audio_codecs",
        "subtitle_codecs",
        "matches_target_profile",
        "raw_probe",
        "extracted_by",
        "probed_at",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "probed_at",
        "created_at",
        "updated_at",
    )
    raw_id_fields = ("media_file",)
    date_hierarchy = "created_at"


@admin.register(TranscodeProfile)
class TranscodeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "container",
        "video_codecs",
        "audio_codecs",
        "subtitle_codecs",
        "bitrates",
    )
    list_filter = ("container", "video_codecs", "audio_codecs", "bitrates")


@admin.register(TranscodeJob)
class TranscodeJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "media_file",
        "input_path",
        "command",
        "priority",
        "status",
        "error_message",
        "created_at",
        "updated_at",
        "worker",
    )
    list_filter = ("created_at", "updated_at")
    raw_id_fields = ("media_file",)
    date_hierarchy = "created_at"
