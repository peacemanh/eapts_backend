from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, DateField, Max, Prefetch, Count, Min
from django.db.models.functions import Cast
import rest_framework.serializers as serializers
from .models import AggregateRecord
from apps.data_element.models import DataElementSetMember, DataElement
from apps.locations.models import Location
from .serializers import (
    AggregateRecordSerializer,
    GroupedFieldSerializer,
    GroupedAggregateRecordSerializer
)
import logging
import re
from datetime import datetime
import dateutil.parser

logger = logging.getLogger(__name__)


class AggregateRecordViewSet(viewsets.ModelViewSet):
    """
    Production-ready ViewSet for AggregateRecord with:
    - Token AND Session authentication supported for all operations
    - Institution context required for all operations
    - create/update-if-duplicate
    - bulk-insert (create-or-update)
    - bulk-delete
    - by-form summary
    - search-values
    - grouped endpoint (/grouped/) returning one object per record_id (nested fields)
    - limit_dates support (latest N distinct dates) applied before grouping or listing
    - by-location endpoint (requires institution context)
    - Pair data element queries
    - Group filtering support
    """
    queryset = AggregateRecord.objects.all().select_related(
        'data_element', 'form', 'value_coded', 'group',  # Added 'group' here
        'institution', 'location', 'created_by', 'updated_by'
    ).order_by('-date_created')
    serializer_class = AggregateRecordSerializer
    filter_backends = [DjangoFilterBackend,
                       filters.SearchFilter, filters.OrderingFilter]
    
    # Support BOTH TokenAuthentication (for API clients) AND SessionAuthentication (for web frontend)
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    filterset_fields = {
        'form': ['exact', 'in'],
        'data_element': ['exact'],
        'value_coded': ['exact'],
        'record_id': ['exact'],
        'location': ['exact'],
        'group': ['exact', 'in'],  # NEW: Add group filter support
        'date_created': ['exact', 'gte', 'lte'],
    }

    search_fields = [
        'record_id', 'data_element__name', 'form__name', 'value_text',
        'value_coded__name', 'value_numeric',
        'location__name', 'group__name',  # Added group__name to search
    ]
    ordering_fields = [
        'date_created', 'date_updated', 'form', 'data_element', 'group',  # Added group
        'value_numeric', 'value_datetime', 'record_id',
        'location__name', 'group__name'  # Added group__name
    ]
    ordering = ['-date_created']

    def get_queryset(self):
        """
        Apply institution context first, then other filters.
        Institution is required for all operations.
        User must be authenticated (via token OR session).
        """
        # User is guaranteed to be authenticated via token OR session
        current_user = self.request.user
        
        queryset = super().get_queryset()
        
        # REQUIRED: Get institution from query parameters
        institution_id = self.request.query_params.get('institution')
        
        if not institution_id:
            raise serializers.ValidationError(
                {"institution": "This parameter is required for all operations."}
            )
        
        try:
            institution_id = int(institution_id)
            # Verify institution exists
            institution = Location.objects.filter(id=institution_id).first()
            if not institution:
                raise serializers.ValidationError(
                    {"institution": f"Institution with ID {institution_id} does not exist."}
                )
            
            # Apply institution filter to all queries
            queryset = queryset.filter(institution_id=institution_id)
        except ValueError:
            raise serializers.ValidationError(
                {"institution": "Invalid institution ID. Must be an integer."}
            )

        # Apply other filters only after institution filter
        
        # NEW: Add group filter
        group_id = self.request.query_params.get('group')
        if group_id:
            try:
                # Handle comma-separated list for multiple groups
                if ',' in group_id:
                    group_ids = [int(g.strip()) for g in group_id.split(',') if g.strip()]
                    queryset = queryset.filter(group_id__in=group_ids)
                else:
                    queryset = queryset.filter(group_id=int(group_id))
            except ValueError:
                # If not integer, try filtering by group name
                queryset = queryset.filter(group__name__icontains=group_id)
        
        # numeric range filters
        min_value = self.request.query_params.get('min_value')
        max_value = self.request.query_params.get('max_value')
        if min_value or max_value:
            try:
                if min_value:
                    queryset = queryset.filter(value_numeric__gte=float(min_value))
                if max_value:
                    queryset = queryset.filter(value_numeric__lte=float(max_value))
            except (ValueError, TypeError):
                # ignore invalid numeric filters
                pass

        # date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(date_created__gte=start_date)
        if end_date:
            queryset = queryset.filter(date_created__lte=end_date)

        data_element_type = self.request.query_params.get('data_element_type')
        if data_element_type:
            # This uses the related datatype - adjust field name based on your DataType model
            queryset = queryset.filter(data_element__datatype_id__name__icontains=data_element_type)

        # location filter (within the institution)
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)

        # limit by latest distinct dates (date part)
        limit_dates = self.request.query_params.get('limit_dates')
        if limit_dates:
            try:
                n = int(limit_dates)
                if n > 0:
                    latest_dates_qs = (
                        queryset
                        .annotate(only_date=Cast('date_created', output_field=DateField()))
                        .values_list('only_date', flat=True)
                        .distinct()
                        .order_by('-only_date')[:n]
                    )
                    latest_dates = list(latest_dates_qs)
                    if latest_dates:
                        # filter to records whose date_created.date is in those latest dates
                        queryset = queryset.filter(date_created__date__in=latest_dates)
            except (ValueError, TypeError):
                pass

        return queryset

    def _get_queryset_with_sort_weights(self):
        """
        Optimized queryset that prefetches sort_weights for BOTH form and group memberships.
        """
        queryset = self.get_queryset()
        
        # Create a prefetch for ALL DataElementSetMember relationships
        # This will prefetch memberships for both forms and groups
        sort_weight_prefetch = Prefetch(
            'data_element__included_in_sections',
            queryset=DataElementSetMember.objects.select_related('section_element'),
            to_attr='prefetched_memberships'
        )
        
        queryset = queryset.prefetch_related(sort_weight_prefetch)
        
        return queryset

    # -------------------------
    # CREATE → UPDATE IF DUPLICATE
    # -------------------------
    def create(self, request, *args, **kwargs):
        # Ensure institution is provided in request data
        if 'institution' not in request.data:
            return Response(
                {"institution": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        record_id = request.data.get("record_id")
        form = request.data.get("form")
        data_element = request.data.get("data_element")
        institution_id = request.data.get("institution")

        existing = None
        if record_id and form and data_element and institution_id:
            existing = AggregateRecord.objects.filter(
                record_id=record_id,
                form=form,
                data_element=data_element,
                institution_id=institution_id
            ).first()

        context = self.get_serializer_context()
        context['data_type'] = request.data.get('data_type')

        if existing:
            serializer = self.get_serializer(
                existing, data=request.data, partial=True, context=context)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # -------------------------
    # BULK INSERT/UPDATE
    # -------------------------
    @action(detail=False, methods=['post'], url_path='bulk-insert')
    def bulk_insert(self, request):
        if not isinstance(request.data, list):
            return Response({"error": "Payload must be a list of records."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Verify all records have institution specified
        for i, record in enumerate(request.data):
            if 'institution' not in record:
                return Response(
                    {"error": f"All records must have 'institution' field specified. Record {i} is missing it."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        created_or_updated_instances = []

        with transaction.atomic():
            for record in request.data:
                record_id = record.get("record_id")
                form = record.get("form")
                data_element = record.get("data_element")
                institution_id = record.get("institution")

                existing = None
                if record_id and form and data_element and institution_id:
                    existing = AggregateRecord.objects.filter(
                        record_id=record_id,
                        form=form,
                        data_element=data_element,
                        institution_id=institution_id
                    ).first()

                context = self.get_serializer_context()
                context['data_type'] = record.get('data_type')

                if existing:
                    serializer = self.get_serializer(
                        existing, data=record, partial=True, context=context)
                    serializer.is_valid(raise_exception=True)
                    instance = serializer.save()
                else:
                    serializer = self.get_serializer(data=record, context=context)
                    serializer.is_valid(raise_exception=True)
                    instance = serializer.save()

                created_or_updated_instances.append(instance)

        result_serializer = self.get_serializer(
            created_or_updated_instances, many=True)
        return Response({
            "status": "success",
            "processed": len(created_or_updated_instances),
            "user": request.user.username,
            "records": result_serializer.data
        }, status=status.HTTP_201_CREATED)

    # -------------------------
    # BY-FORM summary
    # -------------------------
    @action(detail=False, methods=['get'], url_path='by-form')
    def by_form(self, request):
        # User is authenticated via token OR session
        current_user = request.user
        
        # Institution is already enforced in get_queryset()
        form_id = request.query_params.get('form_id')
        queryset = self.get_queryset()

        if form_id:
            queryset = queryset.filter(form_id=form_id)

        form_stats = queryset.values('form_id', 'form__name').annotate(
            record_count=Count('id'),
            earliest_record=Min('date_created'),
            latest_record=Max('date_created')
        )

        return Response({
            'institution_id': request.query_params.get('institution'),
            'requested_by': current_user.username,
            'forms': list(form_stats),
            'total_records': queryset.count()
        })

    # -------------------------
    # BY-LOCATION endpoint (requires institution context)
    # -------------------------
    @action(detail=False, methods=['get'], url_path='by-location')
    def by_location(self, request):
        """
        Get aggregate records for a specific location within the institution.
        Requires institution parameter and location_id parameter.
        User must be authenticated (via token OR session).
        """
        # User is authenticated via token OR session
        current_user = request.user
        
        location_id = request.query_params.get('location_id')
        
        if not location_id:
            return Response(
                {"error": "location_id parameter is required for by-location endpoint."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            location_id = int(location_id)
        except ValueError:
            return Response(
                {"error": "Invalid location ID. Must be an integer."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get institution ID from query params
        institution_id = request.query_params.get('institution')
        if not institution_id:
            return Response(
                {"error": "institution parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the base queryset (already filtered by institution)
        queryset = self.get_queryset()
        
        # Further filter by location
        queryset = queryset.filter(location_id=location_id)
        
        # Get location name for context
        try:
            location = Location.objects.get(id=location_id)
            location_name = location.name
        except Location.DoesNotExist:
            location_name = "Unknown Location"
        
        # Get institution name for context
        try:
            institution = Location.objects.get(id=institution_id)
            institution_name = institution.name
        except Location.DoesNotExist:
            institution_name = "Unknown Institution"
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            # Add metadata to response
            response.data.update({
                'institution_id': institution_id,
                'institution_name': institution_name,
                'location_id': location_id,
                'location_name': location_name,
                'requested_by': current_user.username,
            })
            return response

        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'institution_id': institution_id,
            'institution_name': institution_name,
            'location_id': location_id,
            'location_name': location_name,
            'requested_by': current_user.username,
            'total_records': queryset.count(),
            'records': serializer.data
        })

    # -------------------------
    # SEARCH across value fields
    # -------------------------
    @action(detail=False, methods=['get'], url_path='search-values')
    def search_values(self, request):
        # User is authenticated via token OR session
        current_user = request.user
        
        query = request.query_params.get('q')
        if not query:
            return Response({"error": "Query parameter 'q' is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Institution is already enforced in get_queryset()
        queryset = self.get_queryset()
        queryset = queryset.filter(
            Q(value_text__icontains=query) |
            Q(value_numeric__icontains=query) |
            Q(data_element__name__icontains=query) |
            Q(form__name__icontains=query) |
            Q(value_coded__name__icontains=query) |
            Q(location__name__icontains=query) |
            Q(group__name__icontains=query)  # Added group name to search
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # -------------------------
    # BULK DELETE
    # -------------------------
    @action(detail=False, methods=['delete'], url_path='bulk-delete')
    def bulk_delete(self, request):
        # User is authenticated via token OR session
        current_user = request.user
        
        record_ids = request.data.get('ids', [])
        form_id = request.data.get('form_id')
        location_id = request.data.get('location_id')

        # Institution is already enforced in get_queryset()
        queryset = self.get_queryset()

        with transaction.atomic():
            if record_ids:
                deleted_count, _ = queryset.filter(id__in=record_ids).delete()
            elif form_id:
                deleted_count, _ = queryset.filter(form_id=form_id).delete()
            elif location_id:
                deleted_count, _ = queryset.filter(location_id=location_id).delete()
            else:
                return Response(
                    {"error": "Provide either 'ids' array, 'form_id', or 'location_id' for bulk delete"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response({
            "status": "success",
            "deleted": deleted_count,
            "deleted_by": current_user.username
        }, status=status.HTTP_200_OK)

    # -------------------------
    # DUPLICATE single record
    # -------------------------
    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate_record(self, request, pk=None):
        # User is authenticated via token OR session
        current_user = request.user
        
        instance = self.get_object()
        instance.pk = None
        instance.uuid = None
        instance.created_by = current_user
        instance.updated_by = current_user
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # -------------------------
    # GROUPED endpoint: one object per record_id with nested fields
    # -------------------------
    @action(detail=False, methods=['get'], url_path='grouped')
    def grouped(self, request):
        """
        Return one nested object per record_id.
        Institution context is already enforced in get_queryset().
        User must be authenticated (via token OR session).
        """
        # User is authenticated via token OR session
        current_user = request.user
        
        # Use the optimized queryset that prefetches sort weights
        queryset = self._get_queryset_with_sort_weights()
        base_qs = self.filter_queryset(queryset)


        # Step 1: compute groups (record_id) ordered by latest date per record
        groups_qs = base_qs.values('record_id').annotate(latest_created=Max('date_created')).order_by('-latest_created')

        record_id_list = [g['record_id'] for g in groups_qs]

        total_groups = len(record_id_list)

        # Step 2: paginate record_id_list (we want to paginate groups)
        paginator = self.paginator
        request_for_paginate = request
        if paginator is not None:
            page_record_ids = paginator.paginate_queryset(record_id_list, request_for_paginate, view=self)
        else:
            page_record_ids = record_id_list

        if not page_record_ids:
            # nothing to return
            empty_resp = {
                'count': total_groups,
                'results': []
            }
            return Response(empty_resp)

        # Step 3: fetch all rows belonging to the page's record_ids in one query
        # Using the already prefetched queryset
        records_qs = (
            base_qs
            .filter(record_id__in=page_record_ids)
            .order_by('-date_created', 'data_element')  # deterministic ordering for nested fields
        )

        # Build mapping record_id -> list of record instances
        groups_map = {}
        for rec in records_qs:
            groups_map.setdefault(rec.record_id, []).append(rec)

        # Step 4: build ordered grouped objects following the page_record_ids order
        grouped_results = []
        for rid in page_record_ids:
            recs = groups_map.get(rid, [])
            if not recs:
                continue

            # Use latest doc-level metadata from the most recent record in recs
            latest = max(recs, key=lambda r: r.date_created)

            # Serialize nested fields with a dedicated serializer
            fields_serializer = GroupedFieldSerializer(recs, many=True, context=self.get_serializer_context())
            grouped_item = {
                'record_id': rid,
                'form': latest.form.id if latest.form else None,
                'form_name': latest.form.name if latest.form else None,
                'institution': latest.institution.id if latest.institution else None,
                'institution_name': latest.institution.name if latest.institution else None,
                'location': latest.location.id if latest.location else None,
                'location_name': latest.location.name if latest.location else None,
                'group': latest.group.id if latest.group else None,  # NEW: Add group ID
                'group_name': latest.group.name if latest.group else None,  # NEW: Add group name
                'date_created': latest.date_created,
                'date_updated': latest.date_updated,
                'fields': fields_serializer.data
            }
            grouped_results.append(grouped_item)

        # Step 5: return paginated response (groups paginated)
        if paginator is not None:
            response = paginator.get_paginated_response(grouped_results)
            # Add user info to response
            response.data['requested_by'] = current_user.username
            return response
        else:
            return Response({
                'count': total_groups,
                'requested_by': current_user.username,
                'results': grouped_results
            })

    # ==============================================
    # PAIR DATA ELEMENT QUERIES
    # ==============================================
    
    def _get_value_filter(self, data_element_id, value, institution_id):
        """
        Auto-detect which field to filter on based on data type.
        Returns a dict like {'value_coded_id': 123} or {'value_text': 'abc'}
        """
        # Try to find what type of value this data element stores
        sample = AggregateRecord.objects.filter(
            institution_id=institution_id,
            data_element_id=data_element_id
        ).exclude(
            # Exclude records where all value fields are null
            value_coded_id__isnull=True,
            value_numeric__isnull=True,
            value_text__isnull=True,
            value_datetime__isnull=True
        ).first()
        
        if sample:
            if sample.value_coded_id is not None:
                return self._handle_coded_value(data_element_id, value)
            elif sample.value_numeric is not None:
                return self._handle_numeric_value(value)
            elif sample.value_datetime is not None:
                return self._handle_datetime_value(value)
            elif sample.value_text is not None:
                return {'value_text': str(value)}
        
        # STRATEGY 2: Check data element's datatype configuration
        try:
            # Use select_related to fetch the datatype in the same query
            de = DataElement.objects.select_related('datatype_id').get(id=data_element_id)
            
            if de.datatype_id:
                # Get datatype details - adjust field names based on your actual DataType model
                datatype_name = getattr(de.datatype_id, 'name', '').lower()
                datatype_code = getattr(de.datatype_id, 'code', '').lower()
                datatype_value = datatype_name or datatype_code
                
                # Coded types (dropdown, radio, checkbox, select)
                coded_types = ['coded', 'select', 'dropdown', 'radio', 'checkbox', 'multi-select', 'boolean']
                if any(dt in datatype_value for dt in coded_types):
                    return self._handle_coded_value(data_element_id, value)
                
                # Numeric types
                numeric_types = ['numeric', 'number', 'integer', 'decimal', 'float', 'double', 'percentage']
                if any(dt in datatype_value for dt in numeric_types):
                    return self._handle_numeric_value(value)
                
                # Date/time types
                datetime_types = ['date', 'datetime', 'time', 'timestamp']
                if any(dt in datatype_value for dt in datetime_types):
                    return self._handle_datetime_value(value)
                
                # Text types (default)
                return {'value_text': str(value)}
                
        except DataElement.DoesNotExist:
            logger.warning(f"DataElement with id {data_element_id} not found")
        except Exception as e:
            logger.error(f"Error checking datatype for data_element {data_element_id}: {str(e)}")
        
        # STRATEGY 3: Infer from value format
        return self._infer_filter_from_value(value)

    def _handle_coded_value(self, data_element_id, value):
        """Handle coded value filtering with multiple strategies"""
        # Try as integer ID first
        try:
            int_value = int(value)
            # Verify this ID exists as a DataElement (coded value)
            if DataElement.objects.filter(id=int_value).exists():
                return {'value_coded_id': int_value}
        except (ValueError, TypeError):
            pass
        
        # Try to find by name (case-insensitive exact match)
        try:
            coded_element = DataElement.objects.filter(
                name__iexact=str(value).strip()
            ).first()
            if coded_element:
                return {'value_coded_id': coded_element.id}
        except Exception:
            pass
        
        # Try to find by code if available
        try:
            if hasattr(DataElement, 'code'):
                coded_element = DataElement.objects.filter(
                    code__iexact=str(value).strip()
                ).first()
                if coded_element:
                    return {'value_coded_id': coded_element.id}
        except Exception:
            pass
        
        # Try partial match as last resort for coded values
        try:
            coded_element = DataElement.objects.filter(
                name__icontains=str(value).strip()
            ).first()
            if coded_element:
                return {'value_coded_id': coded_element.id}
        except Exception:
            pass
        
        # If all else fails, treat as text
        return {'value_text': str(value)}

    def _handle_numeric_value(self, value):
        """Handle numeric value filtering"""
        # Clean the value (remove commas, spaces)
        if isinstance(value, str):
            value = value.replace(',', '').replace(' ', '')
        
        try:
            # Try as float
            float_value = float(value)
            # Check if it's actually an integer
            if float_value.is_integer():
                return {'value_numeric': int(float_value)}
            return {'value_numeric': float_value}
        except (ValueError, TypeError):
            # If it can't be converted to float, treat as text
            return {'value_text': str(value)}

    def _handle_datetime_value(self, value):
        """Handle datetime value filtering"""
        try:
            # Try to parse the datetime
            if isinstance(value, str):
                parsed_date = dateutil.parser.parse(value)
                return {'value_datetime': parsed_date}
            elif isinstance(value, datetime):
                return {'value_datetime': value}
            else:
                return {'value_text': str(value)}
        except (ValueError, TypeError):
            return {'value_text': str(value)}

    def _infer_filter_from_value(self, value):
        """Infer the appropriate filter from the value format"""
        if value is None or value == '':
            return {}
        
        # Check if it looks like a date
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY
            r'^\d{2}-\d{2}-\d{4}$',  # MM-DD-YYYY
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # YYYY-MM-DD HH:MM:SS
        ]
        
        if isinstance(value, str):
            for pattern in date_patterns:
                if re.match(pattern, value):
                    return self._handle_datetime_value(value)
        
        # Check if it looks like a number
        try:
            float(value)
            return self._handle_numeric_value(value)
        except (ValueError, TypeError):
            pass
        
        # Default to text
        return {'value_text': str(value)}
    
    def _apply_additional_filters(self, queryset, request):
        """
        Apply additional filters similar to get_queryset() method.
        Used for pair query endpoints.
        """
        # numeric range filters
        min_value = request.query_params.get('min_value')
        max_value = request.query_params.get('max_value')
        if min_value or max_value:
            try:
                if min_value:
                    queryset = queryset.filter(value_numeric__gte=float(min_value))
                if max_value:
                    queryset = queryset.filter(value_numeric__lte=float(max_value))
            except (ValueError, TypeError):
                # ignore invalid numeric filters
                pass

        # date range
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(date_created__gte=start_date)
        if end_date:
            queryset = queryset.filter(date_created__lte=end_date)

        data_element_type = request.query_params.get('data_element_type')
        if data_element_type:
            queryset = queryset.filter(data_element__datatype_id__name__icontains=data_element_type)

        # location filter (within the institution)
        location_id = request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)

        # NEW: Add group filter
        group_id = request.query_params.get('group')
        if group_id:
            try:
                if ',' in group_id:
                    group_ids = [int(g.strip()) for g in group_id.split(',') if g.strip()]
                    queryset = queryset.filter(group_id__in=group_ids)
                else:
                    queryset = queryset.filter(group_id=int(group_id))
            except ValueError:
                queryset = queryset.filter(group__name__icontains=group_id)

        # limit by latest distinct dates (date part)
        limit_dates = request.query_params.get('limit_dates')
        if limit_dates:
            try:
                n = int(limit_dates)
                if n > 0:
                    latest_dates_qs = (
                        queryset
                        .annotate(only_date=Cast('date_created', output_field=DateField()))
                        .values_list('only_date', flat=True)
                        .distinct()
                        .order_by('-only_date')[:n]
                    )
                    latest_dates = list(latest_dates_qs)
                    if latest_dates:
                        # filter to records whose date_created.date is in those latest dates
                        queryset = queryset.filter(date_created__date__in=latest_dates)
            except (ValueError, TypeError):
                pass

        return queryset

    # -------------------------
    # ENDPOINT 1: Both data elements exist (no value filters)
    # -------------------------
    @action(detail=False, methods=['get'], url_path='both-data-elements-exist')
    def both_data_elements_exist(self, request):
        """
        Endpoint 1: Fetch records where both data elements exist
        Optional parameter: limit - number of records to return (default: all/paginated)
        """
        current_user = request.user
        
        # Get required parameters
        institution_id = request.query_params.get('institution')
        first_data_element = request.query_params.get('first_data_element')
        second_data_element = request.query_params.get('second_data_element')
        
        # Get optional limit parameter
        limit = request.query_params.get('limit')
        
        if not all([institution_id, first_data_element, second_data_element]):
            return Response(
                {"success": False, "error": "institution, first_data_element, and second_data_element are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Convert to integers
            institution_id = int(institution_id)
            first_data_element = int(first_data_element)
            second_data_element = int(second_data_element)
            
            # Convert limit if provided
            if limit:
                limit = int(limit)
                if limit <= 0:
                    return Response(
                        {"success": False, "error": "Limit must be a positive integer"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Verify institution exists
            institution = Location.objects.filter(id=institution_id).first()
            if not institution:
                return Response(
                    {"success": False, "error": f"Institution with ID {institution_id} does not exist."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Step 1: Get record_ids where first data element exists
            first_record_ids = AggregateRecord.objects.filter(
                institution_id=institution_id,
                data_element_id=first_data_element
            ).values_list('record_id', flat=True).distinct()
            
            # Step 2: Get record_ids where second data element exists
            second_record_ids = AggregateRecord.objects.filter(
                institution_id=institution_id,
                data_element_id=second_data_element
            ).values_list('record_id', flat=True).distinct()
            
            # Step 3: Intersection - record_ids that have BOTH data elements
            common_record_ids = set(first_record_ids) & set(second_record_ids)
            
            # Step 4: Fetch all records for these common record_ids
            # (including both data elements)
            final_queryset = AggregateRecord.objects.filter(
                institution_id=institution_id,
                record_id__in=common_record_ids,
                data_element_id__in=[first_data_element, second_data_element]
            ).select_related(
                'data_element', 'form', 'value_coded', 'group',
                'institution', 'location', 'created_by', 'updated_by'
            ).order_by('-date_created')
            
            # Apply limit if provided (overrides pagination)
            if limit:
                final_queryset = final_queryset[:limit]
            
            # Apply additional filters
            final_queryset = self._apply_additional_filters(final_queryset, request)
            
            # Get names for metadata
            first_de_name = f"Data Element {first_data_element}"
            second_de_name = f"Data Element {second_data_element}"
            
            try:
                first_de = DataElement.objects.get(id=first_data_element)
                first_de_name = first_de.name
            except DataElement.DoesNotExist:
                pass
            
            try:
                second_de = DataElement.objects.get(id=second_data_element)
                second_de_name = second_de.name
            except DataElement.DoesNotExist:
                pass
            
            # Handle response based on whether limit was used
            if limit:
                # Return limited results without pagination
                serializer = self.get_serializer(final_queryset, many=True, context=self.get_serializer_context())
                
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'metadata': {
                        'institution_id': institution_id,
                        'institution_name': institution.name,
                        'first_data_element': first_data_element,
                        'first_data_element_name': first_de_name,
                        'second_data_element': second_data_element,
                        'second_data_element_name': second_de_name,
                        'common_record_ids_count': len(common_record_ids),
                        'returned_count': len(serializer.data),
                        'limit_applied': limit,
                        'requested_by': current_user.username,
                        'filter_type': 'both_data_elements_exist',
                        'pagination_skipped': True
                    }
                })
            
            # Apply pagination (only if no limit)
            page = self.paginate_queryset(final_queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True, context=self.get_serializer_context())
                response = self.get_paginated_response(serializer.data)
                # Add metadata
                response.data.update({
                    'success': True,
                    'metadata': {
                        'institution_id': institution_id,
                        'institution_name': institution.name,
                        'first_data_element': first_data_element,
                        'first_data_element_name': first_de_name,
                        'second_data_element': second_data_element,
                        'second_data_element_name': second_de_name,
                        'common_record_ids_count': len(common_record_ids),
                        'requested_by': current_user.username,
                        'filter_type': 'both_data_elements_exist'
                    }
                })
                return response
            
            # No pagination and no limit
            serializer = self.get_serializer(final_queryset, many=True, context=self.get_serializer_context())
            
            return Response({
                'success': True,
                'data': serializer.data,
                'metadata': {
                    'institution_id': institution_id,
                    'institution_name': institution.name,
                    'first_data_element': first_data_element,
                    'first_data_element_name': first_de_name,
                    'second_data_element': second_data_element,
                    'second_data_element_name': second_de_name,
                    'common_record_ids_count': len(common_record_ids),
                    'requested_by': current_user.username,
                    'filter_type': 'both_data_elements_exist',
                    'total_records': final_queryset.count()
                }
            })
            
        except ValueError as e:
            return Response(
                {"success": False, "error": f"Invalid parameter: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"success": False, "error": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # -------------------------
    # ENDPOINT 2: First exists, second with specific value
    # -------------------------
    @action(detail=False, methods=['get'], url_path='first-exists-second-with-value')
    def first_exists_second_with_value(self, request):
        """
        Endpoint 2: First data element exists, second has specific value
        Optional parameter: limit - number of records to return (default: all/paginated)
        """
        current_user = request.user
        
        # Get required parameters
        institution_id = request.query_params.get('institution')
        first_data_element = request.query_params.get('first_data_element')
        second_data_element = request.query_params.get('second_data_element')
        second_value = request.query_params.get('second_value')
        
        # Get optional limit parameter
        limit = request.query_params.get('limit')
        
        if not all([institution_id, first_data_element, second_data_element, second_value]):
            return Response(
                {"success": False, "error": "institution, first_data_element, second_data_element, and second_value are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Convert to integers
            institution_id = int(institution_id)
            first_data_element = int(first_data_element)
            second_data_element = int(second_data_element)
            
            # Convert limit if provided
            if limit:
                limit = int(limit)
                if limit <= 0:
                    return Response(
                        {"success": False, "error": "Limit must be a positive integer"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Verify institution exists
            institution = Location.objects.filter(id=institution_id).first()
            if not institution:
                return Response(
                    {"success": False, "error": f"Institution with ID {institution_id} does not exist."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Auto-detect which field to filter on for second value
            second_filter = self._get_value_filter(second_data_element, second_value, institution_id)
            
            # Step 1: Get record_ids where first data element exists
            first_record_ids = AggregateRecord.objects.filter(
                institution_id=institution_id,
                data_element_id=first_data_element
            ).values_list('record_id', flat=True).distinct()
            
            # Step 2: Get record_ids where second data element has specific value
            second_record_ids = AggregateRecord.objects.filter(
                institution_id=institution_id,
                data_element_id=second_data_element,
                **second_filter
            ).values_list('record_id', flat=True).distinct()
            
            # Step 3: Intersection - record_ids that have BOTH conditions
            common_record_ids = set(first_record_ids) & set(second_record_ids)
            
            # Step 4: Fetch records for FIRST data element only (what front-end expects)
            final_queryset = AggregateRecord.objects.filter(
                institution_id=institution_id,
                record_id__in=common_record_ids,
                data_element_id=first_data_element  # ONLY first data element
            ).select_related(
                'data_element', 'form', 'value_coded', 'group',
                'institution', 'location', 'created_by', 'updated_by'
            ).order_by('-date_created')
            
            # Apply limit if provided (overrides pagination)
            if limit:
                final_queryset = final_queryset[:limit]
            
            # Apply additional filters
            final_queryset = self._apply_additional_filters(final_queryset, request)
            
            # Get names for metadata
            first_de_name = f"Data Element {first_data_element}"
            second_de_name = f"Data Element {second_data_element}"
            
            try:
                first_de = DataElement.objects.get(id=first_data_element)
                first_de_name = first_de.name
            except DataElement.DoesNotExist:
                pass
            
            try:
                second_de = DataElement.objects.get(id=second_data_element)
                second_de_name = second_de.name
            except DataElement.DoesNotExist:
                pass
            
            # Determine which field was used for filtering
            second_value_field = list(second_filter.keys())[0] if second_filter else 'auto_detected'
            
            # Handle response based on whether limit was used
            if limit:
                # Return limited results without pagination
                serializer = self.get_serializer(final_queryset, many=True, context=self.get_serializer_context())
                
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'metadata': {
                        'institution_id': institution_id,
                        'institution_name': institution.name,
                        'first_data_element': first_data_element,
                        'first_data_element_name': first_de_name,
                        'second_data_element': second_data_element,
                        'second_data_element_name': second_de_name,
                        'second_value': second_value,
                        'second_value_field': second_value_field,
                        'common_record_ids_count': len(common_record_ids),
                        'returned_count': len(serializer.data),
                        'limit_applied': limit,
                        'requested_by': current_user.username,
                        'filter_type': 'first_exists_second_with_value',
                        'pagination_skipped': True
                    }
                })
            
            # Apply pagination (only if no limit)
            page = self.paginate_queryset(final_queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True, context=self.get_serializer_context())
                response = self.get_paginated_response(serializer.data)
                # Add metadata
                response.data.update({
                    'success': True,
                    'metadata': {
                        'institution_id': institution_id,
                        'institution_name': institution.name,
                        'first_data_element': first_data_element,
                        'first_data_element_name': first_de_name,
                        'second_data_element': second_data_element,
                        'second_data_element_name': second_de_name,
                        'second_value': second_value,
                        'second_value_field': second_value_field,
                        'common_record_ids_count': len(common_record_ids),
                        'requested_by': current_user.username,
                        'filter_type': 'first_exists_second_with_value'
                    }
                })
                return response
            
            # No pagination and no limit
            serializer = self.get_serializer(final_queryset, many=True, context=self.get_serializer_context())
            
            return Response({
                'success': True,
                'data': serializer.data,
                'metadata': {
                    'institution_id': institution_id,
                    'institution_name': institution.name,
                    'first_data_element': first_data_element,
                    'first_data_element_name': first_de_name,
                    'second_data_element': second_data_element,
                    'second_data_element_name': second_de_name,
                    'second_value': second_value,
                    'second_value_field': second_value_field,
                    'common_record_ids_count': len(common_record_ids),
                    'requested_by': current_user.username,
                    'filter_type': 'first_exists_second_with_value',
                    'total_records': final_queryset.count()
                }
            })
            
        except ValueError as e:
            return Response(
                {"success": False, "error": f"Invalid parameter: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"success": False, "error": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # -------------------------
    # ENDPOINT 3: Both with specific values
    # -------------------------
    @action(detail=False, methods=['get'], url_path='both-with-specific-values')
    def both_with_specific_values(self, request):
        """
        Endpoint 3: Both data elements have specific values
        Optional parameter: limit - number of records to return (default: all/paginated)
        """
        current_user = request.user
        
        # Get required parameters
        institution_id = request.query_params.get('institution')
        first_data_element = request.query_params.get('first_data_element')
        first_value = request.query_params.get('first_value')
        second_data_element = request.query_params.get('second_data_element')
        second_value = request.query_params.get('second_value')
        
        # Get optional limit parameter
        limit = request.query_params.get('limit')
        
        if not all([institution_id, first_data_element, first_value, second_data_element, second_value]):
            return Response(
                {"success": False, "error": "institution, first_data_element, first_value, second_data_element, and second_value are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Convert to integers
            institution_id = int(institution_id)
            first_data_element = int(first_data_element)
            second_data_element = int(second_data_element)
            
            # Convert limit if provided
            if limit:
                limit = int(limit)
                if limit <= 0:
                    return Response(
                        {"success": False, "error": "Limit must be a positive integer"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Verify institution exists
            institution = Location.objects.filter(id=institution_id).first()
            if not institution:
                return Response(
                    {"success": False, "error": f"Institution with ID {institution_id} does not exist."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Auto-detect filters for both
            first_filter = self._get_value_filter(first_data_element, first_value, institution_id)
            second_filter = self._get_value_filter(second_data_element, second_value, institution_id)
            
            # Step 1: Get record_ids where first data element has specific value
            first_record_ids = AggregateRecord.objects.filter(
                institution_id=institution_id,
                data_element_id=first_data_element,
                **first_filter
            ).values_list('record_id', flat=True).distinct()
            
            # Step 2: Get record_ids where second data element has specific value
            second_record_ids = AggregateRecord.objects.filter(
                institution_id=institution_id,
                data_element_id=second_data_element,
                **second_filter
            ).values_list('record_id', flat=True).distinct()
            
            # Step 3: Intersection - record_ids that have BOTH conditions
            common_record_ids = set(first_record_ids) & set(second_record_ids)
            
            # Step 4: Fetch records for FIRST data element only
            final_queryset = AggregateRecord.objects.filter(
                institution_id=institution_id,
                record_id__in=common_record_ids,
                data_element_id=first_data_element  # ONLY first data element
            ).select_related(
                'data_element', 'form', 'value_coded', 'group',
                'institution', 'location', 'created_by', 'updated_by'
            ).order_by('-date_created')
            
            # Apply limit if provided (overrides pagination)
            if limit:
                final_queryset = final_queryset[:limit]
            
            # Apply additional filters
            final_queryset = self._apply_additional_filters(final_queryset, request)
            
            # Get names for metadata
            first_de_name = f"Data Element {first_data_element}"
            second_de_name = f"Data Element {second_data_element}"
            
            try:
                first_de = DataElement.objects.get(id=first_data_element)
                first_de_name = first_de.name
            except DataElement.DoesNotExist:
                pass
            
            try:
                second_de = DataElement.objects.get(id=second_data_element)
                second_de_name = second_de.name
            except DataElement.DoesNotExist:
                pass
            
            # Determine which fields were used for filtering
            first_value_field = list(first_filter.keys())[0] if first_filter else 'auto_detected'
            second_value_field = list(second_filter.keys())[0] if second_filter else 'auto_detected'
            
            # Handle response based on whether limit was used
            if limit:
                # Return limited results without pagination
                serializer = self.get_serializer(final_queryset, many=True, context=self.get_serializer_context())
                
                return Response({
                    'success': True,
                    'data': serializer.data,
                    'metadata': {
                        'institution_id': institution_id,
                        'institution_name': institution.name,
                        'first_data_element': first_data_element,
                        'first_data_element_name': first_de_name,
                        'first_value': first_value,
                        'first_value_field': first_value_field,
                        'second_data_element': second_data_element,
                        'second_data_element_name': second_de_name,
                        'second_value': second_value,
                        'second_value_field': second_value_field,
                        'common_record_ids_count': len(common_record_ids),
                        'returned_count': len(serializer.data),
                        'limit_applied': limit,
                        'requested_by': current_user.username,
                        'filter_type': 'both_with_specific_values',
                        'pagination_skipped': True
                    }
                })
            
            # Apply pagination (only if no limit)
            page = self.paginate_queryset(final_queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True, context=self.get_serializer_context())
                response = self.get_paginated_response(serializer.data)
                # Add metadata
                response.data.update({
                    'success': True,
                    'metadata': {
                        'institution_id': institution_id,
                        'institution_name': institution.name,
                        'first_data_element': first_data_element,
                        'first_data_element_name': first_de_name,
                        'first_value': first_value,
                        'first_value_field': first_value_field,
                        'second_data_element': second_data_element,
                        'second_data_element_name': second_de_name,
                        'second_value': second_value,
                        'second_value_field': second_value_field,
                        'common_record_ids_count': len(common_record_ids),
                        'requested_by': current_user.username,
                        'filter_type': 'both_with_specific_values'
                    }
                })
                return response
            
            # No pagination and no limit
            serializer = self.get_serializer(final_queryset, many=True, context=self.get_serializer_context())
            
            return Response({
                'success': True,
                'data': serializer.data,
                'metadata': {
                    'institution_id': institution_id,
                    'institution_name': institution.name,
                    'first_data_element': first_data_element,
                    'first_data_element_name': first_de_name,
                    'first_value': first_value,
                    'first_value_field': first_value_field,
                    'second_data_element': second_data_element,
                    'second_data_element_name': second_de_name,
                    'second_value': second_value,
                    'second_value_field': second_value_field,
                    'common_record_ids_count': len(common_record_ids),
                    'requested_by': current_user.username,
                    'filter_type': 'both_with_specific_values',
                    'total_records': final_queryset.count()
                }
            })
            
        except ValueError as e:
            return Response(
                {"success": False, "error": f"Invalid parameter: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"success": False, "error": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )