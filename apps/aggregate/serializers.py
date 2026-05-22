# apps/aggregate/serializers.py - FULL UPDATED VERSION
from rest_framework import serializers
from django.db import transaction
from django.core.validators import URLValidator, EmailValidator
from .models import AggregateRecord
from apps.data_element.models import DataElement
from apps.locations.models import Location
from dateutil.parser import parse
from datetime import datetime, time as dt_time
import re

# -------------------------
# Bulk ListSerializer for bulk create/update
# -------------------------
class BulkAggregateRecordSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        records = [AggregateRecord(**item) for item in validated_data]
        return AggregateRecord.objects.bulk_create(records)

    def update(self, instances, validated_data):
        instance_mapping = {instance.id: instance for instance in instances}
        updated_instances = []

        for data in validated_data:
            instance = instance_mapping.get(data.get('id'))
            if instance:
                for attr, value in data.items():
                    setattr(instance, attr, value)
                updated_instances.append(instance)

        if updated_instances:
            update_fields = [
                'value_text', 'value_numeric', 'value_coded',
                'value_datetime', 'date_updated', 'record_id',
                'institution', 'location', 'updated_by', 'group'
            ]
            return AggregateRecord.objects.bulk_update(
                updated_instances,
                update_fields
            )
        return updated_instances


