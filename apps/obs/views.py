from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.obs.models import Obs
from apps.obs.serializers import (
    ObsListDetailSerializer,
    ObsCreateUpdateSerializer,
)


class ObsViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'record_id': ['exact', 'icontains'],
        'person_id': ['exact'],
        'encounter_id': ['exact'],
        'form': ['exact'],
        'data_element': ['exact'],
        'group': ['exact', 'isnull'],
        'institution': ['exact'],
        'location': ['exact'],
        'created_by': ['exact'],
        'date_created': ['gte', 'lte', 'exact'],
    }
    
    search_fields = ['record_id', 'person_id', 'encounter_id', 'value_text']
    ordering_fields = ['date_created', 'date_updated', 'record_id']
    ordering = ['-date_created']

    def get_queryset(self):
        return Obs.objects.select_related(
            'data_element', 'form', 'group', 'institution',
            'location', 'value_coded', 'created_by', 'updated_by',
        ).all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ObsCreateUpdateSerializer
        return ObsListDetailSerializer

    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)