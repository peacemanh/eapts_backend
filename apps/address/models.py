import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex  # If using PostgreSQL
from django.contrib.postgres.search import SearchVectorField  # If using PostgreSQL


class AddressLevel(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        verbose_name = "Address Level"
        verbose_name_plural = "Address Levels"
        indexes = [
            # For filtering active levels and ordering
            models.Index(fields=['is_active', 'order']),
            models.Index(fields=['order', 'is_active']),
            # For quick lookups by code
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class AddressEntry(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=150)
    address_level = models.ForeignKey(AddressLevel, on_delete=models.CASCADE)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children'
    )
    address_code = models.CharField(max_length=50, blank=True, null=True)

    # NEW — Geographic coordinates
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    # Optional: For advanced text search (PostgreSQL only)
    # search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        unique_together = ('name', 'address_level', 'parent')
        ordering = ['address_level__order', 'name']
        verbose_name = "Address Entry"
        verbose_name_plural = "Address Entries"
        
        # CRITICAL PERFORMANCE INDEXES
        indexes = [
            # Primary filtering indexes
            models.Index(fields=['is_active']),
            models.Index(fields=['is_active', 'address_level']),
            models.Index(fields=['is_active', 'parent']),
            models.Index(fields=['is_active', 'address_level', 'parent']),
            
            # Hierarchical query optimization
            models.Index(fields=['parent', 'is_active']),
            models.Index(fields=['address_level', 'is_active']),
            models.Index(fields=['parent', 'address_level', 'is_active']),
            
            # Name search optimization
            models.Index(fields=['name']),
            models.Index(fields=['is_active', 'name']),
            models.Index(fields=['name', 'address_level']),
            
            # Geographic queries
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['is_active', 'latitude', 'longitude']),
            
            # UUID for quick lookups
            models.Index(fields=['uuid']),
            
            # Address code searches
            models.Index(fields=['address_code']),
            models.Index(fields=['is_active', 'address_code']),
        ]
        
        # PostgreSQL-specific indexes for better text search
        # indexes = [
        #     GinIndex(fields=['name']),  # GIN index for faster text search
        #     GinIndex(fields=['search_vector']),  # For full-text search
        # ]

    def __str__(self):
        return self.name

    # NEW — full hierarchical path
    @property
    def full_path(self):
        path = [self.name]
        parent = self.parent
        while parent is not None:
            path.append(parent.name)
            parent = parent.parent
        return " / ".join(reversed(path))