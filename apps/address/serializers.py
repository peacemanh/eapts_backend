from rest_framework import serializers
from .models import AddressLevel, AddressEntry


# ----------------------------
# Address Level Serializer
# ----------------------------
class AddressLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AddressLevel
        fields = "__all__"
        read_only_fields = ["id", "uuid"]


# ----------------------------
# Upward Parent Chain Serializer (for list + detail)
# ----------------------------
class AddressEntryParentChainSerializer(serializers.ModelSerializer):
    parent = serializers.SerializerMethodField()
    address_level = AddressLevelSerializer(read_only=True)
    uuid = serializers.UUIDField(read_only=True)

    class Meta:
        model = AddressEntry
        fields = [
            "id",
            "uuid",
            "name",
            "address_code",
            "address_level",
            "latitude",
            "longitude",
            "is_active",
            "parent",
        ]
        read_only_fields = ["id", "uuid"]

    def get_parent(self, obj):
        """
        Recursively serialize parent -> parent's parent -> ... until None.
        NOTE: to avoid N+1 DB queries, ensure the view's queryset uses select_related
        for parent__parent... up to an expected depth.
        """
        parent = getattr(obj, "parent", None)
        if not parent:
            return None
        # Recursively use the same serializer
        return AddressEntryParentChainSerializer(parent, context=self.context).data


# ----------------------------
# Downward Tree Serializer (parent -> children)
# ----------------------------
class AddressEntryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    address_level = AddressLevelSerializer(read_only=True)
    uuid = serializers.UUIDField(read_only=True)

    class Meta:
        model = AddressEntry
        fields = [
            "id",
            "uuid",
            "name",
            "address_level",
            "parent",
            "address_code",
            "latitude",
            "longitude",
            "is_active",
            "children",
        ]
        read_only_fields = ["id", "uuid"]

    def get_children(self, obj):
        qs = obj.children.filter(is_active=True).order_by("name")
        # Use same serializer for recursion
        return AddressEntryTreeSerializer(qs, many=True, context=self.context).data


# ----------------------------
# Minimal Serializer (for dropdowns etc.)
# ----------------------------
class AddressEntryMinimalSerializer(serializers.ModelSerializer):
    uuid = serializers.UUIDField(read_only=True)
    address_level_name = serializers.CharField(source="address_level.name", read_only=True)
    address_level_uuid = serializers.UUIDField(source="address_level.uuid", read_only=True)

    class Meta:
        model = AddressEntry
        fields = ["id", "uuid", "name", "address_level", "address_level_name", "address_level_uuid", "address_code"]
        read_only_fields = ["id", "uuid"]


# ----------------------------
# Create / Update Serializer
# ----------------------------
class AddressEntryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AddressEntry
        fields = [
            "name",
            "address_level",
            "parent",
            "address_code",
            "latitude",
            "longitude",
            "is_active",
        ]

    def validate(self, data):
        name = data.get("name")
        level = data.get("address_level")
        parent = data.get("parent")

        if AddressEntry.objects.filter(name=name, address_level=level, parent=parent, is_active=True).exists():
            raise serializers.ValidationError(
                "An active address entry with the same name, level and parent already exists."
            )
        return data