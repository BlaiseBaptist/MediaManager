import tempfile
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from core.models import MediaFile, MediaSource, TranscodeJob


class QueueViewTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        root = Path(self.temp_dir.name)
        self.source_a = MediaSource.objects.create(name="Alpha", path=str(root / "alpha"))
        self.source_b = MediaSource.objects.create(name="Beta", path=str(root / "beta"))

        self.file_a = MediaFile.objects.create(
            source=self.source_a,
            absolute_path=str(root / "alpha" / "one.mkv"),
            relative_path="one.mkv",
            file_name="one.mkv",
            size_bytes=100,
            stage=MediaFile.Stage.TRANSCODE_PENDING,
            is_present=True,
        )
        self.file_b = MediaFile.objects.create(
            source=self.source_b,
            absolute_path=str(root / "beta" / "two.mkv"),
            relative_path="two.mkv",
            file_name="two.mkv",
            size_bytes=100,
            stage=MediaFile.Stage.TRANSCODE_PENDING,
            is_present=True,
        )

    def test_queue_filters_by_status_source_and_auto_generated(self):
        auto_job = TranscodeJob.objects.create(
            source=self.source_a,
            media_file=self.file_a,
            input_path=self.file_a.absolute_path,
            command="auto",
            status=TranscodeJob.Status.PENDING,
            auto_generated=True,
        )
        TranscodeJob.objects.create(
            source=self.source_b,
            media_file=self.file_b,
            input_path=self.file_b.absolute_path,
            command="manual",
            status=TranscodeJob.Status.RUNNING,
            auto_generated=False,
        )

        response = self.client.get(
            reverse("queue"),
            {"status": "pending", "source": str(self.source_a.id), "auto_generated": "1"},
        )

        self.assertEqual(response.status_code, 200)
        jobs = list(response.context["jobs"])
        self.assertEqual([job.id for job in jobs], [auto_job.id])

    def test_requeue_job_moves_running_job_back_to_pending(self):
        job = TranscodeJob.objects.create(
            source=self.source_a,
            media_file=self.file_a,
            input_path=self.file_a.absolute_path,
            command="auto",
            status=TranscodeJob.Status.RUNNING,
            auto_generated=True,
            error_message="boom",
        )

        response = self.client.post(
            reverse("requeue_job", args=[job.id]),
            {"next": reverse("queue")},
        )

        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, TranscodeJob.Status.PENDING)
        self.assertEqual(job.error_message, "")
        self.file_a.refresh_from_db()
        self.assertEqual(self.file_a.stage, MediaFile.Stage.TRANSCODE_PENDING)
