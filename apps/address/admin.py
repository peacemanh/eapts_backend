from django.contrib import admin
from .models import AddressLevel, AddressEntry


@admin.register(AddressLevel)
class AddressLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('order',)


@admin.register(AddressEntry)
class AddressEntryAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'address_level', 'parent', 'address_code',
        'latitude', 'longitude', 'is_active'
    )
    list_filter = ('address_level', 'is_active')
    search_fields = ('name', 'address_code')
    autocomplete_fields = ('parent', 'address_level')
