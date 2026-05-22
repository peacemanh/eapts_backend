import re
import logging
from typing import Dict, Any

from rest_framework import serializers
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.core.validators import validate_email
from django.contrib.auth.base_user import BaseUserManager
from django.apps import apps

from apps.person.serializers.person_serializer import (
    PersonSerializer, 
    PersonWithAddressSerializer,
    PersonCreateSerializer
)
from apps.person.models.user import User
from apps.person.models.person import Person, PersonName

logger = logging.getLogger(__name__)


class PermissionSerializer(serializers.ModelSerializer):
    """Enhanced Permission Serializer with content type details"""
    content_type_name = serializers.CharField(source='content_type.model', read_only=True)
    app_label = serializers.CharField(source='content_type.app_label', read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'content_type', 'content_type_name', 'app_label']
        read_only_fields = fields


class GroupSerializer(serializers.ModelSerializer):
    """Enhanced Group Serializer"""
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'user_count']
        read_only_fields = ['user_count']

    def get_user_count(self, obj) -> int:
        return obj.user_set.count()


class GroupWithPermissionsSerializer(GroupSerializer):
    """Group Serializer with detailed permissions"""
    permissions = PermissionSerializer(many=True, read_only=True)
    permissions_detail = serializers.SerializerMethodField()

    class Meta(GroupSerializer.Meta):
        model = Group
        fields = GroupSerializer.Meta.fields + ['permissions', 'permissions_detail']

    def get_permissions_detail(self, obj) -> Dict[str, Any]:
        """Group permissions by app for better organization"""
        permissions_by_app = {}
        for perm in obj.permissions.all():
            app_label = perm.content_type.app_label
            if app_label not in permissions_by_app:
                permissions_by_app[app_label] = []
            permissions_by_app[app_label].append({
                'id': perm.id,
                'name': perm.name,
                'codename': perm.codename,
                'model': perm.content_type.model
            })
        return permissions_by_app


