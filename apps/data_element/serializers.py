# apps/data_element/serializers.py
from django.db import transaction
from rest_framework import serializers
import pandas as pd
import io
import csv
import json
from .models import (
    DataElementClass,
    DataType,
    MappingSource,
    DataElement,
    DataElementValueSet,
    DataElementSetMember,
    DataElementSourceMapping,
)


# -------------------------
# Nested serializers for FK fields
# -------------------------
class DataElementClassNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataElementClass
        fields = ['id', 'name']


class DataTypeNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataType
        fields = ['id', 'name']


class MappingSourceNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = MappingSource
        fields = ['id', 'name']


# -------------------------
# Source Mapping nested serializer
# -------------------------
class DataElementSourceMappingNestedSerializer(serializers.ModelSerializer):
    source_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DataElementSourceMapping
        fields = ['id', 'source', 'source_detail', 'code', 'description']

    def get_source_detail(self, obj):
        return MappingSourceNestedSerializer(obj.source).data


# -------------------------
# ValueSet nested serializer (LIGHTWEIGHT BUT BACKWARD COMPATIBLE)
# -------------------------
class DataElementValueSetNestedSerializer(serializers.ModelSerializer):
    """
    Lightweight nested serializer for ValueSet that maintains backward compatibility
    Returns the same structure as before but with lightweight data
    Limited to 100 answer elements for performance
    """
    answer_element_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DataElementValueSet
        fields = ['id', 'answer_element', 'answer_element_detail', 'sort_weight']

    def get_answer_element_detail(self, obj):
        """
        Returns a lightweight representation of the answer element
        maintaining the same structure as the original nested response
        Limited to 100 answer elements for performance
        """
        # Limit source mappings to prevent N+1 queries and large payloads
        source_mappings = obj.answer_element.source_mappings.all()[:5]  # Limit to 5 source mappings per answer
        
        return {
            'id': obj.answer_element.id,
            'name': obj.answer_element.name,
            'label': obj.answer_element.label,
            'source_mappings': DataElementSourceMappingNestedSerializer(
                source_mappings, 
                many=True, 
                context=self.context
            ).data
        }


# -------------------------
# SetMember nested serializer (UNCHANGED)
# -------------------------
class DataElementSetMemberNestedSerializer(serializers.ModelSerializer):
    member_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DataElementSetMember
        fields = ['id', 'member_element', 'member_detail', 'sort_weight']

    def get_member_detail(self, obj):
        return DataElementSerializer(obj.member_element, context=self.context).data


