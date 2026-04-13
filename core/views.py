from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TranscodeJobForm
from .models import MediaSource, TranscodeJob


def home(request):
    context = {
        "source_count": MediaSource.objects.count(),
        "job_count": TranscodeJob.objects.count(),
        "pending_job_count": TranscodeJob.objects.filter(status=TranscodeJob.Status.PENDING).count(),
    }
    return render(request, "core/home.html", context)


def queue(request):
    if request.method == "POST":
        form = TranscodeJobForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("queue")
    else:
        form = TranscodeJobForm()

    jobs = TranscodeJob.objects.select_related("source").all()
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
    if status != TranscodeJob.Status.FAILED:
        job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])
    return redirect("queue")


def delete_job(request, job_id):
    job = get_object_or_404(TranscodeJob, pk=job_id)
    if request.method == "POST":
        job.delete()
    return redirect("queue")
