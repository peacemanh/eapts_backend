from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from apps.person.models.person import Person, PersonName
from apps.person.serializers.person_serializer import (
    PersonSerializer, PersonNameSerializer, PersonCreateSerializer,
    PersonLocationUpdateSerializer, PersonWithAddressSerializer
)


class BasePersonView:
    """Base view with common person functionality"""
    
    def get_optimized_queryset(self, include_full_hierarchy=False):
        """Centralized query optimization"""
        queryset = Person.objects.all()
        return queryset
    
    def apply_filters(self, queryset):
        """Apply common filters"""
        params = self.request.query_params
        
        # Gender filter
        if gender := params.get('gender'):
            queryset = queryset.filter(gender=gender)
            
        # Birthdate range filters
        if birthdate_from := params.get('birthdate_from'):
            queryset = queryset.filter(birthdate__gte=birthdate_from)
            
        if birthdate_to := params.get('birthdate_to'):
            queryset = queryset.filter(birthdate__lte=birthdate_to)
        
        # Location-based filters
        if location_id := params.get('location_id'):
            queryset = queryset.filter(location_id=location_id)
            
        if location_name := params.get('location_name'):
            queryset = queryset.filter(location__name__icontains=location_name)
        
        # Address-based filters
        if address_name := params.get('address_name'):
            queryset = queryset.filter(location__address__name__icontains=address_name)
            
        if address_level := params.get('address_level'):
            queryset = queryset.filter(location__address__address_level__name__icontains=address_level)
        
        # Geographic filters
        if has_coordinates := params.get('has_coordinates'):
            if has_coordinates.lower() in ('true', '1', 'yes'):
                queryset = queryset.filter(
                    location__address__latitude__isnull=False,
                    location__address__longitude__isnull=False
                )
            elif has_coordinates.lower() in ('false', '0', 'no'):
                queryset = queryset.filter(
                    location__address__latitude__isnull=True,
                    location__address__longitude__isnull=True
                )
        
        return queryset.order_by('-created_at')


class PersonListCreateView(BasePersonView, generics.ListCreateAPIView):
    serializer_class = PersonSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['gender', 'location']
    search_fields = ['names__given_name', 'names__last_name', 'contact_info']
    ordering_fields = ['created_at', 'birthdate']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PersonCreateSerializer
        
        # Use detailed serializer when requested
        include_address = self.request.query_params.get('include_address', '').lower() in ('true', '1', 'yes')
        return PersonWithAddressSerializer if include_address else PersonSerializer
    
    def get_queryset(self):
        include_full_hierarchy = self.get_serializer_class() == PersonWithAddressSerializer
        queryset = self.get_optimized_queryset(include_full_hierarchy)
        return self.apply_filters(queryset)
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except ValidationError as e:
            # Return validation errors properly
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': _('Failed to create person. Please try again.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PersonDetailView(BasePersonView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PersonSerializer
    lookup_field = 'id'
    
    def get_serializer_class(self):
        include_address = self.request.query_params.get('include_address', '').lower() in ('true', '1', 'yes')
        return PersonWithAddressSerializer if include_address else PersonSerializer
    
    def get_queryset(self):
        include_full_hierarchy = self.get_serializer_class() == PersonWithAddressSerializer
        return self.get_optimized_queryset(include_full_hierarchy)
    
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(queryset, id=self.kwargs['id'])
        self.check_object_permissions(self.request, obj)
        return obj
    
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': _('Failed to update person. Please try again.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {'error': _('Failed to delete person. Please try again.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def address_details(self, request, *args, **kwargs):
        """Get detailed address information with optimized query"""
        person = get_object_or_404(
            self.get_optimized_queryset(include_full_hierarchy=True),
            id=self.kwargs['id']
        )
        serializer = PersonWithAddressSerializer(person, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['patch'], url_path='update-location')
    def update_location(self, request, *args, **kwargs):
        """Custom action to update only the location"""
        person = self.get_object()
        serializer = PersonLocationUpdateSerializer(
            person, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    serializer.save()
                    return Response(serializer.data)
            except Exception as e:
                return Response(
                    {'error': _('Failed to update location. Please try again.')},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PersonNameListCreateView(generics.ListCreateAPIView):
    serializer_class = PersonNameSerializer
    
    def get_queryset(self):
        person_id = self.kwargs.get('person_id')
        if person_id:
            return PersonName.objects.filter(person_id=person_id).select_related('person', 'person__location')
        return PersonName.objects.all().select_related('person', 'person__location')
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        person_id = self.kwargs.get('person_id')
        if person_id:
            context['person_id'] = person_id
        return context
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': _('Failed to create person name. Please try again.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PersonNameDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PersonNameSerializer
    lookup_field = 'id'
    
    def get_queryset(self):
        return PersonName.objects.all().select_related('person', 'person__location')
    
    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert lookup_url_kwarg in self.kwargs, (
            'Expected view %s to be called with a URL keyword argument '
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            'attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )
        
        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        obj = get_object_or_404(queryset, **filter_kwargs)
        
        self.check_object_permissions(self.request, obj)
        return obj
    
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': _('Failed to update person name. Please try again.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            person = instance.person
            was_preferred = instance.preferred
            
            response = super().destroy(request, *args, **kwargs)
            
            if was_preferred and person.names.exists():
                new_preferred = person.names.first()
                new_preferred.preferred = True
                new_preferred.save()
            
            return response
            
        except Exception as e:
            return Response(
                {'error': _('Failed to delete person name. Please try again.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )