# apps/locations/models.py

from django.db import models

from apps.address.models import AddressEntry

class LocationTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children'
    )
    # Use ForeignKey to AddressEntry instead of plain text
    address = models.ForeignKey(AddressEntry, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)  # Replaces contact_info

    # Many-to-many via LocationTagMap
    tags = models.ManyToManyField(LocationTag, through='LocationTagMap', related_name='locations')

    def __str__(self):
        return self.name


class LocationTagMap(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    location_tag = models.ForeignKey(LocationTag, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('location', 'location_tag')

    def __str__(self):
        return f"{self.location.name} - {self.location_tag.name}"
