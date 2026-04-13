from django.urls import path

from . import views, worker_api

urlpatterns = [
    path("", views.home, name="home"),
    path("queue/", views.queue, name="queue"),
    path("library/", views.library, name="library"),
    path("media/", views.media_inventory, name="media_inventory"),
    path("media/scan/", views.scan_library, name="scan_library"),
    path("api/worker/jobs/next", worker_api.worker_next_job, name="worker_next_job"),
    path("api/worker/jobs/<int:job_id>/input/", worker_api.worker_job_input, name="worker_job_input"),
    path("queue/<int:job_id>/status/<str:status>/", views.update_job_status, name="update_job_status"),
    path("queue/<int:job_id>/delete/", views.delete_job, name="delete_job"),
]
