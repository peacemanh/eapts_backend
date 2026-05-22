# apps/data_element/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count, Prefetch
import csv
from django.http import HttpResponse

from .models import (
    DataElementClass,
    DataType,
    MappingSource,
    DataElement,
    DataElementValueSet,
    DataElementSetMember,
    DataElementSourceMapping,
)
from .serializers import (
    DataElementClassSerializer,
    DataTypeSerializer,
    MappingSourceSerializer,
    DataElementSerializer,
    DataElementValueSetSerializer,
    DataElementSetMemberSerializer,
    DataElementSourceMappingSerializer,
    CSVImportSerializer,
    DataElementListSerializer,
    ImmediateSetMemberSerializer,
    AnswerElementSearchSerializer,
)

# ----------------------------
# Custom Pagination Classes
# ----------------------------
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'total_pages': self.page.paginator.num_pages,
            'results': data
        })


class DataElementPagination(StandardResultsSetPagination):
    page_size = 10
    
    def paginate_queryset(self, queryset, request, view=None):
        # Get search parameter
        search_query = request.query_params.get('search', '')
        
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(label__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(class_id__name__icontains=search_query) |
                Q(datatype_id__name__icontains=search_query)
            ).distinct()
        
        return super().paginate_queryset(queryset, request, view)


# ----------------------------
# Metadata CRUD views
# ----------------------------
class DataElementClassViewSet(viewsets.ModelViewSet):
    queryset = DataElementClass.objects.all()
    serializer_class = DataElementClassSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'id']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class DataTypeViewSet(viewsets.ModelViewSet):
    queryset = DataType.objects.all()
    serializer_class = DataTypeSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'id']


class MappingSourceViewSet(viewsets.ModelViewSet):
    queryset = MappingSource.objects.all()
    serializer_class = MappingSourceSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'id']


