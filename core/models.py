from django.db import models


class MediaSource(models.Model):
    name = models.CharField(max_length=200)
    path = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class MediaFile(models.Model):
    class Stage(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        TRANSCODE_PENDING = "transcode_pending", "Transcode pending"
        TRANSCODING = "transcoding", "Transcoding"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        MISSING = "missing", "Missing"

    source = models.ForeignKey(
        MediaSource, on_delete=models.CASCADE, related_name="media_files"
    )
    absolute_path = models.CharField(max_length=600, unique=True)
    relative_path = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField(default=0)
    modified_at = models.DateTimeField(null=True, blank=True)
    stage = models.CharField(
        max_length=32, choices=Stage.choices, default=Stage.DISCOVERED, db_index=True
    )
    is_present = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.absolute_path

    class Meta:
        ordering = ["stage", "source__name", "relative_path"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "relative_path"],
                name="unique_mediafile_per_source_relative_path",
            ),
        ]


class MediaMetadata(models.Model):
    media_file = models.OneToOneField(
        MediaFile, on_delete=models.CASCADE, related_name="metadata_record"
    )
    container_format = models.CharField(max_length=120, blank=True, default="")
    duration_seconds = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )
    bitrate = models.BigIntegerField(null=True, blank=True)
    video_codecs = models.JSONField(default=list, blank=True)
    audio_codecs = models.JSONField(default=list, blank=True)
    subtitle_codecs = models.JSONField(default=list, blank=True)
    matches_target_profile = models.BooleanField(default=False, db_index=True)
    raw_probe = models.JSONField(default=dict, blank=True)
    extracted_by = models.CharField(max_length=120, blank=True, default="")
    probed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Metadata for {self.media_file.absolute_path}"


class TranscodeProfile(models.Model):
    FIXED_TRANSCODE_QUALITY = "23"
    FIXED_TRANSCODE_VIDEO_CODEC = "libsav1"
    FIXED_TRANSCODE_AUDIO_CODEC = "libopus"
    FIXED_OUTPUT_EXTENSION = ".mkv"
    FIXED_TARGET_CONTAINER_CONTAINS = "matroska"
    FIXED_TARGET_VIDEO_CODECS = ["av1"]
    FIXED_TARGET_AUDIO_CODECS = ["opus"]
    FIXED_TARGET_SUBTITLE_CODECS: list[str] = []

    target_container_contains = models.CharField(
        max_length=120, blank=True, default=FIXED_TARGET_CONTAINER_CONTAINS
    )
    target_video_codecs = models.JSONField(default=list, blank=True)
    target_audio_codecs = models.JSONField(default=list, blank=True)
    target_subtitle_codecs = models.JSONField(default=list, blank=True)
    transcode_quality = models.CharField(
        max_length=32, blank=True, default=FIXED_TRANSCODE_QUALITY
    )
    transcode_video_codec = models.CharField(
        max_length=120, blank=True, default=FIXED_TRANSCODE_VIDEO_CODEC
    )
    transcode_audio_codec = models.CharField(
        max_length=120, blank=True, default=FIXED_TRANSCODE_AUDIO_CODEC
    )
    transcode_ffmpeg_args = models.JSONField(default=list, blank=True)
    output_extension = models.CharField(
        max_length=16, blank=True, default=FIXED_OUTPUT_EXTENSION
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def load(cls) -> "TranscodeProfile":
        profile, _ = cls.objects.get_or_create(pk=1)
        fixed_values = {
            "target_container_contains": cls.FIXED_TARGET_CONTAINER_CONTAINS,
            "target_video_codecs": cls.FIXED_TARGET_VIDEO_CODECS,
            "target_audio_codecs": cls.FIXED_TARGET_AUDIO_CODECS,
            "target_subtitle_codecs": cls.FIXED_TARGET_SUBTITLE_CODECS,
            "transcode_quality": cls.FIXED_TRANSCODE_QUALITY,
            "transcode_video_codec": cls.FIXED_TRANSCODE_VIDEO_CODEC,
            "transcode_audio_codec": cls.FIXED_TRANSCODE_AUDIO_CODEC,
            "output_extension": cls.FIXED_OUTPUT_EXTENSION,
        }
        changed = False
        for field_name, expected in fixed_values.items():
            if getattr(profile, field_name) != expected:
                setattr(profile, field_name, expected)
                changed = True
        if changed:
            profile.save(update_fields=[*fixed_values.keys(), "updated_at"])
        return profile

    def __str__(self) -> str:
        return "Transcode profile"


class TranscodeJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    source = models.ForeignKey(
        MediaSource, on_delete=models.CASCADE, related_name="jobs"
    )
    media_file = models.ForeignKey(
        MediaFile, on_delete=models.CASCADE, related_name="jobs", null=True, blank=True
    )
    input_path = models.CharField(max_length=500, default="")
    command = models.TextField(default="")
    priority = models.PositiveSmallIntegerField(default=100, db_index=True)
    auto_generated = models.BooleanField(default=False, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.source.name} - {self.input_path} ({self.status})"

    class Meta:
        ordering = ["status", "priority", "-created_at"]
