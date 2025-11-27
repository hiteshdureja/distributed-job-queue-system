import json
import time
from django.shortcuts import render
from django.db.models import Count
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Job


def is_rate_limited(user_id):
    one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
    count = Job.objects.filter(user_id=user_id, created_at__gte=one_minute_ago).count()
    return count >= 10


def has_active_job_quota(user_id):
    count = Job.objects.filter(user_id=user_id, status__in=['PENDING', 'RUNNING']).count()
    return count >= 5


@csrf_exempt
def submit_job(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        user_id = data.get('user_id', 'anon')
        idem_key = data.get('idempotency_key')

        if idem_key:
            existing = Job.objects.filter(idempotency_key=idem_key).first()
            if existing:
                return JsonResponse({'job_id': existing.id, 'status': 'EXISTING_JOB'})

        if is_rate_limited(user_id):
            return JsonResponse({'error': 'Rate limit exceeded (10/min)'}, status=429)
        if has_active_job_quota(user_id):
            return JsonResponse({'error': 'Quota exceeded (Max 5 concurrent)'}, status=429)

        job = Job.objects.create(
            user_id=user_id,
            payload=data.get('payload', {}),
            idempotency_key=idem_key
        )
        return JsonResponse({'job_id': job.id, 'status': 'SUBMITTED'}, status=201)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    
@csrf_exempt
def requeue_job(request, job_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        job = Job.objects.get(id=job_id)
        
        if job.status not in ['FAILED', 'COMPLETED']:
            return JsonResponse({'error': f'Job must be FAILED or COMPLETED to manually {action}.'}, status=400)
        
        if action == 'REQUEUE':
            job.status = 'PENDING'
            job.retry_count = 0
            job.log_output = f"Manually re-queued by user at {timezone.now().strftime('%H:%M:%S')}"
            message = "Re-queued to PENDING."
            
        elif action == 'FORCE_SUCCESS':
            job.status = 'COMPLETED'
            job.log_output = f"Manually set to COMPLETED by user at {timezone.now().strftime('%H:%M:%S')}"
            message = "Manually set to COMPLETED."
            
        elif action == 'FORCE_FAIL':
            job.status = 'FAILED' 
            job.log_output = f"Manually marked as FAILED by user at {timezone.now().strftime('%H:%M:%S')}"
            message = "Manually marked as FAILED."
            
        else:
            return JsonResponse({'error': 'Invalid action specified.'}, status=400)

        job.save()
        
        return JsonResponse({'job_id': job.id, 'status': job.status, 'message': message}, status=200)

    except Job.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def job_status(request, job_id):
    try:
        job = Job.objects.get(id=job_id)
        return JsonResponse({
            'job_id': job.id,
            'status': job.status,
            'retries': job.retry_count,
            'result': job.log_output
        })
    except Job.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)


def dashboard_view(request):
    return render(request, 'dashboard.html')


def dashboard_api(request):
    """Returns JSON stats and paginated list for the frontend to poll"""
    page_number = request.GET.get('page', 1)
    page_size = 10
    stats = Job.objects.values('status').annotate(count=Count('status'))
    data = {s['status']: s['count'] for s in stats}
    all_jobs = Job.objects.all().order_by('-created_at')
    paginator = Paginator(all_jobs, page_size)
    page_obj = paginator.get_page(page_number)
    recent_jobs = list(page_obj.object_list.values(
        'id', 'status', 'retry_count', 'user_id', 'created_at', 'log_output'
    ))
    
    return JsonResponse({
        'counts': data,
        'jobs': recent_jobs,
        'pagination': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
    })