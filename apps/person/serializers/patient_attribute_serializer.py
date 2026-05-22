from rest_framework import serializers
from apps.person.models.patient import PatientAttributeType, PatientAttribute


class PatientAttributeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientAttributeType
        fields = ['id', 'name', 'description', 'datatype', 'options', 'is_active']


class PatientAttributeSerializer(serializers.ModelSerializer):
    attribute_type_detail = PatientAttributeTypeSerializer(source='attribute_type', read_only=True)

    class Meta:
        model = PatientAttribute
        fields = [
            'id',
            'patient',
            'attribute_type',
            'attribute_type_detail',
            'value',
            'date_created',
            'date_updated',
        ]