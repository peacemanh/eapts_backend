from rest_framework import serializers
from apps.person.models.patient import Patient
from apps.person.serializers.person_serializer import PersonSerializer


class PatientSerializer(serializers.ModelSerializer):
    person_detail = PersonSerializer(source='person', read_only=True)

    class Meta:
        model = Patient
        fields = ['id', 'person', 'person_detail', 'medical_record_number']
