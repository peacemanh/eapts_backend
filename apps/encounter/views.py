from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from .models import Encounter
from .serializers import EncounterSerializer

class EncounterViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Encounters to be viewed or edited.
    """
    queryset = Encounter.objects.all()
    serializer_class = EncounterSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ['date_created', 'date_updated']
    search_fields = ['uuid']

    # You can override create, update, delete if you want custom logic
