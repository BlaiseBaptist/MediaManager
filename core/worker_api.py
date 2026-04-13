import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import MediaFile, TranscodeJob, TranscodeProfile

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


def _authenticate_worker(request) -> HttpResponse | None:
    token = getattr(settings, "MEDIA_MANAGER_AUTH_TOKEN", None)
    if not token:
        return None

    header = request.headers.get("Authorization", "")
    expected = f"Bearer {token}"
    if header != expected:
        return HttpResponse(status=401)
    return None


def _job_filename(job: TranscodeJob) -> str:
    if job.media_file_id and job.media_file.file_name:
        return job.media_file.file_name
    candidate = Path(job.input_path).name
    return candidate or "input.bin"


def _delivery_filename(job: TranscodeJob) -> str:
    if job.media_file_id and job.media_file.file_name:
        extension = _delivery_extension()
        return f"{Path(job.media_file.file_name).stem}{extension}"
    candidate = Path(job.input_path).stem
    extension = _delivery_extension()
    return f"{candidate}{extension}" if candidate else f"output{extension}"


def _delivery_extension() -> str:
    profile = TranscodeProfile.load()
    extension = (profile.output_extension or ".mp4").strip()
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension


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
        "input_url": request.build_absolute_uri(reverse("worker_job_input", args=[job.id])),
        "filename": _job_filename(job),
    }
    payload["transcode"] = {
        "quality": profile.transcode_quality,
        "video_codec": profile.transcode_video_codec,
        "audio_codec": profile.transcode_audio_codec,
        "ffmpeg_args": _sanitize_ffmpeg_args(profile.transcode_ffmpeg_args),
    }
    payload["delivery"] = {
        "output_url": request.build_absolute_uri(reverse("worker_job_output", args=[job.id])),
        "filename": _delivery_filename(job),
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
        return None

    updated = (
        TranscodeJob.objects.filter(pk=candidate.pk, status=TranscodeJob.Status.PENDING)
        .update(status=TranscodeJob.Status.RUNNING, error_message="", updated_at=timezone.now())
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
    auth_error = _authenticate_worker(request)
    if auth_error is not None:
        return auth_error

    job = _claim_next_job()
    if job is None:
        return HttpResponse(status=204)

    return JsonResponse(_job_payload(request, job))


@require_GET
def worker_job_input(request, job_id: int):
    auth_error = _authenticate_worker(request)
    if auth_error is not None:
        return auth_error

    job = get_object_or_404(TranscodeJob.objects.select_related("media_file"), pk=job_id)
    source_path = job.media_file.absolute_path if job.media_file_id else job.input_path
    file_path = Path(source_path)
    if not file_path.is_file():
        return HttpResponse(status=404)

    filename = _job_filename(job)
    return FileResponse(file_path.open("rb"), as_attachment=True, filename=filename)


@csrf_exempt
@require_POST
def worker_complete_job(request, job_id: int):
    auth_error = _authenticate_worker(request)
    if auth_error is not None:
        return auth_error

    _request_json(request)
    job = get_object_or_404(TranscodeJob.objects.select_related("media_file"), pk=job_id)
    job.status = TranscodeJob.Status.COMPLETE
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    if job.media_file_id:
        job.media_file.stage = MediaFile.Stage.READY
        job.media_file.is_present = True
        job.media_file.save(update_fields=["stage", "is_present", "updated_at"])
    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def worker_failed_job(request, job_id: int):
    auth_error = _authenticate_worker(request)
    if auth_error is not None:
        return auth_error

    payload = _request_json(request)
    job = get_object_or_404(TranscodeJob.objects.select_related("media_file"), pk=job_id)
    job.status = TranscodeJob.Status.FAILED
    job.error_message = str(payload.get("error", "")) if payload.get("error") is not None else ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    if job.media_file_id:
        job.media_file.stage = MediaFile.Stage.FAILED
        job.media_file.save(update_fields=["stage", "updated_at"])
    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def worker_job_output(request, job_id: int):
    auth_error = _authenticate_worker(request)
    if auth_error is not None:
        return auth_error

    get_object_or_404(TranscodeJob, pk=job_id)
    return HttpResponse(status=204)
