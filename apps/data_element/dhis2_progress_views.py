# apps/data_element/views/dhis2_progress_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache
from django.conf import settings
import time


class DHIS2SyncProgressView(APIView):
    """
    API View for getting DHIS2 sync progress
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        """
        Get sync progress by job_id or latest
        """
        job_id = request.query_params.get('job_id')
        
        if job_id:
            # Get specific job progress
            progress_key = f"dhis2_sync_progress_{job_id}"
            progress_data = cache.get(progress_key)
        else:
            # Get latest job progress
            progress_data = None
            # Try to find any progress key
            # Note: In production, use Redis SCAN or maintain a list of active jobs
            # For now, we'll check a few possible keys
            for i in range(10):  # Check last 10 possible job ids
                check_key = f"dhis2_sync_progress_{int(time.time()) - i}"
                if cache.has_key(check_key):
                    progress_data = cache.get(check_key)
                    break
        
        if progress_data:
            return Response({
                'success': True,
                'progress': progress_data
            })
        else:
            return Response({
                'success': False,
                'error': 'No sync job found',
                'progress': {
                    'job_id': job_id or 'unknown',
                    'stage': 'not_started',
                    'current': 0,
                    'total': 0,
                    'percentage': 0,
                    'message': 'No active sync job found',
                    'status': 'not_started',
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }
            }, status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request, format=None):
        """
        Clear sync progress
        """
        job_id = request.query_params.get('job_id')
        
        if job_id:
            progress_key = f"dhis2_sync_progress_{job_id}"
            cache.delete(progress_key)
            return Response({
                'success': True,
                'message': f'Progress for job {job_id} cleared'
            })
        else:
            # For simplicity, we'll just clear the specific pattern
            # In production, you might want to be more selective
            return Response({
                'success': False,
                'error': 'Job ID required to clear progress'
            }, status=status.HTTP_400_BAD_REQUEST)


class DHIS2SyncJobsView(APIView):
    """
    API View for listing active DHIS2 sync jobs
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        """
        List all active sync jobs
        """
        # In a real implementation with Redis, you would use SCAN
        # For Django's cache backend, we need a workaround
        
        jobs = []
        
        # Simple implementation: store active jobs in a list
        active_jobs_key = 'dhis2_active_sync_jobs'
        active_jobs = cache.get(active_jobs_key, [])
        
        for job_id in active_jobs[:10]:  # Limit to last 10 jobs
            progress_key = f"dhis2_sync_progress_{job_id}"
            progress_data = cache.get(progress_key)
            
            if progress_data:
                jobs.append({
                    'job_id': job_id,
                    'progress': progress_data
                })
            else:
                # Remove stale job from list
                active_jobs.remove(job_id)
        
        # Update the cache with cleaned list
        cache.set(active_jobs_key, active_jobs, 3600)
        
        return Response({
            'success': True,
            'jobs': jobs,
            'total': len(jobs)
        })