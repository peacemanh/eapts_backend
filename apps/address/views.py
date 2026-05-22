from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.http import JsonResponse
import csv
import io
import uuid

from .models import AddressLevel, AddressEntry
from .serializers import (
    AddressLevelSerializer,
    AddressEntryParentChainSerializer,
    AddressEntryTreeSerializer,
    AddressEntryMinimalSerializer,
    AddressEntryCreateSerializer,
)


# -------------------------------------------------------------------
# Configuration: adjust depth if you have deeper ancestor chains
# -------------------------------------------------------------------
PARENT_CHAIN_DEPTH = 5  # select_related depth for parent chain optimization


# ------------------------------
# Address Level ViewSet
# ------------------------------
class AddressLevelViewSet(viewsets.ModelViewSet):
    queryset = AddressLevel.objects.all()
    serializer_class = AddressLevelSerializer

    def get_queryset(self):
        return AddressLevel.objects.filter(is_active=True)

    def perform_destroy(self, instance):
        # Soft delete instead of hard delete
        instance.is_active = False
        instance.save()


# ------------------------------
# Address Entry ViewSet
# ------------------------------
class AddressEntryViewSet(viewsets.ModelViewSet):
    """
    - list() now returns upward parent-chain for each entry (child -> parent -> ...)
    - downward tree endpoints (tree/children/subtree) unchanged
    - /<pk>/upwards/ returns parent-chain for the specific entry (pk may be id or uuid)
    - /upwards_by_uuid/?uuid=... returns parent-chain by uuid query param
    """
    queryset = AddressEntry.objects.filter(is_active=True)
    # Base serializer_class isn't used much because get_serializer_class overrides it
    serializer_class = AddressEntryParentChainSerializer

    def _parent_select_related(self):
        """
        Build a tuple of select_related lookups like:
        ('parent', 'parent__parent', 'parent__parent__parent', ...)
        Stop at PARENT_CHAIN_DEPTH
        """
        parts = []
        for i in range(1, PARENT_CHAIN_DEPTH + 1):
            parts.append("__".join(["parent"] * i))
        return tuple(parts)

    # -------------
    # Serializer selection
    # -------------
    def get_serializer_class(self):
        # default list returns upward parent-chain
        if self.action == "list":
            return AddressEntryParentChainSerializer
        if self.action == "tree":
            return AddressEntryTreeSerializer
        if self.action in ["create", "update", "partial_update"]:
            return AddressEntryCreateSerializer
        if self.action in ["children", "subtree"]:
            return AddressEntryTreeSerializer
        if self.action in ["upwards", "upwards_by_uuid"]:
            return AddressEntryParentChainSerializer
        return AddressEntryParentChainSerializer

    # -------------
    # Queryset and performance optimization
    # -------------
    def get_queryset(self):
        """
        Apply filters and add select_related for parent chain optimization.
        Use query params: parent_id, parent_uuid, address_level_id
        """
        qs = AddressEntry.objects.filter(is_active=True)

        parent_id = self.request.query_params.get("parent_id")
        if parent_id:
            qs = qs.filter(parent_id=parent_id)

        parent_uuid = self.request.query_params.get("parent_uuid")
        if parent_uuid:
            qs = qs.filter(parent__uuid=parent_uuid)

        address_level_id = self.request.query_params.get("address_level_id")
        if address_level_id:
            qs = qs.filter(address_level_id=address_level_id)

        # Add select_related for parent chain to reduce queries when serializing parent chain
        parent_related = self._parent_select_related()
        # Also include address_level and top-level parent for joining
        qs = qs.select_related("address_level", "parent", *parent_related).prefetch_related("children")

        return qs.order_by("name")

    # -------------
    # Allow lookup by both ID and UUID for detail endpoints
    # -------------
    def get_object(self):
        pk = self.kwargs.get("pk")
        if pk is None:
            # Fallback to default behavior if not provided
            return super().get_object()
        # Try UUID first
        try:
            uuid.UUID(str(pk))
            return get_object_or_404(AddressEntry, uuid=pk, is_active=True)
        except (ValueError, AttributeError):
            return get_object_or_404(AddressEntry, id=pk, is_active=True)

    # ===================================================
    # DOWNWARD ENDPOINTS (kept as before)
    # ===================================================
    @action(detail=False, methods=["get"])
    def tree(self, request):
        roots = AddressEntry.objects.filter(parent__isnull=True, is_active=True).order_by("name")
        serializer = AddressEntryTreeSerializer(roots, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        node = self.get_object()
        children = node.children.filter(is_active=True).order_by("name")
        serializer = AddressEntryTreeSerializer(children, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def subtree(self, request, pk=None):
        node = self.get_object()
        serializer = AddressEntryTreeSerializer(node, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def hierarchy(self, request, pk=None):
        """
        Return some lightweight hierarchy metadata for a node (non-recursive)
        """
        node = self.get_object()
        return Response({
            "id": node.id,
            "uuid": node.uuid,
            "name": node.name,
            "full_path": getattr(node, "full_path", None),
            "address_level": node.address_level.name if node.address_level else None,
            "address_level_uuid": getattr(node.address_level, "uuid", None),
        })

    # Soft-delete override
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


# ------------------------------
# Address CSV Upload API
# ------------------------------
class AddressCSVUploadView(APIView):
    """
    Upload CSV where each column corresponds to AddressLevel order
    and parent-child relationship is derived from the row order.

    CSV format example:
    Country,Region,Zone,Woreda,Kebele
    Ethiopia,Addis Ababa,Zone 1,Woreda 1,Kebele 05
    ...
    """
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = file.read().decode("utf-8")
        except Exception:
            return Response({"error": "Could not decode file. Ensure UTF-8 encoded CSV."}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.reader(io.StringIO(decoded))
        rows = [row for row in reader if any(cell.strip() for cell in row)]  # remove empty rows

        # Get all active address levels ordered by their order field
        levels = list(AddressLevel.objects.filter(is_active=True).order_by("order"))
        if not levels:
            return Response({"error": "No address levels defined in the system"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                for row in rows:
                    parent = None
                    # iterate through columns, each column corresponds to a level
                    for idx, cell in enumerate(row):
                        name = cell.strip()
                        if not name:
                            continue
                        if idx >= len(levels):
                            raise ValueError(f"CSV row has more columns than configured AddressLevels (column {idx + 1})")
                        level = levels[idx]
                        # Create or get existing active entry for the given name/level/parent
                        obj, created = AddressEntry.objects.get_or_create(
                            name=name,
                            address_level=level,
                            parent=parent,
                            defaults={"is_active": True}
                        )
                        # If object exists but was inactive, reactivate it
                        if not obj.is_active:
                            obj.is_active = True
                            obj.save()
                        parent = obj
            return Response({"success": True}, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------
# Function-based helpers (UUID lookups)
# ------------------------------
@api_view(["GET"])
def get_address_by_uuid(request, uuid):
    try:
        entry = AddressEntry.objects.get(uuid=uuid, is_active=True)
    except AddressEntry.DoesNotExist:
        return Response({"error": "Address entry not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = AddressEntryParentChainSerializer(entry, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
def get_address_level_by_uuid(request, uuid):
    try:
        level = AddressLevel.objects.get(uuid=uuid, is_active=True)
    except AddressLevel.DoesNotExist:
        return Response({"error": "Address level not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = AddressLevelSerializer(level)
    return Response(serializer.data)
