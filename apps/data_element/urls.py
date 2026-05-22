from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DataElementClassViewSet,
    DataTypeViewSet,
    MappingSourceViewSet,
    DataElementViewSet,
    DataElementValueSetViewSet,
    DataElementSetMemberViewSet,
    DataElementSourceMappingViewSet,
    CSVImportViewSet,
)
from .dhis2_sync_views import DHIS2SyncView, DHIS2TestConnectionView
from .dhis2_progress_views import DHIS2SyncProgressView, DHIS2SyncJobsView

# Import the new proxy views
from .data_element_proxy import DHIS2ProxyView, DHIS2TestConnectionView as ProxyTestConnectionView

router = DefaultRouter()
router.register(r'data-element-classes', DataElementClassViewSet)
router.register(r'data-types', DataTypeViewSet)
router.register(r'mapping-sources', MappingSourceViewSet)
router.register(r'data-elements', DataElementViewSet)
router.register(r'data-element-value-sets', DataElementValueSetViewSet)
router.register(r'data-element-set-members', DataElementSetMemberViewSet)
router.register(r'data-element-source-mappings', DataElementSourceMappingViewSet)
router.register(r'csv-import', CSVImportViewSet, basename='csv-import')

urlpatterns = [
    path('', include(router.urls)),
    
    # DHIS2 Sync endpoints (existing)
    path('dhis2/sync/', DHIS2SyncView.as_view(), name='dhis2-sync'),
    path('dhis2/test-connection/', DHIS2TestConnectionView.as_view(), name='dhis2-test-connection'),
    path('dhis2/sync/progress/', DHIS2SyncProgressView.as_view(), name='dhis2-sync-progress'),
    path('dhis2/sync/jobs/', DHIS2SyncJobsView.as_view(), name='dhis2-sync-jobs'),
    
    # Simple proxy for DHIS2 (for frontend to use instead of direct DHIS2 calls)
    path('dhis2-proxy/<path:path>/', DHIS2ProxyView.as_view(), name='dhis2-proxy'),
    path('dhis2-proxy/test-connection/', ProxyTestConnectionView.as_view(), name='dhis2-proxy-test'),
]