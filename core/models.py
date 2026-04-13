from django.db import models


class MediaSource(models.Model):
    name = models.CharField(max_length=200)
    path = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class TranscodeJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    source = models.ForeignKey(MediaSource, on_delete=models.CASCADE, related_name="jobs")
    input_path = models.CharField(max_length=500, default="")
    command = models.TextField(default="")
    priority = models.PositiveSmallIntegerField(default=100, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.source.name} - {self.input_path} ({self.status})"

    class Meta:
        ordering = ["status", "priority", "-created_at"]