class PersonDataSerializer(serializers.Serializer):
    """Serializer for person_data field in UserCreateSerializer"""
    gender = serializers.ChoiceField(choices=Person.Gender.choices)
    birthdate = serializers.DateField(required=False, allow_null=True)
    contact_info = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    location = serializers.IntegerField(required=False, allow_null=True)
    given_name = serializers.CharField(required=True, max_length=100)
    middle_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    
    def validate_location(self, value):
        """Validate location exists"""
        if value:
            try:
                Location = apps.get_model('locations', 'Location')
                if not Location.objects.filter(id=value).exists():
                    raise serializers.ValidationError(_("Selected location does not exist."))
            except LookupError:
                raise serializers.ValidationError(_("Locations app is not available."))
        return value


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Production-grade User Creation Serializer
    Creates person first, then user with person_id
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=8,
        max_length=128,
        help_text=_("Password must be at least 8 characters long")
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    person_id = serializers.PrimaryKeyRelatedField(
        queryset=Person.objects.all(),
        source='person',
        write_only=True,
        required=False,
        allow_null=True
    )
    person_data = PersonDataSerializer(write_only=True, required=False)
    groups = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        many=True,
        required=False,
        write_only=True
    )

    class Meta:
        model = User
        fields = [
            'username', 'password', 'password_confirm', 'status', 'email',
            'first_name', 'last_name', 'person_id', 'person_data', 'groups'
        ]
        extra_kwargs = {
            'username': {
                'help_text': _('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.')
            },
            'email': {
                'required': True,
                'help_text': _('A valid email address is required.')
            }
        }

    def validate_username(self, value: str) -> str:
        """Enhanced username validation"""
        if not re.match(r'^[\w.@+-]+\Z', value):
            raise serializers.ValidationError(
                _("Username can only contain letters, digits and @/./+/-/_ characters.")
            )
        
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(_("A user with that username already exists."))
        
        return value.lower()

    def validate_email(self, value: str) -> str:
        """Enhanced email validation"""
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError(_("Enter a valid email address."))
        
        if not value:
            raise serializers.ValidationError(_("Email address is required."))
        
        normalized_email = BaseUserManager.normalize_email(value)
        
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError(_("A user with that email already exists."))
        
        return normalized_email

    def validate_password(self, value: str) -> str:
        """Enhanced password validation using Django's password validators"""
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        
        # Additional custom validation
        common_passwords = ['password', '12345678', 'admin123', 'qwerty123', 'letmein']
        if value.lower() in common_passwords:
            raise serializers.ValidationError(_("This password is too common."))
        
        # Check for username in password
        username = self.initial_data.get('username', '')
        if username and username.lower() in value.lower():
            raise serializers.ValidationError(_("Password cannot contain your username."))
        
        return value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive validation"""
        # Password confirmation
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({
                "password_confirm": _("Passwords do not match.")
            })
        
        # Person validation
        has_person_id = 'person' in attrs
        has_person_data = 'person_data' in attrs
        
        if not has_person_id and not has_person_data:
            raise serializers.ValidationError({
                "person": _("Either provide an existing person_id or data to create a new person.")
            })
        
        if has_person_id and has_person_data:
            raise serializers.ValidationError({
                "person": _("Cannot provide both person_id and person_data. Choose one.")
            })
        
        return attrs

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> User:
        """Atomic user creation - creates person first, then user"""
        password = validated_data.pop('password')
        validated_data.pop('password_confirm')
        person_data = validated_data.pop('person_data', None)
        groups = validated_data.pop('groups', [])
        
        try:
            # Handle person creation/assignment
            if 'person' in validated_data:
                # Use existing person
                person = validated_data['person']
                if hasattr(person, 'user') and person.user.exists():
                    raise serializers.ValidationError({
                        "person": _("This person is already associated with a user.")
                    })
            elif person_data:
                # Extract name data separately from person data
                given_name = person_data.pop('given_name')
                middle_name = person_data.pop('middle_name', '')
                last_name = person_data.pop('last_name')
                
                # Handle location ID - IMPORTANT FIX: pop it and convert to object
                location_id = person_data.pop('location', None)
                if location_id:
                    try:
                        Location = apps.get_model('locations', 'Location')
                        location = Location.objects.get(id=location_id)
                        person_data['location'] = location
                    except Location.DoesNotExist:
                        raise serializers.ValidationError({
                            "person_data": {"location": _("Selected location does not exist.")}
                        })
                    except LookupError:
                        # If locations app doesn't exist, remove location field
                        logger.warning("Locations app not available, location will be skipped")
                        person_data.pop('location', None)
                
                # Create person object
                person = Person.objects.create(**person_data)
                
                # Create person name
                PersonName.objects.create(
                    person=person,
                    given_name=given_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    preferred=True
                )
                
                validated_data['person'] = person
            else:
                raise serializers.ValidationError(_("Person information is required."))
            
            # Ensure email is provided
            if not validated_data.get('email'):
                raise serializers.ValidationError({
                    "email": _("Email address is required.")
                })
            
            # Create user
            user = User.objects.create(
                username=validated_data['username'],
                email=validated_data['email'],
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                status=validated_data.get('status', User.Status.ACTIVE),
                person=person
            )
            
            # Set password
            user.set_password(password)
            user.save()
            
            # Add groups if provided
            if groups:
                user.groups.set(groups)
            
            logger.info(f"User created successfully: {user.username} (ID: {user.id}, Person ID: {person.id})")
            return user
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}", exc_info=True)
            raise serializers.ValidationError(_("Error creating user. Please try again."))


# ... (rest of the serializers remain the same) ...
class UserBaseSerializer(serializers.ModelSerializer):
    """Base user serializer with common fields and methods"""
    person = PersonSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    created_at = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    updated_at = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = User
        fields = [
            'id', 'username', 'status', 'last_login', 'created_at', 'updated_at',
            'person', 'email', 'first_name', 'last_name', 'is_active', 
            'is_staff', 'is_superuser'
        ]
        read_only_fields = [
            'id', 'last_login', 'created_at', 'updated_at', 
            'is_staff', 'is_superuser'
        ]

    def validate_email(self, value: str) -> str:
        """Email validation that excludes current user"""
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError(_("Enter a valid email address."))
        
        if not value:
            raise serializers.ValidationError(_("Email address is required."))
        
        normalized_email = BaseUserManager.normalize_email(value)
        
        # Check for duplicate emails, excluding current instance
        queryset = User.objects.filter(email__iexact=normalized_email)
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError(_("A user with that email already exists."))
        
        return normalized_email

    def update(self, instance: User, validated_data: Dict[str, Any]) -> User:
        """Enhanced update with selective field saving"""
        # Handle password separately if provided
        password = validated_data.pop('password', None)
        
        if password:
            instance.set_password(password)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class UserSerializer(UserBaseSerializer):
    """Basic user serializer for list views"""
    groups = GroupSerializer(many=True, read_only=True)

    class Meta(UserBaseSerializer.Meta):
        model = User
        fields = UserBaseSerializer.Meta.fields + ['groups']


class UserDetailSerializer(UserSerializer):
    """Detailed user serializer for single object retrieval"""
    user_permissions = PermissionSerializer(many=True, read_only=True)
    groups_detail = GroupWithPermissionsSerializer(source='groups', many=True, read_only=True)

    class Meta(UserSerializer.Meta):
        model = User
        fields = UserSerializer.Meta.fields + ['user_permissions', 'groups_detail']


class UserWithAddressSerializer(UserDetailSerializer):
    """User serializer with complete address information"""
    person = PersonWithAddressSerializer(read_only=True)

    class Meta(UserDetailSerializer.Meta):
        model = User
        fields = UserDetailSerializer.Meta.fields


class UserWithPermissionsSerializer(UserWithAddressSerializer):
    """Comprehensive user serializer with full permission context"""
    all_permissions = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta(UserWithAddressSerializer.Meta):
        model = User
        fields = UserWithAddressSerializer.Meta.fields + ['all_permissions', 'effective_permissions']

    def get_all_permissions(self, obj: User) -> list:
        """Get all permissions (Django's built-in method)"""
        if self.context.get('request') and self.context['request'].user.is_staff:
            return sorted(list(obj.get_all_permissions()))
        return []

    def get_effective_permissions(self, obj: User) -> Dict[str, Any]:
        """Get organized permission information"""
        if self.context.get('request') and self.context['request'].user.is_staff:
            direct_perms = obj.user_permissions.all()
            group_perms = Permission.objects.filter(group__user=obj).distinct()
            
            return {
                'direct_permissions': PermissionSerializer(direct_perms, many=True).data,
                'group_permissions': PermissionSerializer(group_perms, many=True).data,
                'is_superuser': obj.is_superuser,
                'is_staff': obj.is_staff
            }
        return {}


class ChangePasswordSerializer(serializers.Serializer):
    """
    Production-grade password change serializer with comprehensive validation
    """
    old_password = serializers.CharField(
        required=True, 
        write_only=True, 
        style={'input_type': 'password'},
        help_text=_("Your current password")
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
        min_length=8,
        max_length=128,
        help_text=_("New password (at least 8 characters)")
    )
    new_password_confirm = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
        help_text=_("Confirm your new password")
    )

    def validate_old_password(self, value: str) -> str:
        """Validate old password"""
        user = self.context.get('request').user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Current password is incorrect."))
        return value

    def validate_new_password(self, value: str) -> str:
        """Validate new password using Django's validators"""
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        
        # Check if new password is same as old
        user = self.context.get('request').user
        if user.check_password(value):
            raise serializers.ValidationError(_("New password must be different from old password."))
        
        return value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Final validation"""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password_confirm": _("New passwords do not match.")
            })
        
        return attrs


class LoginSerializer(serializers.Serializer):
    """
    Enhanced login serializer with security features
    """
    username = serializers.CharField(
        required=True,
        max_length=150,
        help_text=_("Your username")
    )
    password = serializers.CharField(
        required=True,
        style={'input_type': 'password'},
        max_length=128,
        help_text=_("Your password")
    )
    remember_me = serializers.BooleanField(
        required=False,
        default=False,
        help_text=_("Stay logged in for longer period")
    )

    def validate_username(self, value: str) -> str:
        """Clean username"""
        return value.strip().lower()


class UserStatusSerializer(serializers.Serializer):
    """
    User status change serializer with validation
    """
    status = serializers.ChoiceField(
        choices=User.Status.choices,
        required=True,
        help_text=f"Available statuses: {', '.join([choice[0] for choice in User.Status.choices])}"
    )
    reason = serializers.CharField(
        required=False,
        max_length=500,
        allow_blank=True,
        help_text=_("Optional reason for status change")
    )

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Additional validation with context"""
        user = self.context.get('user')
        request_user = self.context.get('request').user
        
        if user and request_user:
            # Prevent self-deactivation
            if data['status'] == User.Status.INACTIVE and user == request_user:
                raise serializers.ValidationError({
                    "status": _("Cannot deactivate your own account.")
                })
        
        return data