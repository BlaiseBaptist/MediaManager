from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.utils import timezone

from .models import MediaFile, MediaSource

LIBRARY_ROOT = Path("/Volumes/media").resolve()
SCAN_ROOTS = ("movie", "shows")
MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".ts", ".mpg", ".mpeg"}


@dataclass
class ScanStats:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    missing: int = 0


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
            "stage": MediaFile.Stage.DISCOVERED,
            "is_present": True,
        },
    )

    if not created:
        media_file.absolute_path = str(file_path)
        media_file.file_name = file_path.name
        media_file.size_bytes = stat.st_size
        media_file.modified_at = modified_at
        media_file.is_present = True
        if media_file.stage == MediaFile.Stage.MISSING:
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


def media_stage_for_job_status(status: str) -> str:
    mapping = {
        "pending": MediaFile.Stage.TRANSCODE_PENDING,
        "running": MediaFile.Stage.TRANSCODING,
        "complete": MediaFile.Stage.READY,
        "failed": MediaFile.Stage.FAILED,
    }
    return mapping.get(status, MediaFile.Stage.DISCOVERED)
