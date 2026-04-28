from django.tasks import task
import os


@task
def move_file_task(source, target):
    os.rename(source, target)
