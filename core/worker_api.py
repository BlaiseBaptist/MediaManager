from .models import MediaFile, TranscodeJob, TranscodeProfile
import json

# from urllib.parse import quote, urljoin
from pathlib import Path
from datetime import timedelta, datetime
# from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from .library_sync import LIBRARY_ROOT
import os
BLOCKED_FFMPEG_FLAGS = {
    "-c",
    "-codec",
    "-c:v",
    "-codec:v",
    "-c:a",
    "-codec:a",
    "-f",
    "-map",
    "-vn",
    "-an",
    "-sn",
    "-dn",
}

FLAGS_WITH_VALUES = {
    "-c",
    "-codec",
    "-c:v",
    "-codec:v",
    "-c:a",
    "-codec:a",
    "-f",
    "-map",
}


def _job_filename(job: TranscodeJob) -> str:
    if job.media_file_id and job.media_file.file_name:
        return job.media_file.file_name
    candidate = Path(job.input_path).name
    return candidate or "input.bin"


def _job_input_url(request, job: TranscodeJob) -> str:
    return job.input_path[len(str(LIBRARY_ROOT)):]


def _job_output_url(request, job: TranscodeJob) -> str:
    return "/scratch/"+str(job.media_file.id)+".part"


def _request_json(request) -> dict[str, object]:
    if not request.body:
        return {}
    try:
        parsed = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_ffmpeg_args(args: list[str]) -> list[str]:
    sanitized: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in BLOCKED_FFMPEG_FLAGS:
            if arg in FLAGS_WITH_VALUES:
                skip_next = True
            continue
        sanitized.append(arg)
    return sanitized


def _job_payload(request, job: TranscodeJob) -> dict[str, object]:
    profile = TranscodeProfile.load()
    payload = {
        "id": str(job.id),
        "input_url": _job_input_url(request, job),
        "output_url": _job_output_url(request, job),
        "filename": _job_filename(job),
    }
    payload["transcode"] = {
        "quality": "HIGH",
        "video_codec": profile.target_video_codecs[0],
        "audio_codec": profile.target_audio_codecs[0],
    }
    return payload


def _claim_next_job() -> TranscodeJob | None:
    candidate = (
        TranscodeJob.objects.select_related("source", "media_file")
        .filter(status=TranscodeJob.Status.PENDING)
        .order_by("priority", "-created_at")
        .first()
    )
    if candidate is None:
        candidate = (TranscodeJob.objects.select_related("source", "media_file")
                     .filter(status=TranscodeJob.Status.RUNNING)
                     .order_by("priority", "-created_at").last())
        if candidate is None:
            return None
        if ((candidate.updated_at + timedelta(hours=12) >
             datetime.now(timezone.get_current_timezone()))):
            return None
        TranscodeJob.objects.filter(
            pk=candidate.pk, status=TranscodeJob.Status.RUNNING
        ).update(status=TranscodeJob.Status.PENDING)

    updated = TranscodeJob.objects.filter(
        pk=candidate.pk, status=TranscodeJob.Status.PENDING
    ).update(
        status=TranscodeJob.Status.RUNNING, error_message="", updated_at=timezone.now()
    )
    if not updated:
        return None

    if candidate.media_file_id:
        MediaFile.objects.filter(pk=candidate.media_file_id).update(
            stage=MediaFile.Stage.TRANSCODING,
            is_present=True,
            updated_at=timezone.now(),
        )

    candidate.refresh_from_db()
    return candidate


@require_GET
def worker_next_job(request):
    job = _claim_next_job()
    if job is None:
        return HttpResponse(status=204)

    return JsonResponse(_job_payload(request, job))


@require_GET
def worker_job_input(request, job_id: int):

    job = get_object_or_404(
        TranscodeJob.objects.select_related("media_file"), pk=job_id
    )
    source_path = job.media_file.absolute_path if job.media_file_id else job.input_path
    file_path = Path(source_path)
    if not file_path.is_file():
        return HttpResponse(status=404)

    filename = _job_filename(job)
    return FileResponse(file_path.open("rb"), as_attachment=True, filename=filename)


@csrf_exempt
@require_GET
def worker_complete_job(request, job_id: int):

    _request_json(request)
    job = get_object_or_404(
        TranscodeJob.objects.select_related("media_file"), pk=job_id
    )
    os.rename("/media/scratch/"+str(job.media_file.id)+".part", job.input_path)
    job.status = TranscodeJob.Status.COMPLETE
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    if job.media_file_id:
        job.media_file.stage = MediaFile.Stage.READY
        job.media_file.is_present = True
        job.media_file.save(
            update_fields=["stage", "is_present", "updated_at"])
    return HttpResponse(status=204)


@csrf_exempt
@require_GET
def worker_failed_job(request, job_id: int):

    payload = _request_json(request)
    job = get_object_or_404(
        TranscodeJob.objects.select_related("media_file"), pk=job_id
    )
    job.status = TranscodeJob.Status.FAILED
    job.error_message = (
        str(payload.get("error", "")) if payload.get(
            "error") is not None else ""
    )
    job.save(update_fields=["status", "error_message", "updated_at"])
    if job.media_file_id:
        job.media_file.stage = MediaFile.Stage.FAILED
        job.media_file.save(update_fields=["stage", "updated_at"])
    return HttpResponse(status=204)
