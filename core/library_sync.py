from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.utils import timezone
import requests
from .models import (
    MediaFile,
    MediaMetadata,
    MediaSource,
    TranscodeJob,
    TranscodeProfile,
    DataSource,
)

LIBRARY_ROOT = Path("/media").resolve()
SCAN_ROOTS = ("movie", "shows")
MEDIA_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".m4v",
    ".webm",
    ".ts",
    ".mpg",
    ".mpeg",
}


@dataclass
class ScanStats:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    missing: int = 0
    complete: int = 0
    needs_processing: int = 0
    failed: int = 0

    def __add__(self, other: ScanStats):
        return ScanStats(
            self.scanned + other.scanned,
            self.created + other.created,
            self.updated + other.updated,
            self.missing + other.missing,
            self.complete + other.complete,
            self.needs_processing + other.needs_processing,
            self.failed + other.failed,
        )


def _media_source_for(path: Path) -> MediaSource:
    return MediaSource.objects.get_or_create(
        path=str(path),
        defaults={"name": path.name},
    )[0]


def _top_level_source(file_path: Path) -> Path:
    try:
        relative = file_path.relative_to(LIBRARY_ROOT)
    except ValueError:
        return file_path.parent
    if not relative.parts:
        return LIBRARY_ROOT
    if len(relative.parts) == 1:
        return LIBRARY_ROOT / relative.parts[0]
    return LIBRARY_ROOT / relative.parts[0] / relative.parts[1]


def _iter_media_files(root: Path):
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTENSIONS:
            yield candidate


def _scan_file(file_path: Path) -> tuple[MediaFile, bool, bool]:
    source_path = _top_level_source(file_path)
    source = _media_source_for(source_path)
    relative_path = str(file_path.relative_to(source_path))
    stat = file_path.stat()
    modified_at = datetime.fromtimestamp(
        stat.st_mtime, tz=timezone.get_current_timezone()
    )
    media_file, created = MediaFile.objects.get_or_create(
        source=source,
        relative_path=relative_path,
        defaults={
            "absolute_path": str(file_path),
            "file_name": file_path.name,
            "size_bytes": stat.st_size,
            "modified_at": modified_at,
            "stage": MediaFile.Stage.DISCOVERED,
            "is_present": True,
        },
    )
    changed = (
        media_file.absolute_path != str(file_path)
        or media_file.file_name != file_path.name
        or media_file.size_bytes != stat.st_size
        or media_file.modified_at != modified_at
    )

    if not created:
        media_file.absolute_path = str(file_path)
        media_file.file_name = file_path.name
        media_file.size_bytes = stat.st_size
        media_file.modified_at = modified_at
        media_file.is_present = True
        if media_file.stage == MediaFile.Stage.MISSING or changed:
            media_file.stage = MediaFile.Stage.DISCOVERED
        media_file.save(
            update_fields=[
                "absolute_path",
                "file_name",
                "size_bytes",
                "modified_at",
                "is_present",
                "stage",
                "updated_at",
            ]
        )

    return media_file, created, changed


def _try_probe(file_path: Path, data_source: DataSource) -> ScanStats:
    stats = ScanStats()
    media_file, created, changed = _scan_file(file_path)
    profile = TranscodeProfile.load()
    try:
        metadata = media_file.metadata_record
    except MediaMetadata.DoesNotExist:
        metadata = None
    should_probe = created or changed or metadata is None
    try:
        if should_probe:
            metadata = collect_metadata_for_media_file(media_file, profile=profile)
    except FileNotFoundError as exc:
        media_file.stage = MediaFile.Stage.FAILED
        media_file.save(update_fields=["stage", "updated_at"])
        stats.failed += 1
        raise exc
    except subprocess.CalledProcessError as exc:
        metadata, _ = MediaMetadata.objects.get_or_create(media_file=media_file)
        metadata.extracted_by = "ffprobe"
        metadata.raw_probe = {"error": exc.stderr or str(exc)}
        metadata.save()
        media_file.stage = MediaFile.Stage.FAILED
        media_file.save(update_fields=["stage", "updated_at"])
        stats.failed += 1
        stats.scanned += 1
        if created:
            stats.created += 1
        else:
            stats.updated += 1
        return stats
    media_file.stage = (
        MediaFile.Stage.COMPLETE
        if metadata.matches_target_profile
        else MediaFile.Stage.TRANSCODE_PENDING
    )
    media_file.data_source = data_source
    media_file.save(update_fields=["stage", "updated_at", "source", "data_source"])
    _upsert_transcode_job(media_file)
    stats.scanned += 1
    if created:
        stats.created += 1
    else:
        stats.updated += 1
    if media_file.stage == MediaFile.Stage.COMPLETE:
        stats.complete += 1
    else:
        stats.needs_processing += 1
    return stats


