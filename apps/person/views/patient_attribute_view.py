from rest_framework import generics
from apps.person.models.patient import PatientAttributeType, PatientAttribute
from apps.person.serializers.patient_attribute_serializer import (
    PatientAttributeTypeSerializer,
    PatientAttributeSerializer
)


class PatientAttributeTypeListCreateView(generics.ListCreateAPIView):
    queryset = PatientAttributeType.objects.all()
    serializer_class = PatientAttributeTypeSerializer


class PatientAttributeTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PatientAttributeType.objects.all()
    serializer_class = PatientAttributeTypeSerializer


class PatientAttributeListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientAttributeSerializer

    def get_queryset(self):
        queryset = PatientAttribute.objects.all()
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset

class PatientAttributeDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PatientAttribute.objects.all()
    serializer_class = PatientAttributeSerializer
