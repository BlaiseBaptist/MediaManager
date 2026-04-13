from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TranscodeJobForm
from .library_sync import LIBRARY_ROOT, media_stage_for_job_status, sync_media_library
from .models import MediaFile, MediaSource, TranscodeJob


def home(request):
    context = {
        "source_count": MediaSource.objects.count(),
        "media_file_count": MediaFile.objects.count(),
        "job_count": TranscodeJob.objects.count(),
        "pending_job_count": TranscodeJob.objects.filter(status=TranscodeJob.Status.PENDING).count(),
        "metadata_ready_count": MediaFile.objects.filter(stage=MediaFile.Stage.METADATA_READY).count(),
        "metadata_pending_count": MediaFile.objects.filter(stage=MediaFile.Stage.METADATA_PENDING).count(),
        "ready_media_count": MediaFile.objects.filter(stage=MediaFile.Stage.READY).count(),
        "transcode_pending_count": MediaFile.objects.filter(stage=MediaFile.Stage.TRANSCODE_PENDING).count(),
    }
    return render(request, "core/home.html", context)


def library(request):
    return redirect("media_inventory")


def media_inventory(request):
    stage = request.GET.get("stage")
    files = MediaFile.objects.select_related("source", "metadata_record").all()
    if stage and stage in MediaFile.Stage.values:
        files = files.filter(stage=stage)

    context = {
        "library_root": LIBRARY_ROOT,
        "media_files": files,
        "counts": {
            "total": MediaFile.objects.count(),
            "discovered": MediaFile.objects.filter(stage=MediaFile.Stage.DISCOVERED).count(),
            "metadata_ready": MediaFile.objects.filter(stage=MediaFile.Stage.METADATA_READY).count(),
            "transcode_pending": MediaFile.objects.filter(stage=MediaFile.Stage.TRANSCODE_PENDING).count(),
            "transcoding": MediaFile.objects.filter(stage=MediaFile.Stage.TRANSCODING).count(),
            "ready": MediaFile.objects.filter(stage=MediaFile.Stage.READY).count(),
            "failed": MediaFile.objects.filter(stage=MediaFile.Stage.FAILED).count(),
            "missing": MediaFile.objects.filter(stage=MediaFile.Stage.MISSING).count(),
        },
        "active_stage": stage or "",
    }
    return render(request, "core/media_inventory.html", context)


def scan_library(request):
    if request.method == "POST":
        sync_media_library()
    return redirect("media_inventory")


def queue(request):
    if request.method == "POST":
        form = TranscodeJobForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("queue")
    else:
        form = TranscodeJobForm()

    jobs = TranscodeJob.objects.select_related("source", "media_file", "media_file__metadata_record").all()
    counts = TranscodeJob.objects.values("status").annotate(total=Count("id"))
    status_counts = {entry["status"]: entry["total"] for entry in counts}

    context = {
        "form": form,
        "jobs": jobs,
        "status_counts": status_counts,
        "pending_jobs": jobs.filter(status=TranscodeJob.Status.PENDING),
        "running_jobs": jobs.filter(status=TranscodeJob.Status.RUNNING),
        "complete_jobs": jobs.filter(status=TranscodeJob.Status.COMPLETE),
        "failed_jobs": jobs.filter(status=TranscodeJob.Status.FAILED),
    }
    return render(request, "core/queue.html", context)


def update_job_status(request, job_id, status):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if request.method != "POST":
        return redirect("queue")
    if status not in TranscodeJob.Status.values:
        return redirect("queue")
    job.status = status
    if job.media_file_id:
        job.media_file.stage = media_stage_for_job_status(status)
        job.media_file.is_present = True
        job.media_file.save(update_fields=["stage", "is_present", "updated_at"])
    if status != TranscodeJob.Status.FAILED:
        job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    return redirect("queue")


def delete_job(request, job_id):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if request.method == "POST":
        job.delete()
    return redirect("queue")
