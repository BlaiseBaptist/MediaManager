import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import MediaFile, MediaSource, TranscodeJob


class WorkerAPITests(TestCase):
    def _create_job(self) -> tuple[TranscodeJob, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        source_root = Path(temp_dir.name) / "media"
        source_root.mkdir(parents=True)
        media_path = source_root / "Example Movie.mkv"
        media_path.write_bytes(b"example-bytes")

        source = MediaSource.objects.create(name="Library", path=str(source_root))
        media_file = MediaFile.objects.create(
            source=source,
            absolute_path=str(media_path),
            relative_path="Example Movie.mkv",
            file_name="Example Movie.mkv",
            size_bytes=media_path.stat().st_size,
            stage=MediaFile.Stage.TRANSCODE_PENDING,
            is_present=True,
        )
        job = TranscodeJob.objects.create(
            source=source,
            media_file=media_file,
            input_path=str(media_path),
            command="ffmpeg -i input",
            priority=10,
        )
        return job, media_path

    def test_next_job_returns_204_when_queue_is_empty(self):
        response = self.client.get(reverse("worker_next_job"))

        self.assertEqual(response.status_code, 204)

    def test_next_job_claims_job_and_exposes_download_url(self):
        job, media_path = self._create_job()

        response = self.client.get(reverse("worker_next_job"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(job.id))
        self.assertEqual(payload["filename"], "Example Movie.mkv")
        self.assertTrue(payload["input_url"].startswith("http://testserver/api/media/jobs/"))
        self.assertEqual(payload["transcode"]["quality"], "23")
        self.assertEqual(payload["transcode"]["video_codec"], "libaom-av1")
        self.assertEqual(payload["transcode"]["audio_codec"], "libopus")
        self.assertEqual(payload["delivery"]["filename"], "Example Movie.mkv")

        job.refresh_from_db()
        self.assertEqual(job.status, TranscodeJob.Status.RUNNING)
        self.assertEqual(job.media_file.stage, MediaFile.Stage.TRANSCODING)

        download_path = urlsplit(payload["input_url"]).path
        download = self.client.get(download_path)

        self.assertEqual(download.status_code, 200)
        streamed = b"".join(download.streaming_content)
        self.assertEqual(streamed, media_path.read_bytes())
        self.assertIn('filename="Example Movie.mkv"', download.headers["Content-Disposition"])

    @override_settings(MEDIA_MANAGER_AUTH_TOKEN="secret-token")
    def test_worker_endpoints_require_authorization_when_token_is_configured(self):
        job, _ = self._create_job()

        unauthorized = self.client.get(reverse("worker_next_job"))
        self.assertEqual(unauthorized.status_code, 401)

        authorized = self.client.get(
            reverse("worker_next_job"),
            HTTP_AUTHORIZATION="Bearer secret-token",
        )
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()["id"], str(job.id))