def _upsert_transcode_job(media_file: MediaFile):
    if media_file.stage == MediaFile.Stage.COMPLETE:
        return
    job = (
        TranscodeJob.objects.filter(
            media_file=media_file,
        )
        .order_by("status", "-created_at")
        .first()
    )

    if job is None:
        TranscodeJob.objects.create(
            media_file=media_file,
            input_path=media_file.absolute_path,
            command="",
            priority=100,
            status=TranscodeJob.Status.PENDING,
        )
        return

    else:
        update_fields: list[str] = ["media_file"]
        if job.input_path != media_file.absolute_path:
            job.input_path = media_file.absolute_path
            update_fields.append("input_path")
        if job.status != TranscodeJob.Status.PENDING:
            job.status = TranscodeJob.Status.PENDING
            update_fields.append("status")
        if job.error_message:
            job.error_message = ""
            update_fields.append("error_message")
        job.media_file = media_file
        if update_fields:
            job.save(update_fields=[*update_fields, "updated_at"])
    return


def _format_name(probe_data: dict) -> str:
    format_data = probe_data.get("format", {})
    return (
        format_data.get("format_name") or format_data.get("format_long_name") or ""
    ).strip()


def _stream_codecs(probe_data: dict, codec_type: str) -> list[str]:
    codecs: list[str] = []
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") != codec_type:
            continue
        codec_name = (
            (stream.get("codec_name") or stream.get("codec_long_name") or "")
            .strip()
            .lower()
        )
        if codec_name and codec_name not in codecs:
            codecs.append(codec_name)
    return codecs


def _matches_target_profile(probe_data: dict, profile: TranscodeProfile) -> bool:
    format_name = _format_name(probe_data).lower()
    container_requirement = (
        (profile.target_container_contains or TranscodeProfile.TARGET_CONTAINER)
        .strip()
        .lower()
    )
    container_ok = container_requirement in format_name
    video_codecs = _stream_codecs(probe_data, "video")
    audio_codecs = _stream_codecs(probe_data, "audio")
    subtitle_codecs = _stream_codecs(probe_data, "subtitle")

    target_video_codecs = [
        codec.strip().lower()
        for codec in (
            profile.target_video_codecs or TranscodeProfile.TARGET_VIDEO_CODECS
        )
        if str(codec).strip()
    ]
    target_audio_codecs = [
        codec.strip().lower()
        for codec in (
            profile.target_audio_codecs or TranscodeProfile.TARGET_AUDIO_CODECS
        )
        if str(codec).strip()
    ]
    target_subtitle_codecs = [
        codec.strip().lower()
        for codec in (
            profile.target_subtitle_codecs or TranscodeProfile.TARGET_SUBTITLE_CODECS
        )
        if str(codec).strip()
    ]

    video_ok = bool(video_codecs) and all(
        codec in target_video_codecs for codec in video_codecs
    )
    audio_ok = bool(audio_codecs) and all(
        codec in target_audio_codecs for codec in audio_codecs
    )
    subtitle_ok = not target_subtitle_codecs or (
        bool(subtitle_codecs)
        and all(codec in target_subtitle_codecs for codec in subtitle_codecs)
    )
    return container_ok and video_ok and audio_ok and subtitle_ok


