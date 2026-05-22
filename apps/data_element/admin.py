# apps/data_element/admin.py
from django.contrib import admin
from .models import (
    DataElementClass,
    DataType,
    MappingSource,
    DataElement,
    DataElementValueSet
)

@admin.register(DataElementClass)
class DataElementClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status')
    search_fields = ('name',)

@admin.register(DataType)
class DataTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(MappingSource)
class MappingSourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'url')
    search_fields = ('name',)

@admin.register(DataElement)
class DataElementAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'label', 'class_id', 'datatype_id', 'status')
    search_fields = ('name', 'label', 'description')
    list_filter = ('class_id', 'datatype_id', 'status')

@admin.register(DataElementValueSet)
class DataElementValueSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent_element', 'answer_element')
    search_fields = ('parent_element__name', 'answer_element__name')

