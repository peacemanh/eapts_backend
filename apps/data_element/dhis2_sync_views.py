from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
import logging

from .services.dhis2_sync_service import DHIS2SyncService

logger = logging.getLogger(__name__)


class DHIS2SyncView(APIView):
    """
    API View for syncing with DHIS2
    """
    permission_classes = [IsAuthenticated]
    
    @method_decorator(never_cache)
    def get(self, request, format=None):
        """
        Get sync status and statistics
        """
        try:
            service = DHIS2SyncService()
            
            # Count existing DHIS2 mappings
            from .models import DataElementSourceMapping, MappingSource
            
            mapping_source_id = getattr(settings, 'DHIS2_MAPPING_SOURCE', 2)
            mapping_source = MappingSource.objects.get(id=mapping_source_id)
            
            total_elements = DataElementSourceMapping.objects.filter(
                source=mapping_source
            ).count()
            
            # Separate counts for data elements and indicators based on description
            data_elements_count = DataElementSourceMapping.objects.filter(
                source=mapping_source,
                description__icontains='DHIS2 data_element'
            ).count()
            
            indicators_count = DataElementSourceMapping.objects.filter(
                source=mapping_source,
                description__icontains='DHIS2 indicator'
            ).count()
            
            return Response({
                'status': 'ready',
                'config': {
                    'base_url': getattr(settings, 'DHIS2_BASE_URL', ''),
                    'username': getattr(settings, 'DHIS2_USERNAME', ''),
                    'mapping_source_id': mapping_source_id,
                    'parent_data_element_id': getattr(settings, 'DHIS2_PARENT_DATA_ELEMENT', 167),
                    'parent_indicator_id': getattr(settings, 'DHIS2_PARENT_INDICATOR', 168),
                },
                'statistics': {
                    'total_synced': total_elements,
                    'data_elements': data_elements_count,
                    'indicators': indicators_count,
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting sync status: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @method_decorator(never_cache)
    def post(self, request, format=None):
        """
        Trigger a sync operation
        """
        try:
            sync_type = request.data.get('type', 'both')
            dry_run = request.data.get('dry_run', False)
            page_size = request.data.get('page_size', 100)
            
            if sync_type not in ['data-elements', 'indicators', 'both']:
                return Response(
                    {'error': 'Invalid sync type. Must be: data-elements, indicators, or both'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            service = DHIS2SyncService()
            results = {}
            
            if sync_type in ['data-elements', 'both']:
                results['data_elements'] = service.sync_data_elements(
                    page_size=page_size,
                    dry_run=dry_run
                )
            
            if sync_type in ['indicators', 'both']:
                results['indicators'] = service.sync_indicators(
                    page_size=page_size,
                    dry_run=dry_run
                )
            
            return Response({
                'success': True,
                'dry_run': dry_run,
                'results': results
            })
            
        except Exception as e:
            logger.error(f"Error during sync: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DHIS2TestConnectionView(APIView):
    """
    Test connection to DHIS2 API
    """
    permission_classes = [IsAuthenticated]
    
    @method_decorator(never_cache)
    def get(self, request, format=None):
        """
        Test connection to DHIS2
        """
        try:
            import requests
            from django.conf import settings
            
            base_url = getattr(settings, 'DHIS2_BASE_URL', '')
            username = getattr(settings, 'DHIS2_USERNAME', '')
            password = getattr(settings, 'DHIS2_PASSWORD', '')
            
            if not all([base_url, username, password]):
                return Response({
                    'connected': False,
                    'error': 'DHIS2 configuration is incomplete'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Test connection
            session = requests.Session()
            session.auth = (username, password)
            
            # Try to access system info
            response = session.get(f"{base_url}/system/info")
            
            if response.status_code == 200:
                data = response.json()
                return Response({
                    'connected': True,
                    'system': {
                        'version': data.get('version'),
                        'revision': data.get('revision'),
                        'date': data.get('date'),
                        'systemName': data.get('systemName'),
                    }
                })
            else:
                return Response({
                    'connected': False,
                    'status_code': response.status_code,
                    'error': response.text
                }, status=status.HTTP_502_BAD_GATEWAY)
                
        except requests.exceptions.ConnectionError:
            return Response({
                'connected': False,
                'error': 'Connection failed. Check network and URL.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response({
                'connected': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)