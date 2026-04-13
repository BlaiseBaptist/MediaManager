from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.utils import timezone

from .models import MediaFile, MediaMetadata, MediaSource

LIBRARY_ROOT = Path("/media").resolve()
SCAN_ROOTS = ("movie", "shows")
MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".ts", ".mpg", ".mpeg"}


@dataclass
class ScanStats:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    missing: int = 0


@dataclass
class MetadataStats:
    processed: int = 0
    ready: int = 0
    failed: int = 0


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


def _scan_file(file_path: Path) -> tuple[MediaFile, bool]:
    source_path = _top_level_source(file_path)
    source = _media_source_for(source_path)
    relative_path = str(file_path.relative_to(source_path))
    stat = file_path.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone())

    media_file, created = MediaFile.objects.get_or_create(
        source=source,
        relative_path=relative_path,
        defaults={
            "absolute_path": str(file_path),
            "file_name": file_path.name,
            "size_bytes": stat.st_size,
            "modified_at": modified_at,
            "stage": MediaFile.Stage.METADATA_PENDING,
            "is_present": True,
        },
    )
    metadata_exists = MediaMetadata.objects.filter(media_file=media_file).exists()
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
        if media_file.stage == MediaFile.Stage.MISSING:
            media_file.stage = MediaFile.Stage.METADATA_PENDING
        if changed and metadata_exists:
            media_file.metadata_record.delete()
            metadata_exists = False
        if not metadata_exists and media_file.stage not in (
            MediaFile.Stage.TRANSCODE_PENDING,
            MediaFile.Stage.TRANSCODING,
        ):
            media_file.stage = MediaFile.Stage.METADATA_PENDING
        elif metadata_exists and media_file.stage in (MediaFile.Stage.DISCOVERED, MediaFile.Stage.METADATA_PENDING):
            media_file.stage = MediaFile.Stage.METADATA_READY
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

    return media_file, created


def sync_media_library() -> ScanStats:
    stats = ScanStats()
    seen_paths: set[str] = set()

    for root_name in SCAN_ROOTS:
        root = (LIBRARY_ROOT / root_name).resolve()
        if not root.exists():
            continue
        _media_source_for(root)
        for file_path in _iter_media_files(root):
            media_file, created = _scan_file(file_path)
            seen_paths.add(media_file.absolute_path)
            stats.scanned += 1
            if created:
                stats.created += 1
            else:
                stats.updated += 1

    for media_file in MediaFile.objects.filter(is_present=True):
        if media_file.absolute_path not in seen_paths:
            media_file.is_present = False
            media_file.stage = MediaFile.Stage.MISSING
            media_file.save(update_fields=["is_present", "stage", "updated_at"])
            stats.missing += 1

    return stats


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
    codecs: list[str] = []
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") != codec_type:
            continue
        codec_name = stream.get("codec_name") or stream.get("codec_long_name") or ""
        if codec_name and codec_name not in codecs:
            codecs.append(codec_name)
    return codecs


def _decimal_or_none(value: str | int | float | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def collect_metadata_for_media_file(media_file: MediaFile) -> MediaMetadata:
    file_path = Path(media_file.absolute_path)
    probe_data = _probe_media_file(file_path)
    format_data = probe_data.get("format", {})
    container_format = format_data.get("format_long_name") or format_data.get("format_name") or ""
    metadata, _ = MediaMetadata.objects.get_or_create(media_file=media_file)
    metadata.container_format = container_format
    metadata.duration_seconds = _decimal_or_none(format_data.get("duration"))
    bitrate = format_data.get("bit_rate")
    metadata.bitrate = int(bitrate) if str(bitrate).isdigit() else None
    metadata.video_codecs = _codec_names(probe_data, "video")
    metadata.audio_codecs = _codec_names(probe_data, "audio")
    metadata.subtitle_codecs = _codec_names(probe_data, "subtitle")
    metadata.raw_probe = probe_data
    metadata.extracted_by = "ffprobe"
    metadata.save()
    media_file.stage = MediaFile.Stage.METADATA_READY
    media_file.save(update_fields=["stage", "updated_at"])
    return metadata


def process_pending_metadata(limit: int | None = None) -> MetadataStats:
    stats = MetadataStats()
    pending = MediaFile.objects.select_related("source").filter(
        is_present=True,
        stage__in=[MediaFile.Stage.DISCOVERED, MediaFile.Stage.METADATA_PENDING],
    ).order_by("updated_at")
    if limit is not None:
        pending = pending[:limit]

    for media_file in pending:
        stats.processed += 1
        try:
            collect_metadata_for_media_file(media_file)
        except Exception as exc:
            if isinstance(exc, FileNotFoundError):
                raise
            metadata, _ = MediaMetadata.objects.get_or_create(media_file=media_file)
            metadata.extracted_by = "ffprobe"
            error_text = getattr(exc, "stderr", None) or str(exc)
            metadata.raw_probe = {"error": error_text}
            metadata.save()
            media_file.stage = MediaFile.Stage.FAILED
            media_file.save(update_fields=["stage", "updated_at"])
            stats.failed += 1
        else:
            stats.ready += 1

    return stats


def media_stage_for_job_status(status: str) -> str:
    mapping = {
        "pending": MediaFile.Stage.TRANSCODE_PENDING,
        "running": MediaFile.Stage.TRANSCODING,
        "complete": MediaFile.Stage.READY,
        "failed": MediaFile.Stage.FAILED,
    }
    return mapping.get(status, MediaFile.Stage.DISCOVERED)
