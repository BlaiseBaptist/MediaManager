from pathlib import Path
from datetime import datetime

from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TranscodeJobForm
from .models import MediaSource, TranscodeJob

LIBRARY_ROOT = Path("/Volumes/media").resolve()


def _safe_library_path(relative_path: str | None) -> Path:
    candidate = (LIBRARY_ROOT / (relative_path or "")).resolve()
    if candidate == LIBRARY_ROOT or LIBRARY_ROOT in candidate.parents:
        return candidate
    return LIBRARY_ROOT


def _format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{num_bytes} B"


def home(request):
    context = {
        "source_count": MediaSource.objects.count(),
        "job_count": TranscodeJob.objects.count(),
        "pending_job_count": TranscodeJob.objects.filter(status=TranscodeJob.Status.PENDING).count(),
    }
    return render(request, "core/home.html", context)


def library(request):
    relative_path = request.GET.get("path", "")
    current_path = _safe_library_path(relative_path)

    entries = []
    if current_path.exists():
        for item in sorted(current_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            stat = item.stat()
            entries.append(
                {
                    "name": item.name,
                    "path": str(item.relative_to(LIBRARY_ROOT)),
                    "is_dir": item.is_dir(),
                    "size": _format_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                }
            )

    parent_relative = None
    if current_path != LIBRARY_ROOT:
        parent_relative = str(current_path.parent.relative_to(LIBRARY_ROOT))

    context = {
        "library_root": LIBRARY_ROOT,
        "current_path": current_path,
        "current_relative": "" if current_path == LIBRARY_ROOT else str(current_path.relative_to(LIBRARY_ROOT)),
        "parent_relative": parent_relative,
        "entries": entries,
        "path_exists": current_path.exists(),
    }
    return render(request, "core/library.html", context)


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
