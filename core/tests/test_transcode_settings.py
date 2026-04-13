import tempfile
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from core.models import MediaFile, MediaMetadata, MediaSource, TranscodeProfile


class TranscodeSettingsTests(TestCase):
    def test_saving_settings_updates_profile_and_refreshes_library_matches(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        root = Path(temp_dir.name)
        source = MediaSource.objects.create(name="Library", path=str(root / "media"))
        media_file = MediaFile.objects.create(
            source=source,
            absolute_path=str(root / "media" / "episode.mkv"),
            relative_path="episode.mkv",
            file_name="episode.mkv",
            size_bytes=100,
            stage=MediaFile.Stage.TRANSCODE_PENDING,
            is_present=True,
        )
        MediaMetadata.objects.create(
            media_file=media_file,
            container_format="AVI",
            video_codecs=["h264"],
            audio_codecs=["aac"],
            subtitle_codecs=[],
            matches_target_profile=False,
        )

        response = self.client.post(
            reverse("transcode_settings"),
            {
                "target_container_contains": "avi",
                "target_video_codecs_text": "h264",
                "target_audio_codecs_text": "aac",
                "target_subtitle_codecs_text": "",
                "transcode_quality": "20",
                "transcode_video_codec": "libx265",
                "transcode_audio_codec": "aac",
                "output_extension": ".mkv",
                "transcode_ffmpeg_args_text": "-preset\nslow",
            },
        )

        self.assertEqual(response.status_code, 302)

        profile = TranscodeProfile.load()
        self.assertEqual(profile.target_container_contains, "avi")
        self.assertEqual(profile.transcode_quality, "20")
        self.assertEqual(profile.transcode_video_codec, "libx265")
        self.assertEqual(profile.output_extension, ".mkv")
        self.assertEqual(profile.transcode_ffmpeg_args, ["-preset", "slow"])

        media_file.refresh_from_db()
        self.assertEqual(media_file.stage, MediaFile.Stage.READY)
        self.assertTrue(media_file.metadata_record.matches_target_profile)
