# apps/person/views/user_view.py
import logging
from typing import Any, Dict

from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.throttling import UserRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import Group, Permission
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.db.models import Prefetch, Q

from apps.person.serializers.user_serializer import (
    UserSerializer, 
    UserWithAddressSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    UserWithPermissionsSerializer,
    UserStatusSerializer,
    GroupSerializer,
    GroupWithPermissionsSerializer,
    PermissionSerializer
)

from apps.person.views.person_view import BasePersonView
from apps.person.models.user import User

from rest_framework.pagination import PageNumberPagination

logger = logging.getLogger(__name__)


class UserActionThrottle(UserRateThrottle):
    """Custom throttle for user actions"""
    scope = 'user_actions'
    rate = '10/minute'


class BaseUserView(BasePersonView):
    """Extends BasePersonView to inherit query optimization with enhanced features"""
    
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        """Override permissions based on action"""
        if self.action in ['create', 'destroy', 'make_staff', 'remove_staff', 
                          'assign_permission', 'remove_permission', 'list']:
            return [IsAdminUser()]
        elif self.action in ['change_password', 'assign_group', 'remove_group', 
                           'change_status', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['active_users', 'staff_users']:
            return [IsAuthenticated()]
        return super().get_permissions()
    
    def handle_exception(self, exc):
        """Enhanced exception handling with logging"""
        logger.error(f"UserView exception: {exc}", exc_info=True)
        
        if isinstance(exc, (serializers.ValidationError,)):
            return Response(
                {"error": _("Validation error"), "details": exc.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif isinstance(exc, User.DoesNotExist):
            return Response(
                {"error": _("User not found")},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Log unexpected errors but don't expose details to client
        logger.exception("Unexpected error in UserView")
        return Response(
            {"error": _("An unexpected error occurred")},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'results': data
        })


class UserViewSet(BaseUserView, viewsets.ModelViewSet):
    """
    Production-grade User ViewSet with comprehensive features
    """
    pagination_class = StandardResultsSetPagination
    
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'person__location', 'is_staff', 'is_superuser']
    search_fields = [
        'username', 'email', 'first_name', 'last_name',
        'person__names__given_name', 'person__names__last_name',
        'person__contact_info'
    ]
    ordering_fields = [
        'username', 'email', 'created_at', 'updated_at', 
        'last_login', 'is_staff', 'is_superuser'
    ]
    ordering = ['-created_at']
    throttle_classes = [UserActionThrottle]

    def get_serializer_class(self):
        """Return appropriate serializer based on action and query parameters"""
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action == 'retrieve':
            include_permissions = self.request.query_params.get('include_permissions', '').lower() in ('true', '1', 'yes')
            include_address = self.request.query_params.get('include_address', '').lower() in ('true', '1', 'yes')
            
            if include_permissions:
                return UserWithPermissionsSerializer
            elif include_address:
                return UserWithAddressSerializer
            return UserDetailSerializer
        
        return super().get_serializer_class()

    def get_queryset(self):
        """Highly optimized queryset with comprehensive prefetching"""
        queryset = User.objects.select_related(
            'person',
            'person__location'
        ).prefetch_related(
            Prefetch('groups', queryset=Group.objects.prefetch_related('permissions')),
            'user_permissions',
            Prefetch('person__names', to_attr='prefetched_names')
        )
        
        # Advanced filtering
        username = self.request.query_params.get('username')
        if username:
            queryset = queryset.filter(username__icontains=username)
            
        email = self.request.query_params.get('email')
        if email:
            queryset = queryset.filter(email__icontains=email)
            
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Only show active users by default for non-staff
        if not self.request.user.is_staff and self.action == 'list':
            queryset = queryset.filter(is_active=True)
            
        return queryset.distinct()

    def list(self, request, *args, **kwargs):
        """Enhanced list with pagination and metadata"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Apply page_size from request
        page_size = request.query_params.get('page_size', 10)
        try:
            page_size = int(page_size)
        except (ValueError, TypeError):
            page_size = 10
            
        # Set pagination
        self.pagination_class.page_size = page_size
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'total_pages': 1,
            'current_page': 1,
            'page_size': queryset.count(),
            'results': serializer.data
        })

    def retrieve(self, request, *args, **kwargs):
        """Optimized single user retrieval"""
        try:
            instance = self.get_object()
            
            # Permission check: users can view their own profile, staff can view any
            if not request.user.is_staff and instance != request.user:
                return Response(
                    {"error": _("You do not have permission to view this user.")},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
            
        except User.DoesNotExist:
            return Response(
                {"error": _("User not found")},
                status=status.HTTP_404_NOT_FOUND
            )

    @transaction.atomic
    def perform_create(self, serializer):
        """Enhanced user creation with transaction safety"""
        try:
            user = serializer.save()
            logger.info(f"User created: {user.username} (ID: {user.id})")
        except serializers.ValidationError as e:
            logger.error(f"User creation validation error: {e.detail}")
            raise
        except Exception as e:
            logger.error(f"User creation failed: {e}", exc_info=True)
            raise serializers.ValidationError(_("User creation failed"))

    @transaction.atomic
    def perform_update(self, serializer):
        """Enhanced user update"""
        try:
            user = serializer.save()
            logger.info(f"User updated: {user.username} (ID: {user.id})")
        except Exception as e:
            logger.error(f"User update failed: {e}", exc_info=True)
            raise serializers.ValidationError(_("User update failed"))

    @transaction.atomic
    def perform_destroy(self, instance):
        """Enhanced user deletion - soft delete by deactivating"""
        try:
            username = instance.username
            user_id = instance.id
            
            # Soft delete by deactivating
            instance.status = User.Status.INACTIVE
            instance.save(update_fields=['status', 'updated_at'])
            
            logger.info(f"User deactivated: {username} (ID: {user_id})")
                
        except Exception as e:
            logger.error(f"User deletion failed: {e}", exc_info=True)
            raise

    @action(detail=True, methods=['post'], throttle_classes=[UserActionThrottle])
    def change_status(self, request, pk=None):
        """Enhanced status change with validation"""
        user = self.get_object()
        
        # Permission check
        if not request.user.is_staff and user != request.user:
            return Response(
                {"error": _("You do not have permission to change this user's status.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = UserStatusSerializer(
            data=request.data, 
            context={'user': user, 'request': request}
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        new_status = serializer.validated_data['status']
        old_status = user.status
        
        try:
            with transaction.atomic():
                user.status = new_status
                user.save(update_fields=['status', 'updated_at'])
                
                logger.info(f"User status changed: {user.username} from {old_status} to {new_status}")
                
                return Response({
                    "success": _("Status updated successfully"),
                    "old_status": old_status,
                    "new_status": new_status,
                    "user_id": user.id,
                    "timestamp": timezone.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Status change failed: {e}", exc_info=True)
            return Response(
                {"error": _("Status update failed")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def groups(self, request, pk=None):
        """Get user groups with permissions"""
        user = self.get_object()
        
        # Permission check
        if not request.user.is_staff and user != request.user:
            return Response(
                {"error": _("You do not have permission to view this user's groups.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_groups = user.groups.prefetch_related('permissions').all()
        serializer = GroupWithPermissionsSerializer(user_groups, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def assign_group(self, request, pk=None):
        """Assign group to user with validation"""
        user = self.get_object()
        group_id = request.data.get('group_id')
        
        # Only staff can assign groups
        if not request.user.is_staff:
            return Response(
                {"error": _("Only staff members can assign groups.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not group_id:
            return Response(
                {"error": _("Group ID is required")}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                group = Group.objects.get(id=group_id)
                user.groups.add(group)
                
                logger.info(f"Group {group.name} assigned to user {user.username}")
                
                return Response({
                    "success": _("Group assigned successfully"),
                    "group": GroupSerializer(group).data,
                    "user_id": user.id
                })
                
        except Group.DoesNotExist:
            return Response(
                {"error": _("Group not found")}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def remove_group(self, request, pk=None):
        """Remove group from user"""
        user = self.get_object()
        group_id = request.data.get('group_id')
        
        # Only staff can remove groups
        if not request.user.is_staff:
            return Response(
                {"error": _("Only staff members can remove groups.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not group_id:
            return Response(
                {"error": _("Group ID is required")}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                group = Group.objects.get(id=group_id)
                user.groups.remove(group)
                
                logger.info(f"Group {group.name} removed from user {user.username}")
                
                return Response({"success": _("Group removed successfully")})
                
        except Group.DoesNotExist:
            return Response(
                {"error": _("Group not found")}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'])
    def permissions(self, request, pk=None):
        """Comprehensive permissions overview"""
        user = self.get_object()
        
        # Permission check
        if not request.user.is_staff and user != request.user:
            return Response(
                {"error": _("You do not have permission to view this user's permissions.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        all_permissions = user.get_all_permissions()
        direct_permissions = user.user_permissions.all()
        group_permissions = Permission.objects.filter(group__user=user).distinct()
        
        return Response({
            "all_permissions": sorted(list(all_permissions)),
            "direct_permissions": PermissionSerializer(direct_permissions, many=True).data,
            "group_permissions": PermissionSerializer(group_permissions, many=True).data,
            "is_superuser": user.is_superuser,
            "is_staff": user.is_staff
        })

    @action(detail=True, methods=['post'])
    def assign_permission(self, request, pk=None):
        """Assign a direct permission to user."""
        user = self.get_object()
        permission_id = request.data.get('permission_id')
        
        # Only staff can assign permissions
        if not request.user.is_staff:
            return Response(
                {"error": _("Only staff members can assign permissions.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not permission_id:
            return Response(
                {"error": _("Permission ID is required")}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                permission = Permission.objects.get(id=permission_id)
                user.user_permissions.add(permission)
                
                logger.info(f"Permission {permission.codename} assigned to user {user.username}")
                
                return Response({
                    "success": _("Permission assigned successfully"),
                    "permission": PermissionSerializer(permission).data
                })
        except Permission.DoesNotExist:
            return Response(
                {"error": _("Permission not found")}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def remove_permission(self, request, pk=None):
        """Remove a direct permission from user."""
        user = self.get_object()
        permission_id = request.data.get('permission_id')
        
        # Only staff can remove permissions
        if not request.user.is_staff:
            return Response(
                {"error": _("Only staff members can remove permissions.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not permission_id:
            return Response(
                {"error": _("Permission ID is required")}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                permission = Permission.objects.get(id=permission_id)
                user.user_permissions.remove(permission)
                
                logger.info(f"Permission {permission.codename} removed from user {user.username}")
                
                return Response({"success": _("Permission removed successfully")})
        except Permission.DoesNotExist:
            return Response(
                {"error": _("User does not have this permission")}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def active_users(self, request):
        """Get active users with statistics"""
        active_users = self.get_queryset().filter(is_active=True)
        page = self.paginate_queryset(active_users)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                'users': serializer.data,
                'metadata': {
                    'total_active': active_users.count(),
                    'timestamp': timezone.now().isoformat()
                }
            })
        
        serializer = self.get_serializer(active_users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def staff_users(self, request):
        """Get staff users"""
        staff_users = self.get_queryset().filter(is_staff=True, is_active=True)
        page = self.paginate_queryset(staff_users)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(staff_users, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def make_staff(self, request, pk=None):
        """Grant staff access"""
        user = self.get_object()
        
        # Only staff can grant staff access
        if not request.user.is_staff:
            return Response(
                {"error": _("Only staff members can grant staff access.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if user.is_staff:
            return Response(
                {"warning": _("User already has staff access")},
                status=status.HTTP_200_OK
            )
        
        user.is_staff = True
        user.save(update_fields=['is_staff', 'updated_at'])
        
        logger.info(f"Staff access granted to user: {user.username}")
        
        return Response({
            "success": _("User granted staff access"),
            "is_staff": True,
            "user_id": user.id
        })

    @action(detail=True, methods=['post'])
    def remove_staff(self, request, pk=None):
        """Remove staff access"""
        user = self.get_object()
        
        # Only staff can remove staff access
        if not request.user.is_staff:
            return Response(
                {"error": _("Only staff members can remove staff access.")},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not user.is_staff:
            return Response(
                {"warning": _("User does not have staff access")},
                status=status.HTTP_200_OK
            )
        
        user.is_staff = False
        user.save(update_fields=['is_staff', 'updated_at'])
        
        logger.info(f"Staff access removed from user: {user.username}")
        
        return Response({
            "success": _("Staff access removed from user"),
            "is_staff": False,
            "user_id": user.id
        })


class GroupViewSet(viewsets.ModelViewSet):
    """
    Production-grade Group ViewSet
    """
    queryset = Group.objects.prefetch_related('permissions', 'user_set')
    serializer_class = GroupWithPermissionsSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name']
    search_fields = ['name']
    ordering_fields = ['name']
    permission_classes = [IsAdminUser]
    throttle_classes = [UserActionThrottle]
    
    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return GroupWithPermissionsSerializer
        return GroupSerializer
    
    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """Get all users in this group"""
        group = self.get_object()
        users = group.user_set.filter(is_active=True)
        serializer = UserSerializer(users, many=True)
        
        return Response({
            'users': serializer.data,
            'count': users.count(),
            'group': GroupSerializer(group).data
        })
    
    @action(detail=True, methods=['get'])
    def permissions(self, request, pk=None):
        """Get all permissions for this group"""
        group = self.get_object()
        permissions = group.permissions.all()
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def assign_permission(self, request, pk=None):
        """Assign permission to group"""
        group = self.get_object()
        permission_id = request.data.get('permission_id')
        
        if not permission_id:
            return Response(
                {"error": _("Permission ID is required")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            permission = Permission.objects.get(id=permission_id)
            group.permissions.add(permission)
            
            logger.info(f"Permission {permission.codename} assigned to group {group.name}")
            
            return Response({
                "success": _("Permission assigned successfully"),
                "permission": PermissionSerializer(permission).data
            })
            
        except Permission.DoesNotExist:
            return Response(
                {"error": _("Permission not found")},
                status=status.HTTP_404_NOT_FOUND
            )