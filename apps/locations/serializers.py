# apps/locations/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import Location, LocationTag, LocationTagMap
from apps.address.serializers import AddressEntryParentChainSerializer


# --------------------
# LocationTag Serializer
# --------------------
class LocationTagSerializer(serializers.ModelSerializer):
    location_count = serializers.IntegerField(
        source='locations.count',
        read_only=True
    )

    class Meta:
        model = LocationTag
        fields = ["id", "name", "description", "location_count"]
        read_only_fields = ["id", "location_count"]

    def validate_name(self, value):
        """Validate tag name."""
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                _("Tag name must be at least 2 characters long.")
            )
        return value


# --------------------
# LocationTagMap Serializer
# --------------------
class LocationTagMapSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    tag_name = serializers.CharField(source="location_tag.name", read_only=True)

    class Meta:
        model = LocationTagMap
        fields = ["id", "location", "location_tag", "location_name", "tag_name"]
        read_only_fields = ["id", "location_name", "tag_name"]


# --------------------
# Location List Serializer
# --------------------
class LocationListSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    address_details = AddressEntryParentChainSerializer(source="address", read_only=True)
    tags = LocationTagSerializer(many=True, read_only=True)
    children_count = serializers.IntegerField(
        source="children.count",
        read_only=True
    )

    class Meta:
        model = Location
        fields = [
            "id", "name", "parent", "parent_name", "address", "address_details",
            "description", "tags", "children_count"
        ]
        read_only_fields = ["id", "parent_name", "address_details", "tags", "children_count"]


# --------------------
# Main Location Serializer (for create/update)
# --------------------
class LocationSerializer(serializers.ModelSerializer):
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), 
        write_only=True, 
        required=False, 
        allow_empty=True
    )
    address_details = AddressEntryParentChainSerializer(source="address", read_only=True)
    tags = LocationTagSerializer(many=True, read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    children_count = serializers.IntegerField(source="children.count", read_only=True)

    class Meta:
        model = Location
        fields = [
            "id", "name", "parent", "parent_name", "address", "address_details",
            "description", "tags", "tag_ids", "children_count"
        ]
        read_only_fields = [
            "id", "address_details", "tags", "parent_name", "children_count"
        ]

    def validate_parent(self, value):
        """Validate parent location."""
        # Check for self-reference
        if self.instance and value == self.instance:
            raise serializers.ValidationError(
                _("Location cannot be its own parent.")
            )
        
        # Check for circular references
        if self.instance and value:
            current = value
            while current:
                if current == self.instance:
                    raise serializers.ValidationError(
                        _("Cannot set a descendant location as parent (circular reference).")
                    )
                current = current.parent
        
        return value

    def validate_tag_ids(self, value):
        """Validate tag IDs."""
        if value:
            # Check if all tags exist
            existing_tags = LocationTag.objects.filter(id__in=value)
            existing_tag_ids = set(existing_tags.values_list('id', flat=True))
            invalid_ids = set(value) - existing_tag_ids
            
            if invalid_ids:
                raise serializers.ValidationError(
                    _("Invalid tag IDs: {invalid_ids}").format(invalid_ids=list(invalid_ids))
                )
        return value

    def validate_name(self, value):
        """Validate location name."""
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Location name cannot be empty."))
        if len(value) < 2:
            raise serializers.ValidationError(
                _("Location name must be at least 2 characters long.")
            )
        return value

    def create(self, validated_data):
        """
        Create location - tag handling moved to view for transaction safety.
        """
        tag_ids = validated_data.pop("tag_ids", [])
        location = Location.objects.create(**validated_data)
        
        # Tag associations are handled in the view with transaction
        return location

    def update(self, instance, validated_data):
        """
        Update location - tag handling moved to view for transaction safety.
        """
        tag_ids = validated_data.pop("tag_ids", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Tag associations are handled in the view with transaction
        return instance

    def to_representation(self, instance):
        """Return appropriate representation for GET requests."""
        if self.context.get("request") and self.context["request"].method == "GET":
            return LocationListSerializer(instance, context=self.context).data
        return super().to_representation(instance)