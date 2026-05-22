import logging
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction
from django.apps import apps
from django.core.cache import cache

from apps.person.models.person import Person, PersonName

logger = logging.getLogger(__name__)

# Import location serializers (assuming they exist)
from apps.locations.serializers import LocationListSerializer

class CompactLocationSerializer(LocationListSerializer):
    """Use the existing LocationListSerializer"""
    pass

class DetailedLocationSerializer(LocationListSerializer):
    """Use the existing LocationListSerializer which already includes tags"""
    pass


class PersonNameSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()
    
    class Meta:
        model = PersonName
        fields = [
            'id', 'person', 'given_name', 'middle_name', 'last_name', 'preferred',
            'full_name', 'display_name', 'initials', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'full_name', 'display_name', 'initials']
    
    def get_full_name(self, obj):
        names = [obj.given_name, obj.middle_name, obj.last_name]
        return " ".join(filter(None, names))
    
    def get_display_name(self, obj):
        return f"{obj.given_name} {obj.last_name}"
    
    def get_initials(self, obj):
        initials = obj.given_name[0] if obj.given_name else ''
        if obj.middle_name:
            initials += obj.middle_name[0]
        initials += obj.last_name[0] if obj.last_name else ''
        return initials.upper()
    
    def validate_given_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Given name cannot be empty."))
        if len(value) < 2:
            raise serializers.ValidationError(_("Given name must be at least 2 characters long."))
        return value
    
    def validate_last_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Last name cannot be empty."))
        if len(value) < 2:
            raise serializers.ValidationError(_("Last name must be at least 2 characters long."))
        return value
    
    def validate_middle_name(self, value):
        if value:
            value = value.strip()
            if len(value) < 2:
                raise serializers.ValidationError(_("Middle name must be at least 2 characters long if provided."))
        return value
    
    def validate(self, attrs):
        """Keep original validation logic with caching"""
        person = attrs.get('person')
        given_name = attrs.get('given_name', '').strip().lower()
        middle_name = attrs.get('middle_name', '').strip().lower() if attrs.get('middle_name') else None
        last_name = attrs.get('last_name', '').strip().lower()
        
        # Cache key for duplicate check
        cache_key = f'person_name_duplicate:{person.id if person else 0}:{given_name}:{middle_name or ""}:{last_name}'
        cached_result = cache.get(cache_key)
        
        if cached_result is None:
            # Original query logic
            if person and self.instance:
                existing = PersonName.objects.filter(
                    person=person,
                    given_name__iexact=given_name,
                    last_name__iexact=last_name
                ).exclude(id=self.instance.id)
                if middle_name:
                    existing = existing.filter(middle_name__iexact=middle_name)
                else:
                    existing = existing.filter(middle_name__isnull=True)
            elif person:
                existing = PersonName.objects.filter(
                    person=person,
                    given_name__iexact=given_name,
                    last_name__iexact=last_name
                )
                if middle_name:
                    existing = existing.filter(middle_name__iexact=middle_name)
                else:
                    existing = existing.filter(middle_name__isnull=True)
            else:
                existing = PersonName.objects.none()
            
            cached_result = existing.exists()
            cache.set(cache_key, cached_result, 60)
        
        if cached_result:
            raise serializers.ValidationError(
                _("A name with this combination already exists for this person.")
            )
        
        return attrs
    
    def create(self, validated_data):
        """Keep original create method with cache clearing"""
        try:
            with transaction.atomic():
                person = validated_data['person']
                if not person.names.exists():
                    validated_data['preferred'] = True
                
                if validated_data.get('preferred', False):
                    person.names.filter(preferred=True).update(preferred=False)
                
                instance = super().create(validated_data)
                
                # Clear cache
                cache.delete(f'person:{person.id}:preferred_name')
                
                return instance
        except Exception as e:
            logger.error(f"Error creating person name: {str(e)}")
            raise serializers.ValidationError(
                _("Failed to create person name. Please try again.")
            )
    
    def update(self, instance, validated_data):
        """Keep original update method with cache clearing"""
        try:
            with transaction.atomic():
                if validated_data.get('preferred', False) and not instance.preferred:
                    instance.person.names.filter(preferred=True).update(preferred=False)
                
                updated_instance = super().update(instance, validated_data)
                
                # Clear cache
                cache.delete(f'person:{instance.person.id}:preferred_name')
                
                return updated_instance
        except Exception as e:
            logger.error(f"Error updating person name: {str(e)}")
            raise serializers.ValidationError(
                _("Failed to update person name. Please try again.")
            )


