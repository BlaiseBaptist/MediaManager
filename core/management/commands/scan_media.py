from django.core.management.base import BaseCommand

from core.library_sync import sync_media_library


class Command(BaseCommand):
    help = "Scan /Volumes/media and sync media files into the database."

    def handle(self, *args, **options):
        stats = sync_media_library()
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {stats.scanned} files, created {stats.created}, updated {stats.updated}, marked missing {stats.missing}."
            )
        )
