# apps/data_element/services/dhis2_sync_service.py
import requests
import base64
import time
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.data_element.models import (
    DataElement, 
    DataType, 
    MappingSource, 
    DataElementClass,
    DataElementSourceMapping,
    DataElementValueSet
)
import logging
import json
from django.core.cache import cache

logger = logging.getLogger(__name__)


class DHIS2SyncService:
    """Service for syncing with DHIS2 API with progress tracking"""
    
    def __init__(self, job_id=None):
        self.config = {
            'base_url': getattr(settings, 'DHIS2_BASE_URL', 'https://dhisanalytics.moh.gov.et/api/40'),
            'username': getattr(settings, 'DHIS2_USERNAME', 'admin'),
            'password': getattr(settings, 'DHIS2_PASSWORD', 'district'),
            'default_datatype': getattr(settings, 'DHIS2_DEFAULT_DATATYPE', 1),
            'mapping_source': getattr(settings, 'DHIS2_MAPPING_SOURCE', 2),
            'data_element_class': getattr(settings, 'DHIS2_DATA_ELEMENT_CLASS', 1),
            'parent_data_element': getattr(settings, 'DHIS2_PARENT_DATA_ELEMENT', 167),
            'parent_indicator': getattr(settings, 'DHIS2_PARENT_INDICATOR', 168),
        }
        
        self.job_id = job_id or f"sync_{int(time.time())}"
        self.progress_key = f"dhis2_sync_progress_{self.job_id}"
        self.active_jobs_key = 'dhis2_active_sync_jobs'
        
    def add_to_active_jobs(self):
        """Add job to active jobs list"""
        active_jobs = cache.get(self.active_jobs_key, [])
        if self.job_id not in active_jobs:
            active_jobs.append(self.job_id)
            # Keep only last 20 jobs
            if len(active_jobs) > 20:
                active_jobs = active_jobs[-20:]
            cache.set(self.active_jobs_key, active_jobs, 86400)  # 24 hours
    
    def remove_from_active_jobs(self):
        """Remove job from active jobs list"""
        active_jobs = cache.get(self.active_jobs_key, [])
        if self.job_id in active_jobs:
            active_jobs.remove(self.job_id)
            cache.set(self.active_jobs_key, active_jobs, 86400)
    
    def update_progress(self, current, total, stage, message=None, details=None):
        """Update sync progress in cache"""
        progress_data = {
            'job_id': self.job_id,
            'stage': stage,
            'current': current,
            'total': total,
            'percentage': (current / total * 100) if total > 0 else 0,
            'message': message,
            'details': details,
            'timestamp': timezone.now().isoformat(),
            'status': 'running' if current < total else 'completed',
        }
        
        # Store in cache for 1 hour
        cache.set(self.progress_key, progress_data, 3600)
        
        # Add to active jobs list
        self.add_to_active_jobs()
        
        return progress_data
    
    def get_progress(self):
        """Get current progress"""
        return cache.get(self.progress_key, {
            'job_id': self.job_id,
            'stage': 'not_started',
            'current': 0,
            'total': 0,
            'percentage': 0,
            'message': 'Sync not started',
            'status': 'not_started',
            'timestamp': timezone.now().isoformat(),
        })
    
    def clear_progress(self):
        """Clear progress data"""
        cache.delete(self.progress_key)
        self.remove_from_active_jobs()    
    def initialize_models(self):
        """Initialize and verify required models"""
        try:
            self.default_datatype = DataType.objects.get(id=self.config['default_datatype'])
            self.mapping_source = MappingSource.objects.get(id=self.config['mapping_source'])
            self.data_element_class = DataElementClass.objects.get(id=self.config['data_element_class'])
            self.parent_data_element = DataElement.objects.get(id=self.config['parent_data_element'])
            self.parent_indicator = DataElement.objects.get(id=self.config['parent_indicator'])
        except Exception as e:
            logger.error(f"Failed to initialize models: {str(e)}")
            raise
    
    # ... rest of the existing methods ...
    
    def sync_data_elements(self, page_size=100, dry_run=False):
        """Sync data elements from DHIS2 with progress tracking"""
        try:
            items = self.fetch_dhis2_data('dataElements', page_size)
            
            # Update progress - fetching stage
            self.update_progress(
                current=0,
                total=len(items),
                stage='fetching',
                message=f"Fetched {len(items)} data elements",
                details={'type': 'data_elements', 'count': len(items)}
            )
            
            return self.process_items_with_progress(items, self.parent_data_element, 'data_element', dry_run)
        except Exception as e:
            logger.error(f"Error syncing data elements: {str(e)}")
            raise
    
    def process_items_with_progress(self, items, parent_element, item_type, dry_run=False):
        """Process items with real-time progress updates"""
        stats = {
            'total': len(items),
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [],
            'start_time': timezone.now().isoformat(),
        }
        
        # Update progress - processing stage
        self.update_progress(
            current=0,
            total=stats['total'],
            stage='processing',
            message=f"Processing {stats['total']} {item_type}s",
            details={'type': item_type, 'processed': 0, 'total': stats['total']}
        )
        
        batch_size = 50
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(items) - 1) // batch_size + 1
            
            for item in batch:
                try:
                    result = self.process_single_item(item, parent_element, item_type, dry_run)
                    stats[result] += 1
                except Exception as e:
                    stats['skipped'] += 1
                    stats['errors'].append({
                        'item_id': item.get('id'),
                        'error': str(e)
                    })
            
            # Update progress after each batch
            processed = stats['created'] + stats['updated'] + stats['skipped']
            self.update_progress(
                current=processed,
                total=stats['total'],
                stage='processing',
                message=f"Processing batch {batch_num}/{total_batches}",
                details={
                    'type': item_type,
                    'processed': processed,
                    'total': stats['total'],
                    'batch': batch_num,
                    'total_batches': total_batches,
                    'stats': {
                        'created': stats['created'],
                        'updated': stats['updated'],
                        'skipped': stats['skipped'],
                    }
                }
            )
        
        stats['end_time'] = timezone.now().isoformat()
        return stats