def _metadata_matches_target_profile(
    metadata: MediaMetadata, profile: TranscodeProfile
) -> bool:
    probe_data = {
        "format": {
            "format_name": metadata.container_format,
            "format_long_name": metadata.container_format,
        },
        "streams": [
            *[
                {"codec_type": "video", "codec_name": codec}
                for codec in (metadata.video_codecs or [])
            ],
            *[
                {"codec_type": "audio", "codec_name": codec}
                for codec in (metadata.audio_codecs or [])
            ],
            *[
                {"codec_type": "subtitle", "codec_name": codec}
                for codec in (metadata.subtitle_codecs or [])
            ],
        ],
    }
    return _matches_target_profile(probe_data, profile)


def _probe_media_file(file_path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FileNotFoundError("ffprobe executable was not found on PATH")

    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _codec_names(probe_data: dict, codec_type: str) -> list[str]:
    return _stream_codecs(probe_data, codec_type)


def _decimal_or_none(value: str | int | float | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def collect_metadata_for_media_file(
    media_file: MediaFile, profile: TranscodeProfile | None = None
) -> MediaMetadata:
    profile = profile or TranscodeProfile.load()
    file_path = Path(media_file.absolute_path)
    probe_data = _probe_media_file(file_path)
    format_data = probe_data.get("format", {})
    container_format = (
        format_data.get("format_long_name") or format_data.get("format_name") or ""
    )
    metadata, _ = MediaMetadata.objects.get_or_create(media_file=media_file)
    metadata.container_format = container_format
    metadata.duration_seconds = _decimal_or_none(format_data.get("duration"))
    bitrate = format_data.get("bit_rate")
    metadata.bitrate = int(bitrate) if str(bitrate).isdigit() else None
    metadata.video_codecs = _codec_names(probe_data, "video")
    metadata.audio_codecs = _codec_names(probe_data, "audio")
    metadata.subtitle_codecs = _codec_names(probe_data, "subtitle")
    metadata.matches_target_profile = _matches_target_profile(probe_data, profile)
    metadata.raw_probe = probe_data
    metadata.extracted_by = "ffprobe"
    metadata.save()
    return metadata


def media_stage_for_job_status(status: str) -> str:
    mapping = {
        "pending": MediaFile.Stage.TRANSCODE_PENDING,
        "running": MediaFile.Stage.TRANSCODING,
        "complete": MediaFile.Stage.COMPLETE,
        "failed": MediaFile.Stage.FAILED,
    }
    return mapping.get(status, MediaFile.Stage.DISCOVERED)


def sync_radarr(source: DataSource) -> ScanStats:
    stats = ScanStats()
    headers = {"X-Api-Key": source.api_key}
    MediaFile.objects.filter(data_source=source).update(
        data_source=DataSource.objects.get(name="Unknown")
    )
    try:
        response = requests.get(
            f"{source.location.rstrip('/')}/api/v3/movie", headers=headers, timeout=60
        )
        response.raise_for_status()
        movies = response.json()
    except Exception as e:
        print("Radarr:", e)
        return stats

    for movie in movies:
        file_info = movie.get("movieFile")
        if not file_info:
            continue

        file_path = Path(file_info["path"])
        stats += _try_probe(file_path, source)

    return stats


def sync_sonarr(source: DataSource) -> ScanStats:
    stats = ScanStats()
    headers = {"X-Api-Key": source.api_key}
    MediaFile.objects.filter(data_source=source).update(
        data_source=DataSource.objects.get(name="Unknown")
    )
    try:
        series_res = requests.get(
            f"{source.location.rstrip('/')}/api/v3/series", headers=headers
        )
        series_res.raise_for_status()
        series_list = series_res.json()
        for series in series_list:
            file_res = requests.get(
                f"{source.location.rstrip('/')}/api/v3/episodefile",
                params={"seriesId": series["id"]},
                headers=headers,
            )
            if file_res.status_code != 200:
                continue

            for ef in file_res.json():
                file_path = Path(ef["path"])
                stats += _try_probe(file_path, source)
    except Exception:
        return stats
    return stats
