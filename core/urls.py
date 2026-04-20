from django.urls import path

from . import views, worker_api

urlpatterns = [
    path("", views.home, name="home"),
    path("queue/", views.queue, name="queue"),
    path("media/", views.media_inventory, name="media_inventory"),
    path("media/scan/", views.scan_library, name="scan_library"),
    path("api/worker/jobs/next", worker_api.worker_next_job, name="worker_next_job"),
    path(
        "api/media/jobs/<int:job_id>/input",
        worker_api.worker_job_input,
        name="worker_job_input",
    ),
    path(
        "api/worker/jobs/<int:job_id>/input",
        worker_api.worker_job_input,
        name="worker_job_input_legacy",
    ),
    path(
        "api/worker/jobs/<int:job_id>/complete",
        worker_api.worker_complete_job,
        name="worker_complete_job",
    ),
    path(
        "api/worker/jobs/<int:job_id>/failed",
        worker_api.worker_failed_job,
        name="worker_failed_job",
    ),
    path(
        "queue/<int:job_id>/status/<str:status>/",
        views.update_job_status,
        name="update_job_status",
    ),
    path("reset-failed/", views.reset_failed_jobs, name="reset_failed_jobs"),
    path("delete-jobs/", views.delete_all_jobs, name="delete_all_jobs"),
    path("delete-missing/", views.delete_missing_files, name="delete_missing_files"),
    path("queue/<int:job_id>/requeue/", views.requeue_job, name="requeue_job"),
    path("queue/<int:job_id>/delete/", views.delete_job, name="delete_job"),
]
