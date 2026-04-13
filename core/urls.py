from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("queue/", views.queue, name="queue"),
    path("library/", views.library, name="library"),
    path("queue/<int:job_id>/status/<str:status>/", views.update_job_status, name="update_job_status"),
    path("queue/<int:job_id>/delete/", views.delete_job, name="delete_job"),
]
