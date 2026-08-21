from django.core.management.base import BaseCommand

from cutout.service.uws.service import JobService


class Command(BaseCommand):
    help = "Delete expired cutout jobs (any owner) and unlink safe result/output files."

    def handle(self, *args, **options):
        deleted = JobService().cleanup_expired_jobs()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired job(s)."))
