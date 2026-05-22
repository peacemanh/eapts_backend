from django.contrib import admin
from .models import Encounter

@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'date_created', 'date_updated')
    search_fields = ('uuid',)
    readonly_fields = ('uuid', 'date_created', 'date_updated')
    ordering = ('-date_created',)
