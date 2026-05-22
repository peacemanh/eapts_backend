# apps/person/utils/query_optimization.py
from django.db import models
from django.apps import apps

class AddressQueryOptimizer:
    """Utility to optimize address-related queries with parent hierarchy"""
    
    @staticmethod
    def optimize_person_queryset(queryset, include_full_hierarchy=False):
        """
        Optimize person queryset based on address hierarchy needs
        Uses the same pattern as Location views
        """
        # Use the exact same pattern as LocationListCreate view
        queryset = queryset.select_related(
            'location',
            'location__parent',
            'location__address',
            'location__address__address_level'
        ).prefetch_related(
            'names',
            'location__tags'  # This matches the Location views pattern
        )
        
        if include_full_hierarchy:
            # Use the same parent chain optimization as address views
            queryset = AddressQueryOptimizer._add_parent_hierarchy(queryset)
        
        return queryset
    
    @staticmethod
    def _add_parent_hierarchy(queryset, max_depth=5):
        """
        Use the same parent chain optimization as AddressEntryViewSet
        """
        select_related_fields = [
            'location__address',
            'location__address__address_level',
            'location__address__parent',
            'location__address__parent__address_level'
        ]
        
        # Build parent chain dynamically - same as address views
        parent_chain = 'location__address__parent'
        for depth in range(2, max_depth + 1):
            parent_field = f'{parent_chain}__parent'
            parent_level_field = f'{parent_chain}__parent__address_level'
            
            select_related_fields.extend([parent_field, parent_level_field])
            parent_chain = parent_field
        
        return queryset.select_related(*select_related_fields)