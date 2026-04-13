# Generated manually to simplify the media workflow.

from django.db import migrations, models


def remap_media_stages(apps, schema_editor):
    MediaFile = apps.get_model("core", "MediaFile")
    MediaFile.objects.filter(stage="metadata_ready").update(stage="ready")
    MediaFile.objects.filter(stage="metadata_pending").update(stage="discovered")


def backfill_target_profile_matches(apps, schema_editor):
    MediaMetadata = apps.get_model("core", "MediaMetadata")
    for metadata in MediaMetadata.objects.all():
        container = (metadata.container_format or "").lower()
        video_codecs = [str(codec).strip().lower() for codec in (metadata.video_codecs or []) if str(codec).strip()]
        audio_codecs = [str(codec).strip().lower() for codec in (metadata.audio_codecs or []) if str(codec).strip()]
        metadata.matches_target_profile = (
            "matroska" in container
            and bool(video_codecs)
            and all(codec == "av1" for codec in video_codecs)
            and bool(audio_codecs)
            and all(codec == "flac" for codec in audio_codecs)
        )
        metadata.save(update_fields=["matches_target_profile"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_remove_mediafile_metadata_mediametadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediametadata",
            name="matches_target_profile",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name="mediafile",
            name="stage",
            field=models.CharField(
                choices=[
                    ("discovered", "Discovered"),
                    ("transcode_pending", "Transcode pending"),
                    ("transcoding", "Transcoding"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                    ("missing", "Missing"),
                ],
                db_index=True,
                default="discovered",
                max_length=32,
            ),
        ),
        migrations.RunPython(backfill_target_profile_matches, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(remap_media_stages, reverse_code=migrations.RunPython.noop),
    ]
