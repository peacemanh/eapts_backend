from django.urls import path
from .views import (
    LocationListCreate, LocationRetrieveUpdateDelete,
    LocationTagListCreate, LocationTagRetrieveUpdateDelete,
    LocationTagMapListCreate, LocationTagMapRetrieveUpdateDelete,
    location_children_list, location_descendants_list, root_locations_list,
    bulk_add_tags_to_location, bulk_remove_tags_from_location,
    location_address_upward,
)

app_name = 'locations'

urlpatterns = [
    # =========================================================================
    # LOCATION ENDPOINTS
    # =========================================================================
    
    # Core Location CRUD
    path("", LocationListCreate.as_view(), name="location-list-create"),
    path("<int:pk>/", LocationRetrieveUpdateDelete.as_view(), name="location-retrieve-update-destroy"),
    
    # Location Hierarchy Operations
    path("roots/", root_locations_list, name="root-locations"),
    path("<int:location_id>/children/", location_children_list, name="location-children"),
    path("<int:location_id>/descendants/", location_descendants_list, name="location-descendants"),
    
    # Location Tag Operations
    path("<int:location_id>/bulk-add-tags/", bulk_add_tags_to_location, name="bulk-add-tags"),
    path("<int:location_id>/bulk-remove-tags/", bulk_remove_tags_from_location, name="bulk-remove-tags"),
    
    # Location Address Operations
    path("<int:location_id>/address-upward/", location_address_upward, name="location-address-upward-id"),
    path("address-upward/uuid/<uuid:location_uuid>/", location_address_upward, name="location-address-upward-uuid"),
    
    # =========================================================================
    # LOCATION TAG ENDPOINTS
    # =========================================================================
    
    # Location Tag CRUD
    path("tags/", LocationTagListCreate.as_view(), name="location-tag-list-create"),
    path("tags/<int:pk>/", LocationTagRetrieveUpdateDelete.as_view(), name="location-tag-retrieve-update-destroy"),
    
    # =========================================================================
    # LOCATION TAG MAP ENDPOINTS  
    # =========================================================================
    
    # Location Tag Map CRUD
    path("tag-maps/", LocationTagMapListCreate.as_view(), name="location-tag-map-list-create"),
    path("tag-maps/<int:pk>/", LocationTagMapRetrieveUpdateDelete.as_view(), name="location-tag-map-retrieve-update-destroy"),
]