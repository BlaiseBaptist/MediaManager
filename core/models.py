from django.db import models


class MediaSource(models.Model):
    name = models.CharField(max_length=200)
    path = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class DataSource(models.Model):
    name = models.CharField(max_length=200)
    location = models.URLField(blank=True)
    api_key = models.CharField(max_length=100, blank=True, default="")


class MediaFile(models.Model):
    class Stage(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        TRANSCODE_PENDING = "transcode_pending", "Transcode pending"
        TRANSCODING = "transcoding", "Transcoding"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"
        MISSING = "missing", "Missing"

    source = models.ForeignKey(
        MediaSource, on_delete=models.CASCADE, related_name="media_files"
    )
    data_source = models.ForeignKey(
        DataSource, on_delete=models.PROTECT, null=True, blank=True
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
    raw_probe = models.JSONField(default=dict, blank=True)
    extracted_by = models.CharField(max_length=120, blank=True, default="")
    probed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def matches_target_profile(self) -> bool:
        profile = TranscodeProfile.load()
        if self.container_format.lower() != profile.container.lower():
            return False
        if not all(codec in profile.video_codecs for codec in self.video_codecs):
            return False
        if not all(codec in profile.audio_codecs for codec in self.audio_codecs):
            return False
        if not all(codec in profile.subtitle_codecs for codec in self.subtitle_codecs):
            return False
        return True

    def __str__(self) -> str:
        return f"Metadata for {self.media_file.absolute_path}"


class TranscodeProfile(models.Model):
    CONTAINER = "matroska"
    VIDEO_CODECS = ["av1"]
    AUDIO_CODECS = ["opus"]
    SUBTITLE_CODECS: list[str] = []
    BITRATES = ["100M"]
    container = models.CharField(max_length=120, blank=True, default=CONTAINER)
    video_codecs = models.JSONField(default=list, blank=True)
    audio_codecs = models.JSONField(default=list, blank=True)
    subtitle_codecs = models.JSONField(default=list, blank=True)
    bitrates = models.JSONField(default=list, blank=True)

    @classmethod
    def load(cls) -> "TranscodeProfile":
        profile, _ = cls.objects.get_or_create(pk=1)
        fixed_values = {
            "container": cls.CONTAINER,
            "video_codecs": cls.VIDEO_CODECS,
            "audio_codecs": cls.AUDIO_CODECS,
            "subtitle_codecs": cls.SUBTITLE_CODECS,
            "bitrates": cls.BITRATES,
        }
        changed = False
        for field_name, expected in fixed_values.items():
            if getattr(profile, field_name) != expected:
                setattr(profile, field_name, expected)
                changed = True
        if changed:
            profile.save(update_fields=[*fixed_values.keys()])
        return profile

    def __str__(self) -> str:
        return "Transcode profile"


class TranscodeJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    transcode_profile = models.ForeignKey(
        TranscodeProfile, on_delete=models.PROTECT, default=TranscodeProfile.load
    )
    media_file = models.ForeignKey(
        MediaFile, on_delete=models.CASCADE, related_name="jobs", null=True, blank=True
    )
    input_path = models.CharField(max_length=500, default="")
    command = models.TextField(default="")
    priority = models.PositiveSmallIntegerField(default=100, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    worker = models.TextField(
        default="",
    )

    def __str__(self) -> str:
        return f"{self.media_file.source.name} - {self.input_path} ({self.status})"

    class Meta:
        ordering = ["status", "priority", "-created_at"]
