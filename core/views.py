from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .library_sync import (
    LIBRARY_ROOT,
    media_stage_for_job_status,
    sync_media_library,
)
from .models import MediaFile, MediaSource, TranscodeJob


def _queue_redirect(request):
    return redirect(request.POST.get("next") or reverse("queue"))


def home(request):
    context = {
        "source_count": MediaSource.objects.count(),
        "media_file_count": MediaFile.objects.count(),
        "job_count": TranscodeJob.objects.count(),
        "pending_job_count": TranscodeJob.objects.filter(
            status=TranscodeJob.Status.PENDING
        ).count(),
        "complete_media_count": MediaFile.objects.filter(
            stage=MediaFile.Stage.COMPLETE
        ).count(),
        "transcode_pending_count": MediaFile.objects.filter(
            stage=MediaFile.Stage.TRANSCODE_PENDING
        ).count(),
    }
    return render(request, "core/home.html", context)


def media_inventory(request):
    stage = request.GET.get("stage")
    files = MediaFile.objects.select_related("source", "metadata_record").all()
    if stage and stage in MediaFile.Stage.values:
        files = files.filter(stage=stage)
    paginator = Paginator(files, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)

    context = {
        "library_root": LIBRARY_ROOT,
        "media_files": page_obj,
        "page_obj": page_obj,
        "query_string": query.urlencode(),
        "counts": {
            "total": MediaFile.objects.count(),
            "discovered": MediaFile.objects.filter(
                stage=MediaFile.Stage.DISCOVERED
            ).count(),
            "transcode_pending": MediaFile.objects.filter(
                stage=MediaFile.Stage.TRANSCODE_PENDING
            ).count(),
            "transcoding": MediaFile.objects.filter(
                stage=MediaFile.Stage.TRANSCODING
            ).count(),
            "complete": MediaFile.objects.filter(stage=MediaFile.Stage.COMPLETE).count(),
            "failed": MediaFile.objects.filter(stage=MediaFile.Stage.FAILED).count(),
            "missing": MediaFile.objects.filter(stage=MediaFile.Stage.MISSING).count(),
        },
        "active_stage": stage or "",
    }
    return render(request, "core/media_inventory.html", context)


def scan_library(request):
    if request.method == "POST":
        try:
            stats = sync_media_library()
        except FileNotFoundError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Scan complete: {stats.scanned} files scanned, {stats.complete} complete, {
                    stats.needs_processing} need processing, {stats.missing} marked missing.",
            )
    return redirect("media_inventory")


def reset_failed_jobs(request):
    if request.method == "POST":
        TranscodeJob.objects.filter(status=TranscodeJob.Status.FAILED).update(
            status=TranscodeJob.Status.PENDING)
    return redirect("queue")


def delete_all_jobs(request):
    if request.method == "POST":
        TranscodeJob.objects.all().delete()
    return scan_library(request)


def delete_missing_files(request):
    if request.method == "POST":
        MediaFile.objects.filter(stage=MediaFile.Stage.MISSING).delete()
        MediaFile.objects.filter(stage=MediaFile.Stage.FAILED).delete()
    return scan_library(request)


def queue(request):
    jobs = TranscodeJob.objects.select_related(
        "source", "media_file", "media_file__metadata_record"
    ).all()
    status_filter = request.GET.get("status", "").strip()
    source_filter = request.GET.get("source", "").strip()
    name_filter = request.GET.get("name", "").strip()
    if status_filter and status_filter in TranscodeJob.Status.values:
        jobs = jobs.filter(status=status_filter)
    if source_filter:
        jobs = jobs.filter(source_id=source_filter)
    if name_filter:
        jobs = jobs.filter(media_file__file_name__icontains=name_filter)
    query = request.GET.copy()
    query.pop("page", None)
    counts = TranscodeJob.objects.values("status").annotate(total=Count("id"))
    status_counts = {entry["status"]: entry["total"] for entry in counts}

    context = {
        "jobs": jobs,
        "status_counts": status_counts,
        "filters": {
            "status": status_filter,
            "source": source_filter,
        },
        "query_string": query.urlencode(),
        "sources": MediaSource.objects.order_by("name"),
        "pending_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.PENDING),
        "running_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.RUNNING),
        "complete_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.COMPLETE),
        "failed_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.FAILED),
    }
    return render(request, "core/queue.html", context)


def update_job_status(request, job_id, status):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if request.method != "POST":
        return _queue_redirect(request)
    if status not in TranscodeJob.Status.values:
        return _queue_redirect(request)
    job.status = status
    if job.media_file_id:
        job.media_file.stage = media_stage_for_job_status(status)
        job.media_file.is_present = True
        job.media_file.save(
            update_fields=["stage", "is_present", "updated_at"])
    if status != TranscodeJob.Status.FAILED:
        job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    return _queue_redirect(request)


def requeue_job(request, job_id):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if request.method != "POST":
        return _queue_redirect(request)

    job.status = TranscodeJob.Status.PENDING
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    if job.media_file_id:
        job.media_file.stage = media_stage_for_job_status(
            TranscodeJob.Status.PENDING)
        job.media_file.is_present = True
        job.media_file.save(
            update_fields=["stage", "is_present", "updated_at"])
    return _queue_redirect(request)


def delete_job(request, job_id):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if request.method == "POST":
        job.delete()
    return _queue_redirect(request)
