from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_transcodejob_auto_generated"),
    ]

    operations = [
        migrations.CreateModel(
            name="TranscodeProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_container_contains", models.CharField(blank=True, default="matroska", max_length=120)),
                ("target_video_codecs", models.JSONField(blank=True, default=list)),
                ("target_audio_codecs", models.JSONField(blank=True, default=list)),
                ("target_subtitle_codecs", models.JSONField(blank=True, default=list)),
                ("transcode_quality", models.CharField(blank=True, default="23", max_length=32)),
                ("transcode_video_codec", models.CharField(blank=True, default="libx264", max_length=120)),
                ("transcode_audio_codec", models.CharField(blank=True, default="aac", max_length=120)),
                ("transcode_ffmpeg_args", models.JSONField(blank=True, default=list)),
                ("output_extension", models.CharField(blank=True, default=".mp4", max_length=16)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
