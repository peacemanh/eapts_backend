# apps/locations/views.py
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, CharFilter

from django.shortcuts import get_object_or_404
from django.db import transaction, DatabaseError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import Location, LocationTag, LocationTagMap
from .serializers import (
    LocationSerializer,
    LocationListSerializer,
    LocationTagSerializer,
    LocationTagMapSerializer
)
from apps.address.models import AddressEntry
from apps.address.serializers import AddressEntryParentChainSerializer


class BaseAPIView:
    """Base view class with common functionality."""
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def handle_exception(self, exc):
        """Handle exceptions and return consistent error responses."""
        if isinstance(exc, (ValidationError,)):
            return Response(
                {"error": _("Validation error"), "details": exc.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif isinstance(exc, DatabaseError):
            return Response(
                {"error": _("Database error occurred")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        elif isinstance(exc, NotFound):
            return Response(
                {"error": _("Resource not found")},
                status=status.HTTP_404_NOT_FOUND
            )
        return super().handle_exception(exc)


# --------------------
# Custom Filtersets for Schema Generation
# --------------------
class LocationFilter(FilterSet):
    """Custom filterset for Location model."""
    
    tag_name = CharFilter(
        field_name='tags__name',
        lookup_expr='iexact',
        help_text=_("Filter by tag name")
    )
    parent_exists = CharFilter(
        method='filter_parent_exists',
        help_text=_("Filter locations that have parents (true) or no parents (false)")
    )
    search = CharFilter(
        method='filter_search',
        help_text=_("Search in name and description fields")
    )
    
    class Meta:
        model = Location
        fields = ['parent', 'tags']
    
    def filter_parent_exists(self, queryset, name, value):
        """Filter by parent existence."""
        if value.lower() == 'true':
            return queryset.filter(parent__isnull=False)
        elif value.lower() == 'false':
            return queryset.filter(parent__isnull=True)
        return queryset
    
    def filter_search(self, queryset, name, value):
        """Custom search filter."""
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )


# --------------------
# Location List/Create
# --------------------
class LocationListCreate(BaseAPIView, generics.ListCreateAPIView):
    """
    List all locations or create a new location.
    
    Query Parameters:
    - search: Search in name, description
    - parent: Filter by parent ID
    - tags: Filter by tag IDs
    - tag_name: Filter by tag name
    - parent_exists: true/false to filter locations with/without parents
    """
    queryset = Location.objects.all().select_related("parent", "address").prefetch_related("tags")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = LocationFilter
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']

    def get_serializer_class(self):
        if self.request.method == "GET":
            return LocationListSerializer
        return LocationSerializer

    def get_queryset(self):
        """Optimize and filter queryset."""
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        """Create a new location with tag associations."""
        # Make a mutable copy of the request data
        data = request.data.copy()
        tag_ids = data.pop("tag_ids", [])
        address_id = data.get("address")
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                # Create location
                location = serializer.save()
                
                # Handle address association
                if address_id:
                    address = get_object_or_404(AddressEntry, id=address_id)
                    location.address = address
                    location.save()
                
                # Handle tag associations
                if tag_ids:
                    self._process_tag_associations(location, tag_ids)
                
                location.refresh_from_db()
                
        except Exception as e:
            return Response(
                {"error": _("Failed to create location: {error}").format(error=str(e))},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            LocationListSerializer(location, context=self.get_serializer_context()).data, 
            status=status.HTTP_201_CREATED
        )

    def _process_tag_associations(self, location, tag_ids):
        """Process tag associations for a location."""
        if tag_ids:
            # Validate all tags exist
            valid_tags = LocationTag.objects.filter(id__in=tag_ids)
            valid_tag_ids = set(valid_tags.values_list('id', flat=True))
            invalid_tags = set(tag_ids) - valid_tag_ids
            
            if invalid_tags:
                raise ValidationError(
                    _("Invalid tag IDs: {invalid_tags}").format(invalid_tags=invalid_tags)
                )
            
            # Create tag mappings
            tag_mappings = [
                LocationTagMap(location=location, location_tag_id=tag_id)
                for tag_id in valid_tag_ids
            ]
            LocationTagMap.objects.bulk_create(tag_mappings)


# --------------------
# Location Retrieve/Update/Delete
# --------------------
class LocationRetrieveUpdateDelete(BaseAPIView, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a location instance.
    """
    queryset = Location.objects.all().select_related("parent", "address").prefetch_related("tags")
    serializer_class = LocationSerializer

    def get_serializer_class(self):
        if self.request.method == "GET":
            return LocationListSerializer
        return LocationSerializer

    def update(self, request, *args, **kwargs):
        """Update a location with tag associations."""
        instance = self.get_object()
        # Make a mutable copy of the request data
        data = request.data.copy()
        tag_ids = data.pop("tag_ids", None)
        address_id = data.get("address", None)
        
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                # Update location
                location = serializer.save()
                
                # Handle address association
                if address_id is not None:
                    if address_id:
                        location.address = get_object_or_404(AddressEntry, id=address_id)
                    else:
                        location.address = None
                    location.save()
                
                # Handle tag associations
                if tag_ids is not None:
                    self._process_tag_associations(location, tag_ids, replace_existing=True)
                
                location.refresh_from_db()
                
        except Exception as e:
            return Response(
                {"error": _("Failed to update location: {error}").format(error=str(e))},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(LocationListSerializer(location, context=self.get_serializer_context()).data)

    def perform_destroy(self, instance):
        """Prevent deletion of locations with children."""
        if instance.children.exists():
            raise ValidationError(
                _("Cannot delete location '{location_name}' because it has {child_count} child locations.").format(
                    location_name=instance.name,
                    child_count=instance.children.count()
                )
            )
        super().perform_destroy(instance)

    def _process_tag_associations(self, location, tag_ids, replace_existing=False):
        """Process tag associations for a location."""
        if replace_existing:
            LocationTagMap.objects.filter(location=location).delete()
        
        if tag_ids:
            # Validate all tags exist
            valid_tags = LocationTag.objects.filter(id__in=tag_ids)
            valid_tag_ids = set(valid_tags.values_list('id', flat=True))
            invalid_tags = set(tag_ids) - valid_tag_ids
            
            if invalid_tags:
                raise ValidationError(
                    _("Invalid tag IDs: {invalid_tags}").format(invalid_tags=invalid_tags)
                )
            
            # Create tag mappings
            tag_mappings = [
                LocationTagMap(location=location, location_tag_id=tag_id)
                for tag_id in valid_tag_ids
            ]
            LocationTagMap.objects.bulk_create(tag_mappings)


# --------------------
# LocationTag Views
# --------------------
class LocationTagListCreate(BaseAPIView, generics.ListCreateAPIView):
    """
    List all location tags or create a new tag.
    """
    queryset = LocationTag.objects.all()
    serializer_class = LocationTagSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']


class LocationTagRetrieveUpdateDelete(BaseAPIView, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a location tag instance.
    """
    queryset = LocationTag.objects.all()
    serializer_class = LocationTagSerializer

    def perform_destroy(self, instance):
        """Prevent deletion of tags used by locations."""
        if instance.locations.exists():
            raise ValidationError(
                _("Cannot delete tag '{tag_name}' because it is used by {count} locations.").format(
                    tag_name=instance.name,
                    count=instance.locations.count()
                )
            )
        super().perform_destroy(instance)


# --------------------
# LocationTagMap Views
# --------------------
class LocationTagMapListCreate(BaseAPIView, generics.ListCreateAPIView):
    """
    List all location-tag mappings or create a new mapping.
    """
    queryset = LocationTagMap.objects.all().select_related("location", "location_tag")
    serializer_class = LocationTagMapSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['location', 'location_tag']


class LocationTagMapRetrieveUpdateDelete(BaseAPIView, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a location-tag mapping instance.
    """
    queryset = LocationTagMap.objects.all().select_related("location", "location_tag")
    serializer_class = LocationTagMapSerializer


# --------------------
# Additional Function-Based Views
# --------------------
@api_view(["GET"])
def location_children_list(request, location_id):
    """
    Get all direct children of a specific location.
    """
    try:
        location = get_object_or_404(Location, id=location_id)
        children = location.children.all().select_related("parent", "address").prefetch_related("tags")
        
        serializer = LocationListSerializer(children, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {"error": _("Failed to retrieve children: {error}").format(error=str(e))},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["GET"])
def location_descendants_list(request, location_id):
    """
    Get all descendants of a specific location (recursive).
    """
    try:
        location = get_object_or_404(Location, id=location_id)
        # Simple implementation - get all children recursively
        def get_all_children(loc):
            children = list(loc.children.all())
            for child in loc.children.all():
                children.extend(get_all_children(child))
            return children
        
        descendants = get_all_children(location)
        serializer = LocationListSerializer(descendants, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {"error": _("Failed to retrieve descendants: {error}").format(error=str(e))},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["GET"])
def root_locations_list(request):
    """
    Get all root locations (locations without parents).
    """
    try:
        roots = Location.objects.filter(parent__isnull=True).select_related("address").prefetch_related("tags")
        serializer = LocationListSerializer(roots, many=True)
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {"error": _("Failed to retrieve root locations: {error}").format(error=str(e))},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
def bulk_add_tags_to_location(request, location_id):
    """
    Add multiple tags to a location without replacing existing ones.
    """
    try:
        location = get_object_or_404(Location, id=location_id)
        tag_ids = request.data.get('tag_ids', [])
        
        if not tag_ids:
            return Response(
                {"error": _("No tag IDs provided")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Get existing tag IDs to avoid duplicates
            existing_tag_ids = set(location.tags.values_list('id', flat=True))
            new_tag_ids = [tid for tid in tag_ids if tid not in existing_tag_ids]
            
            if new_tag_ids:
                valid_tags = LocationTag.objects.filter(id__in=new_tag_ids)
                valid_tag_ids = set(valid_tags.values_list('id', flat=True))
                invalid_tags = set(new_tag_ids) - valid_tag_ids
                
                if invalid_tags:
                    return Response(
                        {
                            "error": _("Invalid tag IDs"),
                            "invalid_tags": list(invalid_tags)
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Create new mappings
                tag_mappings = [
                    LocationTagMap(location=location, location_tag=tag)
                    for tag in valid_tags
                ]
                LocationTagMap.objects.bulk_create(tag_mappings)
            
            return Response({
                "success": True,
                "added_count": len(new_tag_ids),
                "already_existed": len(tag_ids) - len(new_tag_ids)
            })
            
    except Exception as e:
        return Response(
            {"error": _("Failed to add tags: {error}").format(error=str(e))},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["POST"])
def bulk_remove_tags_from_location(request, location_id):
    """
    Remove specific tags from a location.
    """
    try:
        location = get_object_or_404(Location, id=location_id)
        tag_ids = request.data.get('tag_ids', [])
        
        if not tag_ids:
            return Response(
                {"error": _("No tag IDs provided")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            deleted_count, _ = LocationTagMap.objects.filter(
                location=location,
                location_tag_id__in=tag_ids
            ).delete()
            
            return Response({
                "success": True,
                "removed_count": deleted_count
            })
            
    except Exception as e:
        return Response(
            {"error": _("Failed to remove tags: {error}").format(error=str(e))},
            status=status.HTTP_400_BAD_REQUEST
        )


# --------------------
# Location Address Upward Parent-Chain
# --------------------
@api_view(["GET"])
def location_address_upward(request, location_id=None, location_uuid=None):
    """
    Return the address parent-chain for a location by ID or UUID.
    """
    try:
        if location_uuid:
            location = get_object_or_404(Location, address__uuid=location_uuid)
        else:
            location = get_object_or_404(Location, id=location_id)

        if not location.address:
            return Response(
                {"error": "Location has no address"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AddressEntryParentChainSerializer(location.address)
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {"error": f"Failed to retrieve address chain: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )