import uuid
from django.db import models

class Job(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    user_id = models.CharField(max_length=50)
    
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    log_output = models.TextField(blank=True, default="") 

    class Meta:
        verbose_name = "Job Queue Item"
        verbose_name_plural = "Job Queue Items"

    def __str__(self):
        return f"Job: {self.id} | Status: {self.status}"