# -------------------------
# Core Model Serializer
# -------------------------
class AggregateRecordSerializer(serializers.ModelSerializer):
    value = serializers.CharField(write_only=True, required=False, allow_blank=True)
    data_type = serializers.CharField(write_only=True)
    group_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    record_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    # Institution field is required for all operations
    institution = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        required=True,
        help_text="Institution ID (required)"
    )
    
    # Location field is optional
    location = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        required=False,
        allow_null=True,
        help_text="Location ID within institution (optional)"
    )
    
    # Data element field (now properly filterable)
    data_element = serializers.PrimaryKeyRelatedField(
        queryset=DataElement.objects.all(),
        required=True,
        help_text="Data Element ID (required)"
    )
    
    # Form field
    form = serializers.PrimaryKeyRelatedField(
        queryset=DataElement.objects.all(),
        required=True,
        help_text="Form ID (required)"
    )

    # Read-only related names
    data_element_name = serializers.CharField(source='data_element.name', read_only=True)
    data_element_type = serializers.CharField(source='data_element.data_type', read_only=True)
    data_element_code = serializers.CharField(source='data_element.code', read_only=True, allow_null=True)
    data_element_description = serializers.CharField(source='data_element.description', read_only=True, allow_null=True)
    
    form_name = serializers.CharField(source='form.name', read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True, allow_null=True)
    value_coded_name = serializers.CharField(source='value_coded.name', read_only=True)
    
    # New fields (read-only for display)
    institution_name = serializers.CharField(source='institution.name', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    updated_by_name = serializers.CharField(source='updated_by.username', read_only=True, allow_null=True)

    class Meta:
        model = AggregateRecord
        fields = [
            'id', 'uuid', 'record_id',
            'data_element', 'form', 'group', 'group_id',
            'data_type', 'institution', 'location',
            'value_text', 'value_numeric', 'value_coded',
            'value_datetime', 'value',
            'date_created', 'date_updated',
            
            # Read-only fields
            'data_element_name', 'data_element_type', 'data_element_code', 'data_element_description',
            'form_name', 'group_name',
            'value_coded_name', 'institution_name', 'location_name',
            'created_by_name', 'updated_by_name'
        ]
        read_only_fields = [
            'id', 'uuid', 'date_created', 'date_updated',
            'created_by', 'updated_by', 'group',
            'data_element_name', 'data_element_type', 'data_element_code', 'data_element_description',
            'form_name', 'group_name',
            'value_coded_name', 'institution_name', 'location_name',
            'created_by_name', 'updated_by_name'
        ]
        list_serializer_class = BulkAggregateRecordSerializer

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            # Don't allow manual setting of created_by/updated_by
            if 'created_by' in attrs:
                del attrs['created_by']
            if 'updated_by' in attrs:
                del attrs['updated_by']
        
        # Handle group_id - validate and set group object
        group_id = attrs.pop('group_id', None)
        if group_id is not None:
            try:
                group = DataElement.objects.get(id=group_id)
                attrs['group'] = group
            except DataElement.DoesNotExist:
                raise serializers.ValidationError({
                    'group_id': f'DataElement with id {group_id} does not exist.'
                })
        elif 'group' not in attrs:
            # If group_id not provided and group not in attrs, set to None
            attrs['group'] = None
        
        # Validate that institution exists and is valid
        institution = attrs.get('institution')
        if institution:
            # You could add additional validation here
            pass
        
        value = attrs.pop('value', None)
        data_type = attrs.pop('data_type', None)

        if data_type is None:
            data_type = self.context.get('data_type')

        # For update operations, if value is not provided, keep existing values
        if self.instance and value is None:
            return attrs

        if value is None or value == '':
            attrs.update({
                'value_text': None,
                'value_numeric': None,
                'value_coded': None,
                'value_datetime': None
            })
            return attrs

        data_type_lower = data_type.lower() if isinstance(data_type, str) else ''

        try:
            if data_type_lower in ['numeric', 'coded']:
                try:
                    if data_type_lower == 'numeric':
                        attrs['value_numeric'] = float(value)
                        attrs['value_text'] = None
                        attrs['value_coded'] = None
                        attrs['value_datetime'] = None
                    else:  # coded
                        coded_element = DataElement.objects.get(id=int(value))
                        attrs['value_coded'] = coded_element
                        attrs['value_text'] = None
                        attrs['value_numeric'] = None
                        attrs['value_datetime'] = None
                except (ValueError, TypeError):
                    raise serializers.ValidationError(f"Value '{value}' cannot be converted to {data_type}.")
                except DataElement.DoesNotExist:
                    raise serializers.ValidationError(f"Invalid coded value: {value}")

            elif data_type_lower in ['text', 'textarea', 'signature', 'url', 'email', 'phone', 'file', 'image', 'boolean']:
                if data_type_lower == 'boolean':
                    if isinstance(value, str):
                        value_lower = value.lower()
                        if value_lower in ['true', '1', 'yes', 'y']:
                            attrs['value_text'] = 'true'
                        elif value_lower in ['false', '0', 'no', 'n']:
                            attrs['value_text'] = 'false'
                        else:
                            raise serializers.ValidationError("Boolean value must be 'true' or 'false'")
                    else:
                        attrs['value_text'] = 'true' if bool(value) else 'false'
                else:
                    attrs['value_text'] = str(value)

                if data_type_lower == 'url':
                    URLValidator()(value)
                elif data_type_lower == 'email':
                    EmailValidator()(value)
                elif data_type_lower == 'phone':
                    phone_pattern = r'^\+?1?\d{9,15}$'
                    if not re.match(phone_pattern, value.replace(' ', '').replace('-', '')):
                        raise serializers.ValidationError("Invalid phone number format.")

                attrs['value_numeric'] = None
                attrs['value_coded'] = None
                attrs['value_datetime'] = None

            elif data_type_lower in ['date', 'datetime', 'time']:
                parsed = parse(value)

                if data_type_lower == 'date':
                    attrs['value_datetime'] = datetime.combine(parsed.date(), dt_time.min)
                elif data_type_lower == 'time':
                    today = datetime.today().date()
                    attrs['value_datetime'] = datetime.combine(today, parsed.time())
                else:  # datetime
                    attrs['value_datetime'] = parsed

                attrs['value_text'] = None
                attrs['value_numeric'] = None
                attrs['value_coded'] = None

            else:
                raise serializers.ValidationError(f"Unsupported data type: {data_type}")

        except serializers.ValidationError:
            raise

        return attrs

    def create(self, validated_data):
        # Auto-set created_by and updated_by to authenticated user
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
            validated_data['updated_by'] = request.user
        else:
            # This shouldn't happen if authentication is properly enforced
            raise serializers.ValidationError("Authentication required.")
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Auto-set updated_by to authenticated user
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['updated_by'] = request.user
        else:
            raise serializers.ValidationError("Authentication required.")
        
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        # Add `value` + infer type
        if instance.value_numeric is not None:
            rep['value'] = float(instance.value_numeric)
            rep['data_type'] = 'numeric'
        elif instance.value_coded is not None:
            rep['value'] = instance.value_coded.id
            rep['data_type'] = 'coded'
        elif instance.value_datetime is not None:
            dt = instance.value_datetime
            if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                rep['value'] = dt.date().isoformat()
                rep['data_type'] = 'date'
            elif dt.date() == datetime.today().date() and (dt.hour != 0 or dt.minute != 0):
                rep['value'] = dt.time().isoformat()
                rep['data_type'] = 'time'
            else:
                rep['value'] = dt.isoformat()
                rep['data_type'] = 'datetime'
        elif instance.value_text is not None:
            rep['value'] = instance.value_text
            rep['data_type'] = 'text'

        return rep


# -------------------------
# Serializers used by grouped endpoint
# -------------------------
class GroupedFieldSerializer(serializers.ModelSerializer):
    data_element = serializers.PrimaryKeyRelatedField(read_only=True)
    data_element_name = serializers.CharField(source='data_element.name', read_only=True)
    data_element_type = serializers.CharField(source='data_element.data_type', read_only=True)
    data_element_code = serializers.CharField(source='data_element.code', read_only=True, allow_null=True)

    form = serializers.PrimaryKeyRelatedField(read_only=True)
    form_name = serializers.CharField(source='form.name', read_only=True)
    
    # Group fields
    group = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    group_name = serializers.CharField(source='group.name', read_only=True, allow_null=True)

    value_coded_name = serializers.CharField(source='value_coded.name', read_only=True, allow_null=True)

    value = serializers.SerializerMethodField()
    data_type = serializers.SerializerMethodField()
    
    # Add sort_weight field
    sort_weight = serializers.SerializerMethodField()
    
    # New fields for institution and location
    institution_name = serializers.CharField(source='institution.name', read_only=True, allow_null=True)
    location_name = serializers.CharField(source='location.name', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    updated_by_name = serializers.CharField(source='updated_by.username', read_only=True, allow_null=True)

    class Meta:
        model = AggregateRecord
        fields = [
            "id", "uuid", "record_id",

            "data_element", "data_element_name", "data_element_type", "data_element_code",
            "form", "form_name",
            "group", "group_name",

            "institution", "institution_name",
            "location", "location_name",

            "value_text", "value_numeric",
            "value_coded", "value_coded_name",
            "value_datetime",

            "value", "data_type",
            "sort_weight",

            "created_by_name", "updated_by_name",
            "date_created", "date_updated"
        ]

    def get_value(self, obj):
        if obj.value_text is not None:
            return obj.value_text
        if obj.value_numeric is not None:
            return float(obj.value_numeric)
        if obj.value_coded is not None:
            return obj.value_coded_id
        if obj.value_datetime is not None:
            return obj.value_datetime.date()
        return None

    def get_data_type(self, obj):
        if obj.value_text is not None:
            return "text"
        if obj.value_numeric is not None:
            return "numeric"
        if obj.value_coded is not None:
            return "coded"
        if obj.value_datetime is not None:
            return "date"
        return None

    def get_sort_weight(self, obj):
        """
        Get the sort_weight using prefetched data to avoid N+1 queries.
        For grouped fields, look for membership in the group.
        For non-grouped fields, look for membership in the form.
        """
        if (obj.data_element_id and 
            hasattr(obj.data_element, 'prefetched_memberships')):
            
            # Priority 1: If field has a group, look for membership in that group
            if obj.group_id:
                for membership in obj.data_element.prefetched_memberships:
                    if membership.section_element_id == obj.group_id:
                        return membership.sort_weight
            
            # Priority 2: If no group or group membership not found, look for membership in form
            if obj.form_id:
                for membership in obj.data_element.prefetched_memberships:
                    if membership.section_element_id == obj.form_id:
                        return membership.sort_weight
        
        # Fallback: return 0 if no relationship found
        return 0


class GroupedAggregateRecordSerializer(serializers.Serializer):
    """
    Top-level grouped serializer used only if you want to use serializer for grouped
    objects (we build grouped dicts in view; this serializer documents the shape).
    """
    record_id = serializers.CharField()
    form = serializers.IntegerField(allow_null=True)
    form_name = serializers.CharField(allow_null=True)
    institution = serializers.IntegerField(allow_null=True)
    institution_name = serializers.CharField(allow_null=True)
    location = serializers.IntegerField(allow_null=True, required=False)
    location_name = serializers.CharField(allow_null=True, required=False)
    group = serializers.IntegerField(allow_null=True, required=False)
    group_name = serializers.CharField(allow_null=True, required=False)
    date_created = serializers.DateTimeField()
    date_updated = serializers.DateTimeField()
    fields = GroupedFieldSerializer(many=True)


# -------------------------
# Serializer for Data Element Statistics
# -------------------------
class DataElementStatsSerializer(serializers.Serializer):
    data_element_id = serializers.IntegerField(source='data_element__id')
    data_element_name = serializers.CharField(source='data_element__name')
    data_element_type = serializers.CharField(source='data_element__data_type')
    data_element_description = serializers.CharField(source='data_element__description', allow_null=True)
    
    total_records = serializers.IntegerField()
    unique_record_ids = serializers.IntegerField()
    avg_value = serializers.FloatField(allow_null=True)
    min_value = serializers.FloatField(allow_null=True)
    max_value = serializers.FloatField(allow_null=True)
    sum_value = serializers.FloatField(allow_null=True)
    latest_record = serializers.DateTimeField()
    earliest_record = serializers.DateTimeField()
    unique_forms = serializers.IntegerField()
    unique_groups = serializers.IntegerField()
    unique_locations = serializers.IntegerField()