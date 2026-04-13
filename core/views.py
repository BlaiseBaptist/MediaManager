from django.shortcuts import render

from .models import MediaSource, TranscodeJob


def home(request):
    context = {
        "source_count": MediaSource.objects.count(),
        "job_count": TranscodeJob.objects.count(),
        "pending_job_count": TranscodeJob.objects.filter(status=TranscodeJob.Status.PENDING).count(),
    }
    return render(request, "core/home.html", context)