class BasePersonSerializer(serializers.ModelSerializer):
    """Base serializer with shared logic - keeping original methods"""
    names = PersonNameSerializer(many=True, read_only=True)
    preferred_name = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    
    class Meta:
        model = Person
        fields = [
            'id', 'gender', 'birthdate', 'contact_info', 'location',
            'age', 'preferred_name', 'names', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'age', 'preferred_name']
    
    def get_preferred_name(self, obj):
        """Keep original method with caching"""
        cache_key = f'person:{obj.id}:preferred_name_data'
        cached = cache.get(cache_key)
        
        if cached is None:
            preferred_name = obj.get_preferred_name()
            if preferred_name:
                cached = {
                    'id': preferred_name.id,
                    'full_name': f"{preferred_name.given_name} {preferred_name.last_name}",
                    'given_name': preferred_name.given_name,
                    'last_name': preferred_name.last_name
                }
                cache.set(cache_key, cached, 300)
            else:
                cached = None
        
        return cached
    
    def get_age(self, obj):
        if not obj.birthdate:
            return None
        
        today = timezone.now().date()
        return today.year - obj.birthdate.year - (
            (today.month, today.day) < (obj.birthdate.month, obj.birthdate.day)
        )
    
    def validate_birthdate(self, value):
        if value and value > timezone.now().date():
            raise serializers.ValidationError(_("Birthdate cannot be in the future."))
        return value
    
    def validate_gender(self, value):
        valid_genders = [choice[0] for choice in Person.Gender.choices]
        if value not in valid_genders:
            raise serializers.ValidationError(
                _(f"Invalid gender choice. Must be one of: {', '.join(valid_genders)}")
            )
        return value
    
    def validate_contact_info(self, value):
        if value and len(value) > 1000:
            raise serializers.ValidationError(_("Contact info cannot exceed 1000 characters."))
        return value.strip() if value else value
    
    def validate_location(self, value):
        if value:
            try:
                Location = apps.get_model('locations', 'Location')
                if not Location.objects.filter(id=value.id).exists():
                    raise serializers.ValidationError(_("Selected location does not exist."))
            except LookupError:
                raise serializers.ValidationError(_("Locations app is not available."))
        return value
    
    def create(self, validated_data):
        """Keep original create method"""
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except Exception as e:
            logger.error(f"Error creating person: {str(e)}")
            raise serializers.ValidationError(
                _("Failed to create person. Please try again.")
            )
    
    def update(self, instance, validated_data):
        """Keep original update method"""
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except Exception as e:
            logger.error(f"Error updating person: {str(e)}")
            raise serializers.ValidationError(
                _("Failed to update person. Please try again.")
            )


class PersonSerializer(BasePersonSerializer):
    """Default person serializer - keep original"""
    location_detail = CompactLocationSerializer(source='location', read_only=True)
    
    class Meta(BasePersonSerializer.Meta):
        fields = BasePersonSerializer.Meta.fields + ['location_detail']
        read_only_fields = BasePersonSerializer.Meta.read_only_fields + ['location_detail']
    
    def to_representation(self, instance):
        """Add caching to representation without changing method signature"""
        cache_key = f'person:{instance.id}:serialized'
        cached = cache.get(cache_key)
        
        if cached is None:
            cached = super().to_representation(instance)
            cache.set(cache_key, cached, 300)
        
        return cached


class PersonWithAddressSerializer(BasePersonSerializer):
    """Person serializer with full address hierarchy - keep original"""
    location_detail = DetailedLocationSerializer(source='location', read_only=True)
    
    class Meta(BasePersonSerializer.Meta):
        fields = BasePersonSerializer.Meta.fields + ['location_detail']
        read_only_fields = BasePersonSerializer.Meta.read_only_fields + ['location_detail']


class PersonCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating person with initial name - keep original"""
    given_name = serializers.CharField(write_only=True, required=True)
    middle_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = Person
        fields = [
            'gender', 'birthdate', 'contact_info', 'location',
            'given_name', 'middle_name', 'last_name'
        ]
    
    def validate_given_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Given name is required."))
        return value
    
    def validate_last_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Last name is required."))
        return value
    
    def create(self, validated_data):
        """Keep original create method"""
        try:
            with transaction.atomic():
                given_name = validated_data.pop('given_name')
                middle_name = validated_data.pop('middle_name', None)
                last_name = validated_data.pop('last_name')
                
                person = Person.objects.create(**validated_data)
                
                PersonName.objects.create(
                    person=person,
                    given_name=given_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    preferred=True
                )
                
                return person
        except Exception as e:
            logger.error(f"Error creating person: {str(e)}")
            raise serializers.ValidationError(
                _("Failed to create person with initial name. Please try again.")
            )


class PersonLocationUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for updating person location - keep original"""
    location_detail = DetailedLocationSerializer(source='location', read_only=True)
    
    class Meta:
        model = Person
        fields = ['location', 'location_detail']
        read_only_fields = ['location_detail']
    
    def update(self, instance, validated_data):
        """Keep original update method with cache clearing"""
        try:
            with transaction.atomic():
                updated_instance = super().update(instance, validated_data)
                
                # Clear cache
                cache.delete(f'person:{instance.id}:serialized')
                
                return updated_instance
        except Exception as e:
            logger.error(f"Error updating location: {str(e)}")
            raise serializers.ValidationError(
                _("Failed to update location. Please try again.")
            )