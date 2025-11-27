import time
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import Job

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs a background worker for processing jobs'

    def handle(self, *args, **kwargs):
        self.stdout.write("Worker started. Waiting for tasks.")
        
        while True:
            job = self.lease_job()
            
            if job:
                self.process_job(job)
            else:
                time.sleep(2)

    def lease_job(self):
        with transaction.atomic():
            job = Job.objects.select_for_update().filter(status='PENDING').order_by('created_at').first()
            
            if job:
                job.status = 'RUNNING'
                job.save()
                self.stdout.write(f"[CLAIMED] Job {job.id}")
                return job
        return None

    def process_job(self, job):
        try:
            self.stdout.write(f"Executing task for {job.id}...")
            
            duration = job.payload.get('duration', 2)
            if job.payload.get('fail_simulation'):
                raise Exception("Simulated Task Failure")
            
            time.sleep(duration) 

            job.status = 'COMPLETED'
            job.log_output = "Task completed successfully."
            job.save()
            self.stdout.write(f"[SUCCESS] Job {job.id}")

        except Exception as e:
            self.stdout.write(f"[FAILURE] Job {job.id}: {e}")
            
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = 'PENDING'
                job.log_output = f"Retry #{job.retry_count} failed due to: {str(e)}"
            else:
                job.status = 'FAILED'
                job.log_output = f"Max retries reached. Error: {str(e)}"
            
            job.save()