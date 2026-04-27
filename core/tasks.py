from django.tasks import task
import shutil


@task
def move_file_task(source, target):
    shutil.move(source, target)