# -------------------------
# Simplified List Serializer for better performance
# -------------------------
class DataElementListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for list views to improve performance
    """
    class_field = DataElementClassNestedSerializer(source='class_id', read_only=True)
    datatype_field = DataTypeNestedSerializer(source='datatype_id', read_only=True)
    source_mappings_count = serializers.SerializerMethodField()
    value_set_answers_count = serializers.SerializerMethodField()
    set_members_count = serializers.SerializerMethodField()

    class Meta:
        model = DataElement
        fields = [
            'id', 'uuid', 'name', 'label',
            'class_field', 'datatype_field',
            'unit', 'length', 'default_value',
            'required', 'multi_value',
            'normal_min_value', 'normal_max_value',
            'description', 'status',
            'created_date', 'updated_date',
            'source_mappings_count',
            'value_set_answers_count',
            'set_members_count',
        ]
        read_only_fields = fields

    def get_source_mappings_count(self, obj):
        return obj.source_mappings.count()

    def get_value_set_answers_count(self, obj):
        return obj.value_set_parents.count()

    def get_set_members_count(self, obj):
        return obj.section_set_members.count()


# -------------------------
# NEW: Lightweight Answer Element Serializer for Search
# -------------------------
class AnswerElementSearchSerializer(serializers.Serializer):
    """
    Ultra-lightweight serializer for answer element search results
    """
    id = serializers.IntegerField()
    name = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    sort_weight = serializers.IntegerField()
    
    # Optional minimal source mappings
    source_mappings = serializers.SerializerMethodField()
    
    def get_source_mappings(self, obj):
        # obj is expected to be a DataElement instance with prefetched source_mappings
        request = self.context.get('request')
        limit = self.context.get('source_mappings_limit', 3)
        
        # If we have prefetched source mappings, use them
        if hasattr(obj, '_prefetched_objects_cache') and 'source_mappings' in obj._prefetched_objects_cache:
            source_mappings = obj.source_mappings.all()[:limit]
        else:
            source_mappings = obj.source_mappings.select_related('source').all()[:limit]
        
        return [
            {
                'id': sm.id,
                'source_id': sm.source_id,
                'source_name': sm.source.name if sm.source else None,
                'code': sm.code
            }
            for sm in source_mappings
        ]


# -------------------------
# Main DataElement Serializer
# -------------------------
class DataElementSerializer(serializers.ModelSerializer):
    """
    Primary serializer for DataElement.
    - returns nested read-only relationships (value_set_answers, set_members, source_mappings)
    - supports writable structured payloads:
        value_set: [{ "answer_id": int, "sort_weight": int }, ...]
        set_members_input: [{ "member_id": int, "sort_weight": int }, ...]
        source_mappings: [{ "source_id": int, "code": str, "description": str }, ...]
    """
    # read-only nested fields
    class_field = DataElementClassNestedSerializer(source='class_id', read_only=True)
    datatype_field = DataTypeNestedSerializer(source='datatype_id', read_only=True)
    
    # Source mappings
    source_mappings = DataElementSourceMappingNestedSerializer(many=True, read_only=True)

    # Value set answers - USING BACKWARD COMPATIBLE LIGHTWEIGHT SERIALIZER
    # Limit to 100 answer elements for performance
    value_set_answers = serializers.SerializerMethodField(read_only=True)
    
    # Set members - UNCHANGED
    set_members = DataElementSetMemberNestedSerializer(source='section_set_members', many=True, read_only=True)

    # write-only structured inputs
    value_set = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(), allow_empty=False),
        write_only=True,
        required=False
    )
    set_members_input = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(), allow_empty=False),
        write_only=True,
        required=False
    )
    source_mappings_input = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(), allow_empty=False),
        write_only=True,
        required=False
    )

    # foreign key write fields
    class_id = serializers.PrimaryKeyRelatedField(queryset=DataElementClass.objects.all(), write_only=True, required=True)
    datatype_id = serializers.PrimaryKeyRelatedField(queryset=DataType.objects.all(), write_only=True, required=True)

    # allow recursive exclusion of set_members in nested calls
    def __init__(self, *args, **kwargs):
        self.exclude_set_members = kwargs.pop('exclude_set_members', False)
        super().__init__(*args, **kwargs)
        if self.exclude_set_members:
            self.fields.pop('set_members', None)

    class Meta:
        model = DataElement
        fields = [
            'id', 'uuid', 'name', 'label',
            'class_id', 'datatype_id',
            'unit', 'length', 'default_value',
            'required', 'multi_value',
            'normal_min_value', 'normal_max_value',
            'description', 'status',
            'created_date', 'updated_date',
            'class_field', 'datatype_field',
            'source_mappings', 'source_mappings_input',
            'value_set_answers', 'value_set',
            'set_members', 'set_members_input',
        ]
        read_only_fields = ['id', 'uuid', 'created_date', 'updated_date',
                            'class_field', 'datatype_field',
                            'source_mappings', 'value_set_answers', 'set_members']
        extra_kwargs = {
            'name': {
                'validators': []  # Remove default unique validator, we'll handle it in validate()
            }
        }

    def get_value_set_answers(self, obj):
        """
        Get value set answers with a limit of 100 for performance
        """
        # Limit to 100 answer elements
        value_set_parents = obj.value_set_parents.all()[:100]
        serializer = DataElementValueSetNestedSerializer(
            value_set_parents, 
            many=True, 
            context=self.context
        )
        return serializer.data

    # -------------------------
    # Input normalization
    # -------------------------
    def to_internal_value(self, data):
        data = data.copy()
        # normalize empty strings for FK fields
        for fk in ('class_id', 'datatype_id'):
            if fk in data and (data[fk] == "" or data[fk] is None):
                data[fk] = None
        # numeric fields
        for num_field in ('length', 'normal_min_value', 'normal_max_value'):
            if num_field in data and data[num_field] == "":
                data[num_field] = None
        return super().to_internal_value(data)

    # -------------------------
    # Validations for structured lists
    # -------------------------
    def _validate_struct_list(self, lst, id_key):
        """
        Validate a structured list of dicts like [{ "answer_id": 3, "sort_weight": 1 }, ...]
        Returns normalized list with integer ids and sort_weight ints.
        """
        if not isinstance(lst, list):
            raise serializers.ValidationError("Expected a list.")
        normalized = []
        seen_ids = set()
        for i, item in enumerate(lst):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"List item at index {i} must be an object.")
            if id_key not in item:
                raise serializers.ValidationError(f"List item at index {i} missing '{id_key}'.")
            try:
                item_id = int(item[id_key])
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Invalid {id_key} at index {i}. must be integer.")
            if item_id in seen_ids:
                raise serializers.ValidationError(f"Duplicate {id_key} {item_id} in list.")
            seen_ids.add(item_id)
            # sort weight optional
            sw = item.get('sort_weight', 0)
            try:
                sw_int = int(sw)
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Invalid sort_weight at index {i}. Must be integer.")
            normalized.append({'id': item_id, 'sort_weight': sw_int})
        return normalized

    def _validate_source_mappings_list(self, lst):
        """
        Validate source mappings list like [{ "source_id": 1, "code": "ABC", "description": "..." }, ...]
        """
        if not isinstance(lst, list):
            raise serializers.ValidationError("Expected a list.")
        
        normalized = []
        seen_sources = set()
        
        for i, item in enumerate(lst):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"List item at index {i} must be an object.")
            
            # Validate source_id
            if 'source_id' not in item:
                raise serializers.ValidationError(f"List item at index {i} missing 'source_id'.")
            
            try:
                source_id = int(item['source_id'])
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Invalid source_id at index {i}. Must be integer.")
            
            # Check for duplicate sources
            if source_id in seen_sources:
                raise serializers.ValidationError(f"Duplicate source_id {source_id} in source mappings.")
            seen_sources.add(source_id)
            
            # Validate source exists
            if not MappingSource.objects.filter(id=source_id).exists():
                raise serializers.ValidationError(f"Source with id {source_id} does not exist.")
            
            # Get code and description (code can be empty/null)
            code = item.get('code', '').strip()
            description = item.get('description', '').strip()
            
            normalized.append({
                'source_id': source_id,
                'code': code if code else None,
                'description': description if description else None
            })
        
        return normalized

    def validate(self, attrs):
        """
        Validate that a data element is not used as its own answer or member.
        Also validate referenced IDs exist and name is unique.
        """
        initial = getattr(self, 'initial_data', {}) or {}
        
        # Validate structured lists if present
        vs = initial.get('value_set', None)
        sm = initial.get('set_members_input', None)
        source_mappings = initial.get('source_mappings_input', None)

        # If update and instance exists, prevent self reference
        instance = getattr(self, 'instance', None)
        
        if vs is not None:
            normalized_vs = self._validate_struct_list(vs, 'answer_id')
            if instance and any(item['id'] == instance.id for item in normalized_vs):
                raise serializers.ValidationError("A DataElement cannot be its own value set answer.")
            # verify referenced ids exist
            existing = set(DataElement.objects.filter(id__in=[i['id'] for i in normalized_vs]).values_list('id', flat=True))
            missing = [i['id'] for i in normalized_vs if i['id'] not in existing]
            if missing:
                raise serializers.ValidationError({"value_set": f"Referenced answer element ids do not exist: {missing}"})

        if sm is not None:
            normalized_sm = self._validate_struct_list(sm, 'member_id')
            if instance and any(item['id'] == instance.id for item in normalized_sm):
                raise serializers.ValidationError("A DataElement cannot be its own set member.")
            existing = set(DataElement.objects.filter(id__in=[i['id'] for i in normalized_sm]).values_list('id', flat=True))
            missing = [i['id'] for i in normalized_sm if i['id'] not in existing]
            if missing:
                raise serializers.ValidationError({"set_members_input": f"Referenced member element ids do not exist: {missing}"})

        if source_mappings is not None:
            self._validate_source_mappings_list(source_mappings)

        # Validate name uniqueness
        name = attrs.get('name')
        if name:
            # Check if a DataElement with this name already exists
            qs = DataElement.objects.filter(name=name)
            if instance:
                # For updates, exclude the current instance
                qs = qs.exclude(id=instance.id)
            
            if qs.exists():
                raise serializers.ValidationError({
                    'name': f'A DataElement with name "{name}" already exists.'
                })

        return attrs

    # -------------------------
    # Create / Update (atomic)
    # -------------------------
    @transaction.atomic
    def create(self, validated_data):
        value_set_data = self.initial_data.get('value_set', [])
        set_member_data = self.initial_data.get('set_members_input', [])
        source_mappings_data = self.initial_data.get('source_mappings_input', [])

        # Remove write-only keys from validated_data if present
        validated_data.pop('value_set', None)
        validated_data.pop('set_members_input', None)
        validated_data.pop('source_mappings_input', None)

        data_element = super().create(validated_data)

        # Create DataElementSourceMapping rows (if any)
        if source_mappings_data:
            normalized_sm = self._validate_source_mappings_list(source_mappings_data)
            for item in normalized_sm:
                DataElementSourceMapping.objects.create(
                    dataelement=data_element,
                    source_id=item['source_id'],
                    code=item['code'],
                    description=item['description']
                )

        # Create DataElementValueSet rows (if any)
        if value_set_data:
            normalized_vs = self._validate_struct_list(value_set_data, 'answer_id')
            for item in normalized_vs:
                DataElementValueSet.objects.create(
                    parent_element=data_element,
                    answer_element_id=item['id'],
                    sort_weight=item['sort_weight']
                )

        # Create DataElementSetMember rows (if any)
        if set_member_data:
            normalized_sm = self._validate_struct_list(set_member_data, 'member_id')
            for item in normalized_sm:
                DataElementSetMember.objects.create(
                    section_element=data_element,
                    member_element_id=item['id'],
                    sort_weight=item['sort_weight']
                )

        return data_element

    @transaction.atomic
    def update(self, instance, validated_data):
        value_set_data = self.initial_data.get('value_set', None)
        set_member_data = self.initial_data.get('set_members_input', None)
        source_mappings_data = self.initial_data.get('source_mappings_input', None)

        # Clean from validated_data to avoid errors
        validated_data.pop('value_set', None)
        validated_data.pop('set_members_input', None)
        validated_data.pop('source_mappings_input', None)

        data_element = super().update(instance, validated_data)

        # Update source mappings
        if source_mappings_data is not None:
            # Replace existing source mappings
            DataElementSourceMapping.objects.filter(dataelement=data_element).delete()
            normalized_sm = self._validate_source_mappings_list(source_mappings_data)
            for item in normalized_sm:
                DataElementSourceMapping.objects.create(
                    dataelement=data_element,
                    source_id=item['source_id'],
                    code=item['code'],
                    description=item['description']
                )

        # Update value set
        if value_set_data is not None:
            DataElementValueSet.objects.filter(parent_element=data_element).delete()
            normalized_vs = self._validate_struct_list(value_set_data, 'answer_id')
            for item in normalized_vs:
                DataElementValueSet.objects.create(
                    parent_element=data_element,
                    answer_element_id=item['id'],
                    sort_weight=item['sort_weight']
                )

        # Update set members
        if set_member_data is not None:
            DataElementSetMember.objects.filter(section_element=data_element).delete()
            normalized_sm = self._validate_struct_list(set_member_data, 'member_id')
            for item in normalized_sm:
                DataElementSetMember.objects.create(
                    section_element=data_element,
                    member_element_id=item['id'],
                    sort_weight=item['sort_weight']
                )

        return data_element


# -------------------------
# Supporting simple serializers
# -------------------------
class DataElementClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataElementClass
        fields = '__all__'


class DataTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataType
        fields = '__all__'


class MappingSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MappingSource
        fields = '__all__'


# -------------------------
# DataElementSourceMapping Serializer
# -------------------------
class DataElementSourceMappingSerializer(serializers.ModelSerializer):
    dataelement_name = serializers.CharField(source='dataelement.name', read_only=True)
    source_name = serializers.CharField(source='source.name', read_only=True)

    class Meta:
        model = DataElementSourceMapping
        fields = ['id', 'dataelement', 'dataelement_name', 'source', 'source_name', 
                  'code', 'description', 'created_date', 'updated_date']


class DataElementValueSetSerializer(serializers.ModelSerializer):
    parent_element_name = serializers.CharField(source='parent_element.name', read_only=True)
    answer_element_name = serializers.CharField(source='answer_element.name', read_only=True)

    class Meta:
        model = DataElementValueSet
        fields = ['id', 'parent_element', 'parent_element_name', 'answer_element', 'answer_element_name', 'sort_weight']


class DataElementSetMemberSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source='section_element.name', read_only=True)
    member_name = serializers.CharField(source='member_element.name', read_only=True)

    class Meta:
        model = DataElementSetMember
        fields = ['id', 'section_element', 'section_name', 'member_element', 'member_name', 'sort_weight']


# -------------------------
# CSV Import Serializer
# -------------------------
class CSVImportSerializer(serializers.Serializer):
    """
    Simple serializer for CSV import using existing DataElementSerializer
    """
    file = serializers.FileField()
    update_existing = serializers.BooleanField(default=False, required=False)
    
    def validate_file(self, value):
        if not value.name.lower().endswith('.csv'):
            raise serializers.ValidationError("File must be a CSV file")
        return value
    
    def create(self, validated_data):
        request = self.context.get('request')
        file = validated_data['file']
        update_existing = validated_data.get('update_existing', False)
        
        try:
            # Read and process CSV
            content = file.read().decode('utf-8-sig')
            
            # Detect delimiter
            sample = content[:1024]
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            # Parse CSV
            df = pd.read_csv(io.StringIO(content), delimiter=delimiter)
            
            results = {
                'total': len(df),
                'created': 0,
                'updated': 0,
                'failed': 0,
                'errors': []
            }
            
            # Process each row
            for index, row in df.iterrows():
                row_num = index + 2  # Account for header row
                try:
                    with transaction.atomic():
                        self.process_row(row, update_existing, request, row_num)
                        
                        if update_existing and DataElement.objects.filter(name=row['name']).exists():
                            results['updated'] += 1
                        else:
                            results['created'] += 1
                            
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append({
                        'row': row_num,
                        'name': row.get('name', 'Unknown'),
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            raise serializers.ValidationError(f"Error processing CSV: {str(e)}")
    
    def process_row(self, row, update_existing, request, row_num):
        """Process a single CSV row using existing DataElementSerializer"""
        # Map CSV columns to serializer fields
        data = {}
        
        # Required fields
        required_fields = ['name', 'label', 'class_id', 'datatype_id']
        for field in required_fields:
            if field not in row or pd.isna(row[field]):
                raise ValueError(f"Missing required field: {field}")
            data[field] = row[field]
        
        # Validate name uniqueness for creation (not for updates where we're updating existing)
        if not update_existing and DataElement.objects.filter(name=data['name']).exists():
            raise ValueError(f"DataElement with name '{data['name']}' already exists")
        
        # Optional fields
        optional_fields = {
            'unit': '',
            'length': None,
            'default_value': '',
            'required': False,
            'multi_value': False,
            'normal_min_value': None,
            'normal_max_value': None,
            'description': '',
            'status': 'active'
        }
        
        for field, default in optional_fields.items():
            if field in row and pd.notna(row[field]):
                # Handle boolean fields
                if field in ['required', 'multi_value']:
                    value = str(row[field]).lower().strip()
                    data[field] = value in ['true', 'yes', '1', 't', 'y']
                # Handle numeric fields
                elif field in ['length', 'normal_min_value', 'normal_max_value']:
                    try:
                        if str(row[field]).strip():
                            data[field] = float(row[field])
                        else:
                            data[field] = default
                    except (ValueError, TypeError):
                        data[field] = default
                else:
                    data[field] = str(row[field]).strip()
            else:
                data[field] = default
        
        # Handle source mappings if provided
        if 'source_mappings' in row and pd.notna(row['source_mappings']):
            try:
                mappings = json.loads(row['source_mappings'])
                if isinstance(mappings, list):
                    data['source_mappings_input'] = mappings
            except:
                pass  # Skip if invalid JSON
        
        # Handle value set if provided
        if 'value_set' in row and pd.notna(row['value_set']):
            try:
                value_set = json.loads(row['value_set'])
                if isinstance(value_set, list):
                    data['value_set'] = [
                        {'answer_id': int(answer_id), 'sort_weight': idx + 1}
                        for idx, answer_id in enumerate(value_set)
                    ]
            except:
                pass  # Skip if invalid JSON
        
        # Handle set members if provided
        if 'set_members' in row and pd.notna(row['set_members']):
            try:
                members = json.loads(row['set_members'])
                if isinstance(members, list):
                    data['set_members_input'] = [
                        {'member_id': int(member_id), 'sort_weight': idx + 1}
                        for idx, member_id in enumerate(members)
                    ]
            except:
                pass  # Skip if invalid JSON
        
        # Check if element exists for update
        if update_existing:
            existing = DataElement.objects.filter(name=data['name']).first()
            if existing:
                serializer = DataElementSerializer(
                    existing, 
                    data=data, 
                    context={'request': request},
                    partial=True
                )
                if serializer.is_valid():
                    return serializer.save()
                else:
                    raise ValueError(f"Validation errors: {serializer.errors}")
        
        # Create new element
        serializer = DataElementSerializer(
            data=data, 
            context={'request': request}
        )
        if serializer.is_valid():
            return serializer.save()
        else:
            raise ValueError(f"Validation errors: {serializer.errors}")


class DataElementLightSerializer(serializers.ModelSerializer):
    """
    Ultra-lightweight serializer that only returns id and name
    Used for the lightweight list endpoint
    """
    class Meta:
        model = DataElement
        fields = ['id', 'name', 'label']


# -------------------------
# Immediate Set Member Serializers (NEW)
# -------------------------
class ImmediateSetMemberSerializer(serializers.Serializer):
    """
    Serializer for immediate set members matching existing API structure
    Returns member info with id, name, label, description
    """
    id = serializers.IntegerField()
    member_element = serializers.SerializerMethodField()
    sort_weight = serializers.IntegerField()
    
    def get_member_element(self, obj):
        return {
            'id': obj.member_element.id,
            'name': obj.member_element.name,
            'label': obj.member_element.label,
            'description': obj.member_element.description
        }