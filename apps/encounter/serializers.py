from rest_framework import serializers
from .models import Encounter

class EncounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Encounter
        fields = ['id', 'uuid', 'date_created', 'date_updated']
        read_only_fields = ['id', 'uuid', 'date_created', 'date_updated']
