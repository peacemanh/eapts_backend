# apps/person/urls/user_urls.py
from django.urls import path
from apps.person.views.auth_view import (
    TwoStepLoginAPIView,
    CompleteLoginAPIView,
    LogoutAPIView,
    GetCSRFAPIView,
    CurrentUserAPIView,
    ChangePasswordAPIView,
    UserAvailableLocationsAPIView,
    # Add token authentication views
    TokenLoginAPIView,
    TokenLogoutAPIView,
    VerifyTokenAPIView,
    RotateTokenAPIView,
    ListUserTokensAPIView,
)
from apps.person.views.user_view import (
    UserViewSet,
    GroupViewSet,
)

urlpatterns = [
    # =========================================================================
    # 🔐 TWO-STEP AUTHENTICATION ENDPOINTS
    # =========================================================================
    # Step 1: Username/Password validation
    path('auth/login/', TwoStepLoginAPIView.as_view(), name='auth-login-step1'),
    
    # Step 2: Location selection and login completion
    path('auth/login/complete/', CompleteLoginAPIView.as_view(), name='auth-login-step2'),
    
    # Logout
    path('auth/logout/', LogoutAPIView.as_view(), name='auth-logout'),
    
    # CSRF token
    path('auth/csrf/', GetCSRFAPIView.as_view(), name='auth-csrf'),
    
    # Current user information
    path('auth/current-user/', CurrentUserAPIView.as_view(), name='auth-current-user'),
    
    # Change password
    path('auth/change-password/', ChangePasswordAPIView.as_view(), name='auth-change-password'),
    
    # Get user's available locations
    path('auth/available-locations/', UserAvailableLocationsAPIView.as_view(), name='auth-available-locations'),
    
    # =========================================================================
    # 🔑 TOKEN AUTHENTICATION ENDPOINTS (for API access)
    # =========================================================================
    # Get authentication token
    path('auth/token/login/', TokenLoginAPIView.as_view(), name='auth-token-login'),
    
    # Delete/revoke token
    path('auth/token/logout/', TokenLogoutAPIView.as_view(), name='auth-token-logout'),
    
    # Verify token validity
    path('auth/token/verify/', VerifyTokenAPIView.as_view(), name='auth-token-verify'),
    
    # Rotate/refresh token
    path('auth/token/rotate/', RotateTokenAPIView.as_view(), name='auth-token-rotate'),
    
    # List user tokens
    path('auth/token/list/', ListUserTokensAPIView.as_view(), name='auth-token-list'),

    # =========================================================================
    # 👤 USER MANAGEMENT ENDPOINTS
    # =========================================================================
    
    # Basic CRUD operations
    path('users/', UserViewSet.as_view({
        'get': 'list',           # List all users
        'post': 'create'         # Create new user
    }), name='user-list'),
    
    path('users/<int:pk>/', UserViewSet.as_view({
        'get': 'retrieve',       # Get user details
        'put': 'update',         # Full update user
        'patch': 'partial_update',  # Partial update user
        'delete': 'destroy'      # Delete user
    }), name='user-detail'),
    
    # 🔧 User Status Management
    path('users/<int:pk>/change-status/', UserViewSet.as_view({
        'post': 'change_status'  # Change user status (active/inactive/suspended/pending)
    }), name='user-change-status'),
    
    # 👥 Group Management for Users
    path('users/<int:pk>/groups/', UserViewSet.as_view({
        'get': 'groups'          # Get user's groups with permissions
    }), name='user-groups'),
    
    path('users/<int:pk>/assign-group/', UserViewSet.as_view({
        'post': 'assign_group'   # Assign group to user
    }), name='user-assign-group'),
    
    path('users/<int:pk>/remove-group/', UserViewSet.as_view({
        'post': 'remove_group'   # Remove group from user
    }), name='user-remove-group'),
    
    # 🔑 Permission Management for Users
    path('users/<int:pk>/permissions/', UserViewSet.as_view({
        'get': 'permissions'     # Get user's comprehensive permissions
    }), name='user-permissions'),
    
    path('users/<int:pk>/assign-permission/', UserViewSet.as_view({
        'post': 'assign_permission'  # Assign direct permission to user
    }), name='user-assign-permission'),
    
    path('users/<int:pk>/remove-permission/', UserViewSet.as_view({
        'post': 'remove_permission'  # Remove direct permission from user
    }), name='user-remove-permission'),
    
    # 👨‍💼 Staff Management
    path('users/<int:pk>/make-staff/', UserViewSet.as_view({
        'post': 'make_staff'     # Grant staff access to user
    }), name='user-make-staff'),
    
    path('users/<int:pk>/remove-staff/', UserViewSet.as_view({
        'post': 'remove_staff'   # Remove staff access from user
    }), name='user-remove-staff'),
    
    # 📊 User Lists and Filters
    path('users/filter/active/', UserViewSet.as_view({
        'get': 'active_users'    # Get all active users with statistics
    }), name='user-active'),
    
    path('users/filter/staff/', UserViewSet.as_view({
        'get': 'staff_users'     # Get all staff users
    }), name='user-staff'),
    
    # =========================================================================
    # 👥 GROUP MANAGEMENT ENDPOINTS
    # =========================================================================
    
    # Basic CRUD operations for groups
    path('groups/', GroupViewSet.as_view({
        'get': 'list',           # List all groups
        'post': 'create'         # Create new group
    }), name='group-list'),
    
    path('groups/<int:pk>/', GroupViewSet.as_view({
        'get': 'retrieve',       # Get group details
        'put': 'update',         # Full update group
        'patch': 'partial_update',  # Partial update group
        'delete': 'destroy'      # Delete group
    }), name='group-detail'),
    
    # Group User Relationships
    path('groups/<int:pk>/users/', GroupViewSet.as_view({
        'get': 'users'           # Get all users in this group
    }), name='group-users'),
    
    # Group Permission Management
    path('groups/<int:pk>/permissions/', GroupViewSet.as_view({
        'get': 'permissions'     # Get all permissions for this group
    }), name='group-permissions'),
    
    path('groups/<int:pk>/assign-permission/', GroupViewSet.as_view({
        'post': 'assign_permission'  # Assign permission to group
    }), name='group-assign-permission'),
]