# ----------------------------
# Data Element CRUD with nested value set answers
# ----------------------------
class DataElementViewSet(viewsets.ModelViewSet):
    queryset = DataElement.objects.select_related(
        'class_id', 'datatype_id'
    ).prefetch_related(
        'source_mappings__source',
        'value_set_parents__answer_element',
        'section_set_members__member_element'
    )
    pagination_class = DataElementPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'label', 'description']
    ordering_fields = ['name', 'id', 'created_date', 'updated_date']
    
    def get_serializer_class(self):
        """
        Use different serializers for list vs detail views
        """
        if self.action == 'list':
            return DataElementListSerializer
        return DataElementSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by class if provided
        class_id = self.request.query_params.get('class_id', None)
        if class_id:
            queryset = queryset.filter(class_id=class_id)
        
        # Filter by data type if provided
        datatype_id = self.request.query_params.get('datatype_id', None)
        if datatype_id:
            queryset = queryset.filter(datatype_id=datatype_id)
        
        # Advanced search across related fields
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(label__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(class_id__name__icontains=search_query) |
                Q(datatype_id__name__icontains=search_query) |
                Q(source_mappings__code__icontains=search_query) |
                Q(source_mappings__source__name__icontains=search_query)
            ).distinct()
        
        return queryset
    
    @action(detail=False, methods=['get'], url_path='get-answer-details')
    def get_answer_details(self, request):
        """
        Get details of specific answer elements by their IDs.
        Used when we have the ID but need the label/name.
        
        URL: /api/data-element/data-elements/get-answer-details/?ids=123,456,789
        
        Query Parameters:
        - ids: comma-separated list of answer element IDs
        - include_source_mappings: include source mappings (optional, defaults to false)
        
        Returns list of answer elements with their details.
        """
        # Get ids from query params
        ids_param = request.query_params.get('ids', '')
        include_source_mappings = request.query_params.get('include_source_mappings', 'false').lower() == 'true'
        
        if not ids_param:
            return Response(
                {'error': 'No IDs provided. Please provide comma-separated IDs in the "ids" parameter.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse IDs
        try:
            id_list = [int(id_str.strip()) for id_str in ids_param.split(',') if id_str.strip()]
        except ValueError:
            return Response(
                {'error': 'Invalid ID format. Please provide comma-separated integers.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not id_list:
            return Response(
                {'error': 'No valid IDs provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Fetch the data elements
        queryset = DataElement.objects.filter(id__in=id_list)
        
        if include_source_mappings:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'source_mappings',
                    queryset=DataElementSourceMapping.objects.select_related('source').only(
                        'id', 'source_id', 'code', 'dataelement_id', 'source__id', 'source__name'
                    )[:3]
                )
            )
        
        # Build results
        results = []
        for element in queryset:
            source_mappings_data = []
            if include_source_mappings:
                source_mappings_data = [
                    {
                        'id': sm.id,
                        'source_id': sm.source_id,
                        'source_name': sm.source.name if sm.source else None,
                        'code': sm.code
                    }
                    for sm in element.source_mappings.all()
                ]
            
            results.append({
                'id': element.id,
                'name': element.name,
                'label': element.label,
                'description': element.description,
                'source_mappings': source_mappings_data if include_source_mappings else []
            })
        
        return Response({
            'requested_ids': id_list,
            'found_count': len(results),
            'results': results
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get statistics about data elements"""
        queryset = self.get_queryset()
        total = queryset.count()
        active = queryset.filter(status='active').count()
        inactive = queryset.filter(status='inactive').count()
        
        # Count by class
        classes = DataElementClass.objects.annotate(
            element_count=Count('data_elements')
        ).values('id', 'name', 'element_count')
        
        # Count by data type
        types = DataType.objects.annotate(
            element_count=Count('data_elements')
        ).values('id', 'name', 'element_count')
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive,
            'by_class': list(classes),
            'by_type': list(types),
        })
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export data elements to CSV"""
        queryset = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="data_elements_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Name', 'Label', 'Class', 'Data Type', 'Unit', 
            'Length', 'Default Value', 'Required', 'Multi Value',
            'Normal Min', 'Normal Max', 'Description', 'Status',
            'Created Date', 'Updated Date'
        ])
        
        for element in queryset:
            writer.writerow([
                element.id,
                element.name,
                element.label,
                element.class_id.name if element.class_id else '',
                element.datatype_id.name if element.datatype_id else '',
                element.unit or '',
                element.length or '',
                element.default_value or '',
                'Yes' if element.required else 'No',
                'Yes' if element.multi_value else 'No',
                element.normal_min_value or '',
                element.normal_max_value or '',
                element.description or '',
                element.status,
                element.created_date.strftime('%Y-%m-%d %H:%M:%S'),
                element.updated_date.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    
    @action(detail=False, methods=['get'], url_path='lightweight')
    def lightweight_list(self, request):
        """
        Get only data element IDs and names.
        Supports conditional pagination:
        - If page_size is provided, returns paginated results
        - If no page_size, returns ALL results (unpaginated)
        
        Query params:
        - page_size: (optional) if provided, enables pagination
        - page: page number for pagination
        - search: (optional) search in name field
        - status: (optional) filter by status
        - class_id: (optional) filter by class
        - datatype_id: (optional) filter by data type
        """
        # Get base queryset with filters applied
        queryset = self.filter_queryset(self.get_queryset())
        
        # Apply search if provided (search in name only for this lightweight endpoint)
        search_query = request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
        
        # Check if pagination is requested
        page_size = request.query_params.get('page_size', None)
        
        if page_size is not None:
            # Enable pagination
            try:
                page_size = int(page_size)
                # Use the existing pagination class but allow page_size override
                paginator = self.pagination_class()
                paginator.page_size = page_size
                
                # Paginate the queryset
                page = paginator.paginate_queryset(queryset, request, view=self)
                
                if page is not None:
                    # Manual data construction for maximum performance
                    data = [{'id': item.id, 'name': item.name, 'label': item.label} for item in page]
                    return paginator.get_paginated_response(data)
                    
            except (ValueError, TypeError):
                # If invalid page_size, return error
                return Response(
                    {'error': 'Invalid page_size parameter. Must be an integer.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # No pagination - return all results
        data = [{'id': item.id, 'name': item.name, 'label': item.label} for item in queryset]
        return Response(data)

    # ----------------------------
    # Answer Element Search Endpoint
    # ----------------------------
    @action(detail=True, methods=['get'], url_path='search-answers')
    def search_answers(self, request, pk=None):
        """
        Search answer elements for a specific parent element.
        
        URL: /api/data-element/elements/{parent_element_id}/search-answers/?q=search_term
        
        Query Parameters:
        - q: search string (minimum 3 characters) - REQUIRED
        - page: page number (optional, defaults to 1)
        - page_size: number of results per page (optional, defaults to 50)
        - include_source_mappings: include source mappings (optional, defaults to true)
        - source_mappings_limit: limit source mappings per answer (optional, defaults to 3)
        
        Returns paginated list of answer elements matching the search term.
        """
        try:
            # Get the parent element
            parent_element = self.get_object()
        except DataElement.DoesNotExist:
            return Response(
                {'error': 'Parent DataElement not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get search query parameter
        search_query = request.query_params.get('q', '').strip()
        
        # Validate minimum length requirement (3 characters)
        if len(search_query) < 3:
            return Response(
                {
                    'error': 'Search query must be at least 3 characters long',
                    'current_length': len(search_query),
                    'minimum_required': 3
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get optional parameters
        include_source_mappings = request.query_params.get('include_source_mappings', 'true').lower() == 'true'
        source_mappings_limit = int(request.query_params.get('source_mappings_limit', 3))
        
        # Get pagination parameters
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 50))
            
            # Validate pagination parameters
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 50
            if page_size > 200:  # Max page size to prevent abuse
                page_size = 200
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid pagination parameters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get all answer element IDs for this parent element
        answer_element_ids = DataElementValueSet.objects.filter(
            parent_element=parent_element
        ).values_list('answer_element_id', flat=True).distinct()
        
        # Build optimized queryset with prefetching
        base_qs = DataElement.objects.filter(id__in=answer_element_ids)
        
        # Apply search filter early to reduce dataset
        filtered_qs = base_qs.filter(
            Q(name__icontains=search_query) |
            Q(label__icontains=search_query) |
            Q(description__icontains=search_query)
        )
        
        # Get total count before applying more complex operations
        total_count = filtered_qs.count()
        
        # If no results, return early
        if total_count == 0:
            return Response({
                'parent_element_id': parent_element.id,
                'parent_element_name': parent_element.name,
                'search_query': search_query,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': 0,
                    'total_pages': 0,
                    'has_next': False,
                    'has_previous': False
                },
                'results': []
            })
        
        # Apply prefetching based on whether source mappings are needed
        if include_source_mappings:
            # Prefetch source mappings with limited data
            filtered_qs = filtered_qs.prefetch_related(
                Prefetch(
                    'source_mappings',
                    queryset=DataElementSourceMapping.objects.select_related('source').only(
                        'id', 'source_id', 'code', 'dataelement_id', 'source__id', 'source__name'
                    )[:source_mappings_limit],
                    to_attr='prefetched_source_mappings'
                )
            ).only('id', 'name', 'label', 'description')
        else:
            # Only get basic fields
            filtered_qs = filtered_qs.only('id', 'name', 'label', 'description')
        
        # Apply ordering and pagination
        ordered_qs = filtered_qs.order_by('name')
        paginated_qs = ordered_qs[offset:offset + page_size]
        
        # Pre-fetch all sort weights in one query for efficiency
        paginated_ids = [ae.id for ae in paginated_qs]
        
        sort_weights = {
            vs.answer_element_id: vs.sort_weight
            for vs in DataElementValueSet.objects.filter(
                parent_element=parent_element,
                answer_element_id__in=paginated_ids
            ).only('answer_element_id', 'sort_weight')
        }
        
        # Build results using prefetched data
        results = []
        for answer_element in paginated_qs:
            # Prepare source mappings if needed
            source_mappings_data = []
            if include_source_mappings:
                # Use prefetched source mappings if available
                if hasattr(answer_element, 'prefetched_source_mappings'):
                    source_mappings = answer_element.prefetched_source_mappings
                else:
                    source_mappings = answer_element.source_mappings.select_related('source').all()[:source_mappings_limit]
                
                source_mappings_data = [
                    {
                        'id': sm.id,
                        'source_id': sm.source_id,
                        'source_name': sm.source.name if sm.source else None,
                        'code': sm.code
                    }
                    for sm in source_mappings
                ]
            
            results.append({
                'id': answer_element.id,
                'name': answer_element.name,
                'label': answer_element.label,
                'description': answer_element.description,
                'sort_weight': sort_weights.get(answer_element.id, 0),
                'source_mappings': source_mappings_data if include_source_mappings else []
            })
        
        # Calculate pagination metadata
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
        
        return Response({
            'parent_element_id': parent_element.id,
            'parent_element_name': parent_element.name,
            'search_query': search_query,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_previous': page > 1
            },
            'results': results
        })

    # ----------------------------
    # Debug Endpoint for Answer Elements
    # ----------------------------
    @action(detail=True, methods=['get'], url_path='debug-answer-elements')
    def debug_answer_elements(self, request, pk=None):
        """
        Debug endpoint to see all answer elements for a parent and test search.
        
        URL: /api/data-element/data-elements/{parent_element_id}/debug-answer-elements/?q=search_term
        
        Query Parameters:
        - q: (optional) search term to test matching
        """
        try:
            # Get the parent element
            parent_element = self.get_object()
        except DataElement.DoesNotExist:
            return Response(
                {'error': 'Parent DataElement not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get optional search query parameter for testing
        test_search = request.query_params.get('q', '').strip()
        
        # Get all answer elements for this parent
        answer_elements_qs = DataElement.objects.filter(
            value_set_answers__parent_element=parent_element
        ).distinct()
        
        # Get all answer elements with their details
        all_answer_elements = answer_elements_qs.values(
            'id', 
            'name', 
            'label', 
            'description'
        ).order_by('name')
        
        # Get the relationship info
        relationships = DataElementValueSet.objects.filter(
            parent_element=parent_element
        ).select_related('answer_element').values(
            'answer_element__id',
            'answer_element__name',
            'answer_element__label',
            'sort_weight'
        ).order_by('sort_weight')
        
        # Build response
        response_data = {
            'parent_element': {
                'id': parent_element.id,
                'name': parent_element.name,
                'label': parent_element.label
            },
            'total_answer_elements': all_answer_elements.count(),
            'all_answer_elements': list(all_answer_elements),
            'relationships': list(relationships),
        }
        
        # If a test search term is provided, show matching results
        if test_search and len(test_search) >= 1:
            # Test different search methods
            icontains_matches = answer_elements_qs.filter(
                Q(name__icontains=test_search) |
                Q(label__icontains=test_search) |
                Q(description__icontains=test_search)
            ).values('id', 'name', 'label', 'description')
            
            startswith_matches = answer_elements_qs.filter(
                Q(name__startswith=test_search) |
                Q(label__startswith=test_search) |
                Q(description__startswith=test_search)
            ).values('id', 'name', 'label', 'description')
            
            contains_matches = answer_elements_qs.filter(
                Q(name__contains=test_search) |
                Q(label__contains=test_search) |
                Q(description__contains=test_search)
            ).values('id', 'name', 'label', 'description')
            
            exact_matches = answer_elements_qs.filter(
                Q(name__iexact=test_search) |
                Q(label__iexact=test_search) |
                Q(description__iexact=test_search)
            ).values('id', 'name', 'label', 'description')
            
            response_data['search_test'] = {
                'search_term': test_search,
                'icontains_matches': {
                    'count': icontains_matches.count(),
                    'results': list(icontains_matches)
                },
                'startswith_matches': {
                    'count': startswith_matches.count(),
                    'results': list(startswith_matches)
                },
                'contains_matches': {
                    'count': contains_matches.count(),
                    'results': list(contains_matches)
                },
                'exact_matches': {
                    'count': exact_matches.count(),
                    'results': list(exact_matches)
                }
            }
        
        return Response(response_data)

    # ----------------------------
    # Immediate Set Members Endpoints
    # ----------------------------
    @action(detail=True, methods=['get'], url_path='immediate-setmembers')
    def immediate_setmembers(self, request, pk=None):
        """
        Get immediate set members for a specific DataElement (section type)
        Returns member info matching frontend expectation with set_members array
        and member_detail objects
        
        URL: /api/data-element/elements/{id}/immediate-setmembers/
        """
        try:
            # Get the main data element
            data_element = self.get_object()
        except DataElement.DoesNotExist:
            return Response(
                {'error': 'DataElement not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all set members for this element (where it's the section_element)
        # Optimized query: only fetch needed fields
        set_members = DataElementSetMember.objects.filter(
            section_element=data_element
        ).select_related(
            'member_element'
        ).only(
            'id',
            'sort_weight',
            'member_element__id',
            'member_element__name',
            'member_element__label',
            'member_element__description'
        ).order_by('sort_weight', 'id')
        
        # Build response structure that matches frontend expectation
        set_members_data = []
        for sm in set_members:
            set_members_data.append({
                'id': sm.id,
                'member_detail': {
                    'id': sm.member_element.id,
                    'name': sm.member_element.name,
                    'label': sm.member_element.label,
                    'description': sm.member_element.description
                },
                'sort_weight': sm.sort_weight
            })
        
        return Response({
            'id': data_element.id,
            'name': data_element.name,
            'label': data_element.label,
            'description': data_element.description,
            'set_members': set_members_data
        })
    
    def handle_exception(self, exc):
        """
        Override to provide better error messages for duplicate names
        """
        from django.db import IntegrityError
        
        if isinstance(exc, IntegrityError) and 'unique constraint' in str(exc).lower() and 'name' in str(exc).lower():
            return Response(
                {'detail': 'A DataElement with this name already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().handle_exception(exc)


# ----------------------------
# Value Set CRUD
# ----------------------------
class DataElementValueSetViewSet(viewsets.ModelViewSet):
    queryset = DataElementValueSet.objects.select_related('parent_element', 'answer_element').all()
    serializer_class = DataElementValueSetSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'parent_element__name',
        'answer_element__name',
    ]
    ordering_fields = ['sort_weight', 'id']


# ----------------------------
# Set Member CRUD (for Section type DataElements)
# ----------------------------
class DataElementSetMemberViewSet(viewsets.ModelViewSet):
    queryset = DataElementSetMember.objects.select_related('section_element', 'member_element').all()
    serializer_class = DataElementSetMemberSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'section_element__name',
        'member_element__name',
    ]
    ordering_fields = ['sort_weight', 'id']


# ----------------------------
# Data Element Source Mapping CRUD
# ----------------------------
class DataElementSourceMappingViewSet(viewsets.ModelViewSet):
    queryset = DataElementSourceMapping.objects.select_related('dataelement', 'source').all()
    serializer_class = DataElementSourceMappingSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'dataelement__name',
        'source__name',
        'code',
        'description'
    ]
    ordering_fields = ['source__name', 'code', 'id']


# ----------------------------
# CSV Import ViewSet
# ----------------------------
class CSVImportViewSet(viewsets.ViewSet):
    """
    Simple ViewSet for CSV import operations
    """
    parser_classes = [MultiPartParser, FormParser]
    
    @action(detail=False, methods=['post'])
    def upload(self, request):
        """
        Upload and import CSV file
        """
        serializer = CSVImportSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            results = serializer.save()
            return Response({
                'success': True,
                'message': 'CSV import completed',
                'results': results
            })
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=400)
    
    @action(detail=False, methods=['get'])
    def template(self, request):
        """
        Download CSV template
        """
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="data_elements_template.csv"'
        
        writer = csv.writer(response)
        
        # Headers
        headers = [
            'name', 'label', 'class_id', 'datatype_id', 
            'unit', 'length', 'default_value', 'required', 
            'multi_value', 'normal_min_value', 'normal_max_value',
            'description', 'status', 'source_mappings', 
            'value_set', 'set_members'
        ]
        writer.writerow(headers)
        
        # Example data (using IDs that likely exist)
        examples = [
            [
                'patient_age', 'Patient Age', '1', '1',
                'years', '', '', 'true', 'false',
                '0', '120', 'Patient age in years', 'active',
                '[{"source_id": 1, "code": "AGE", "description": "Patient age"}]',
                '', ''
            ],
            [
                'gender', 'Gender', '1', '2',
                '', '', '', 'true', 'false',
                '', '', 'Biological gender', 'active',
                '[{"source_id": 2, "code": "GENDER", "description": "Patient gender"}]',
                '[1, 2, 3]', ''
            ],
        ]
        
        for example in examples:
            writer.writerow(example)
        
        return response
    
    @action(detail=False, methods=['get'])
    def reference(self, request):
        """
        Get reference data for CSV import
        """
        from .models import DataElementClass, DataType, MappingSource
        
        classes = DataElementClass.objects.filter(status='active').values('id', 'name')
        types = DataType.objects.all().values('id', 'name')
        sources = MappingSource.objects.all().values('id', 'name')
        
        return Response({
            'classes': list(classes),
            'types': list(types),
            'sources': list(sources)
        })