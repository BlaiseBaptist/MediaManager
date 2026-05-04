from django.contrib import messages
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from .library_sync import (
    LIBRARY_ROOT,
    media_stage_for_job_status,
    sync_radarr,
    sync_sonarr,
    update_file,
    ScanStats,
)
from .models import MediaFile, MediaSource, TranscodeJob, DataSource
import shutil

from pathlib import Path


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
    query = request.GET.copy()

    context = {
        "library_root": LIBRARY_ROOT,
        "media_files": files,
        "page_obj": files,
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
            "complete": MediaFile.objects.filter(
                stage=MediaFile.Stage.COMPLETE
            ).count(),
            "failed": MediaFile.objects.filter(stage=MediaFile.Stage.FAILED).count(),
            "missing": MediaFile.objects.filter(stage=MediaFile.Stage.MISSING).count(),
        },
        "active_stage": stage or "",
    }
    return render(request, "core/media_inventory.html", context)


@require_POST
def rescan_libary(request):
    stats = ScanStats()
    for source in DataSource.objects.all():
        if "radarr" in source.name.lower():
            stats += sync_radarr(source)
        if "sonarr" in source.name.lower():
            stats += sync_sonarr(source)
    stats.missing += MediaFile.objects.filter(
        data_source=DataSource.objects.get(name="Unknown")
    ).update(stage=MediaFile.Stage.MISSING)
    messages.success(
        request,
        f"Scan complete: {stats.scanned} files scanned, {stats.complete} complete, {
            stats.needs_processing
        } need processing, {stats.missing} marked missing.",
    )
    return redirect("media_inventory")


@require_POST
def reset_failed_jobs(request):
    TranscodeJob.objects.filter(status=TranscodeJob.Status.FAILED).update(
        status=TranscodeJob.Status.PENDING
    )
    return _queue_redirect(request)


@require_POST
def delete_all_jobs(request):
    TranscodeJob.objects.all().delete()
    return _queue_redirect(request)


@require_POST
def delete_missing_files(request):
    rescan_libary(request)
    missing_files = MediaFile.objects.filter(stage=MediaFile.Stage.MISSING)
    stats = ScanStats()
    for file in missing_files:
        try:
            shutil.move(file.absolute_path, "/media/spare_files/" + file.relative_path)
            stats.complete += 1
        except Exception:
            stats.failed += 1
        finally:
            file.delete()
    return redirect("media_inventory")


@require_POST
@csrf_exempt
def arr_webhook(request):
    try:
        data = json.loads(request.body)
        event_type = data.get("eventType")
        if event_type == "Test":
            return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    try:
        if event_type == "EpisodeFileDelete":
            return _sonarr_delete_data(data)
        if event_type == "MovieFileDelete":
            return _radarr_delete_data(data)
        if event_type == "Download":
            return _add_data(data)
        if event_type == "Rename":
            return _rename_data(data)
    except Exception as e:
        print(data)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "error", "message": "todo!"}, status=503)


def _sonarr_delete_data(data):
    file = data.get("episodeFile")
    return _delete_file_record(file)


def _radarr_delete_data(data):
    file = data.get("movieFile")
    return _delete_file_record(file)


def _delete_file_record(file):
    deleted_count, delete_info = MediaFile.objects.filter(
        absolute_path=file.get("path")
    ).delete()
    if deleted_count == 0:
        return JsonResponse(
            {
                "status": "delete",
                "message": "could not find any matching files, assuming ok",
            },
            status=200,
        )
    return JsonResponse({"status": "delete", "message": str(delete_info)}, status=200)


def _rename_data(data):
    data_source = get_object_or_404(DataSource, name=data.get("instanceName"))
    stats = ScanStats()
    if data_source.name == "Sonarr":
        renamed_files = data.get("renamedEpisodeFiles")
    if data_source.name == "Radarr":
        renamed_files = data.get("renamedMovieFiles")
    if renamed_files is None:
        return JsonResponse(
            {"status": "error", "message": "unsupported format"}, status=400
        )
    for file in renamed_files:
        old_path = file.get("previousRelativePath")
        renamed = get_object_or_404(MediaFile, relative_path=old_path)
        new_path = Path(file.get("path"))
        stats += update_file(new_path, data_source, renamed)
    return JsonResponse({"status": "rename", "message": str(stats)}, status=200)


def _add_data(data):
    data_source = get_object_or_404(DataSource, name=data.get("instanceName"))
    stats = ScanStats()
    if data_source.name == "Sonarr":
        added_files = data.get("episodeFiles")
    if data_source.name == "Radarr":
        added_files = [data.get("movieFile")]
        # TODO: add radarr support
        return JsonResponse({"status": "error", "message": "todo!"}, status=503)
    if added_files is None:
        return JsonResponse(
            {"status": "error", "message": "unknown service or bad request"}, status=400
        )
    for file in added_files:
        new_path = Path(file.get("path"))
        stats += update_file(new_path, data_source)
    return JsonResponse({"status": "add", "message": str(stats)}, status=200)


def queue(request):
    jobs = TranscodeJob.objects.select_related(
        "media_file__source", "media_file", "media_file__metadata_record"
    ).all()
    source_filter = request.GET.get("source", "").strip()
    status_filter = request.GET.get("status", "").strip()
    data_filter = request.GET.get("data", "").strip()
    name_filter = request.GET.get("name", "").strip()
    if status_filter and status_filter in TranscodeJob.Status.values:
        jobs = jobs.filter(status=status_filter)
    if source_filter:
        jobs = jobs.filter(media_file__source=source_filter)
    if data_filter:
        jobs = jobs.filter(media_file__data_source=data_filter)
    if name_filter:
        jobs = jobs.filter(media_file__file_name__icontains=name_filter)
    query = request.GET.copy()
    counts = TranscodeJob.objects.values("status").annotate(total=Count("id"))
    status_counts = {entry["status"]: entry["total"] for entry in counts}
    context = {
        "jobs": jobs,
        "status_counts": status_counts,
        "filters": {
            "status": status_filter,
            "source": source_filter,
            "data": data_filter,
        },
        "query_string": query.urlencode(),
        "sources": MediaSource.objects.order_by("name"),
        "data_sources": DataSource.objects.order_by("name"),
        "pending_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.PENDING),
        "running_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.RUNNING),
        "complete_jobs": TranscodeJob.objects.filter(
            status=TranscodeJob.Status.COMPLETE
        ),
        "failed_jobs": TranscodeJob.objects.filter(status=TranscodeJob.Status.FAILED),
    }
    return render(request, "core/queue.html", context)


@require_POST
def update_job_status(request, job_id, status):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if status not in TranscodeJob.Status.values:
        return _queue_redirect(request)
    job.status = status
    if job.media_file_id:
        job.media_file.stage = media_stage_for_job_status(status)
        job.media_file.is_present = True
        job.media_file.save(update_fields=["stage", "is_present", "updated_at"])
    if status != TranscodeJob.Status.FAILED:
        job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    return _queue_redirect(request)


@require_POST
def requeue_job(request, job_id):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    job.status = TranscodeJob.Status.PENDING
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    if job.media_file_id:
        job.media_file.stage = media_stage_for_job_status(TranscodeJob.Status.PENDING)
        job.media_file.is_present = True
        job.media_file.save(update_fields=["stage", "is_present", "updated_at"])
    return _queue_redirect(request)


@require_POST
def delete_job(request, job_id):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    job.delete()
    return _queue_redirect(request)
