from django.core.management.base import BaseCommand, CommandError

from core.library_sync import sync_media_library


class Command(BaseCommand):
    help = "Scan /Volumes/media, probe media files, and classify them in the database."

    def handle(self, *args, **options):
        try:
            stats = sync_media_library()
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {stats.scanned} files, created {stats.created}, updated {stats.updated}, marked missing {stats.missing}."
            )
        )
