from django.core.management.base import BaseCommand, CommandError

from core.library_sync import process_pending_metadata


class Command(BaseCommand):
    help = "Run ffprobe against pending media files and store metadata in the database."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Process at most this many files.")

    def handle(self, *args, **options):
        try:
            stats = process_pending_metadata(limit=options["limit"])
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {stats.processed} files, ready {stats.ready}, failed {stats.failed}."
            )
        )
