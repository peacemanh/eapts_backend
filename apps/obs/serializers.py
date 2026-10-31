from django.db import transaction
from rest_framework import serializers
from apps.obs.models import Obs


class ObsListDetailSerializer(serializers.ModelSerializer):
    """Serializer optimized for reading Obs records with related details."""
    
    data_element_name = serializers.CharField(source='data_element.name', read_only=True)
    form_name = serializers.CharField(source='form.name', read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True, allow_null=True)
    institution_name = serializers.CharField(source='institution.name', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    updated_by_username = serializers.CharField(source='updated_by.username', read_only=True, allow_null=True)
    value_coded_name = serializers.CharField(source='value_coded.name', read_only=True, allow_null=True)

    class Meta:
        model = Obs
        fields = [
            'id', 'uuid', 'record_id', 'person_id', 'encounter_id',
            'data_element', 'data_element_name', 'form', 'form_name',
            'group', 'group_name', 'institution', 'institution_name',
            'location', 'location_name', 'value_text', 'value_numeric',
            'value_coded', 'value_coded_name', 'value_datetime',
            'created_by', 'created_by_username', 'updated_by', 'updated_by_username',
            'date_created', 'date_updated',
        ]
        read_only_fields = ['id', 'uuid', 'date_created', 'date_updated', 'created_by', 'updated_by']


class ObsBulkCreateListSerializer(serializers.ListSerializer):
    """Custom ListSerializer that gracefully handles extra kwargs from perform_create."""
    
    def create(self, validated_data, **kwargs):
        request = self.context.get('request')
        default_user = request.user if request and request.user.is_authenticated else None
        
        # Grab audit fields from kwargs passed by perform_create, fallback to request user
        created_by = kwargs.get('created_by', default_user)
        updated_by = kwargs.get('updated_by', default_user)

        created_obs = []
        with transaction.atomic():
            for item in validated_data:
                item['created_by'] = created_by
                item['updated_by'] = updated_by
                obs = Obs.objects.create(**item)
                created_obs.append(obs)
        return created_obs


class ObsCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer optimized for creating and updating Obs records."""

    class Meta:
        model = Obs
        list_serializer_class = ObsBulkCreateListSerializer
        fields = [
            'id',
            'uuid',
            'record_id',
            'person_id',
            'encounter_id',
            'data_element',
            'form',
            'group',
            'institution',
            'location',
            'value_text',
            'value_numeric',
            'value_coded',
            'value_datetime',
        ]
        read_only_fields = ['id', 'uuid']

    def validate(self, attrs):
        value_fields = ['value_text', 'value_numeric', 'value_coded', 'value_datetime']
        if not any(attrs.get(field) is not None for field in value_fields):
            raise serializers.ValidationError(
                "At least one value field (value_text, value_numeric, value_coded, or value_datetime) must be provided."
            )
        return attrs