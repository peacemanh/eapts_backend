from django.contrib import admin
from .models import AggregateRecord

@admin.register(AggregateRecord)
class AggregateRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'form', 'data_element', 'value_text', 'value_numeric', 'value_coded', 'value_datetime', 'date_created', 'date_updated')
    list_filter = ('form', 'data_element', 'value_coded', 'date_created')
    search_fields = ('data_element__name', 'form__name', 'value_text', 'value_coded__name')
