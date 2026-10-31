# apps/obs/admin.py
from django.contrib import admin
from .models import Obs


@admin.register(Obs)
class ObsAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'uuid',
        'record_id',
        'person_id',
        'encounter_id',
        'form',
        'data_element',
        'group',
        'value_text',
        'value_numeric',
        'value_coded',
        'value_datetime',
        'institution',
        'location',
        'created_by',
        'updated_by',
        'date_created',
        'date_updated',
    )

    list_filter = (
        'form',
        'data_element',
        'group',
        'value_coded',
        'institution',
        'location',
        'date_created',
        'date_updated',
    )

    search_fields = (
        'record_id',
        'person_id',
        'encounter_id',
        'data_element__name',
        'form__name',
        'group__name',
        'value_text',
        'value_coded__name',
    )

    readonly_fields = (
        'id',
        'uuid',
        'date_created',
        'date_updated',
    )

    ordering = ('-date_created',)

    list_per_page = 50