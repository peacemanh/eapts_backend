# apps/person/views/auth_view.py
import logging
from typing import List
from django.core.cache import cache

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.generics import GenericAPIView
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db import transaction

# Add these imports for token authentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.serializers import AuthTokenSerializer

from apps.person.serializers.user_serializer import (
    LoginSerializer,
    ChangePasswordSerializer,
    UserWithPermissionsSerializer
)
from apps.person.models.user import User
from apps.locations.models import Location

logger = logging.getLogger(__name__)


class AuthenticationThrottle(AnonRateThrottle):
    """Custom throttle for authentication endpoints"""
    scope = 'authentication'
    rate = '5/minute'


class UserActionThrottle(UserRateThrottle):
    """Custom throttle for user actions"""
    scope = 'user_actions'
    rate = '10/minute'


class HealthCheckAPIView(GenericAPIView):
    """Health check endpoint"""
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def get(self, request):
        return Response({
            "status": "healthy",
            "service": "Health‑Dosé Authentication",
            "timestamp": timezone.now().isoformat(),
            "version": "1.0.0"
        })


class GetCSRFAPIView(GenericAPIView):
    """CSRF Token API"""
    serializer_class = serializers.Serializer
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def get(self, request):
        """
        Django's CsrfViewMiddleware automatically sets the CSRF cookie.
        This endpoint just needs to be called to trigger it.
        """
        return Response({
            "detail": "CSRF cookie set",
            "timestamp": timezone.now().isoformat()
        })


class TwoStepLoginAPIView(GenericAPIView):
    """Two-step login process with location hierarchy"""
    serializer_class = LoginSerializer
    throttle_classes = [AuthenticationThrottle]
    permission_classes = [AllowAny]
    
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request):
        """Step 1: Username/Password validation"""
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            data = serializer.validated_data
            username = data['username']
            password = data['password']
            
            # Check for brute force protection
            ip_address = self._get_client_ip(request)
            cache_key = f"login_attempts:{username}:{ip_address}"
            attempts = cache.get(cache_key, 0)
            
            if attempts >= 5:
                logger.warning(f"Too many login attempts for user: {username} from IP: {ip_address}")
                return Response(
                    {"error": _("Too many login attempts. Please try again later.")},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            user = authenticate(username=username, password=password)
            
            if user is None:
                # Increment failed attempts
                cache.set(cache_key, attempts + 1, timeout=900)  # 15 minutes
                logger.warning(f"Failed login attempt for user: {username} from IP: {ip_address}")
                return Response(
                    {"error": _("Invalid credentials")}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Check if user is active
            if not user.is_active:
                return Response(
                    {"error": _("Account is deactivated")},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Get user's registered location from Person model
            user_location = self._get_user_location(user)
            
            if not user_location:
                return Response(
                    {"error": _("User location not configured. Please contact administrator.")},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get all child locations (including the user's location itself)
            available_locations = self._get_all_child_locations(user_location)
            
            if not available_locations:
                # If no locations found, at least include the user's location
                available_locations = [self._location_to_dict(user_location, depth=0)]
            
            # Create a temporary session token for step 2
            session_token = self._generate_session_token()
            cache.set(
                f"login_session:{session_token}",
                {
                    'user_id': user.id,
                    'username': user.username,
                    'user_location_id': user_location.id,
                    'step': 2,
                    'expires': timezone.now() + timezone.timedelta(minutes=5)
                },
                timeout=300  # 5 minutes
            )
            
            return Response({
                "success": _("Credentials verified. Please select location."),
                "session_token": session_token,
                "available_locations": available_locations,
                "user_info": {
                    "username": user.username,
                    "full_name": user.get_full_name(),
                    "email": user.email,
                    "primary_location": {
                        "id": user_location.id,
                        "name": user_location.name,
                        "code": getattr(user_location, 'code', ''),
                    }
                },
                "location_hierarchy": {
                    "root_location_id": user_location.id,
                    "total_locations": len(available_locations)
                }
            })
            
        except Exception as e:
            logger.error(f"Login step 1 error: {e}", exc_info=True)
            return Response(
                {"error": _("Authentication failed")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_user_location(self, user):
        """Get user's assigned location from Person model"""
        try:
            # Check if user has a person record with location
            if hasattr(user, 'person') and user.person:
                return user.person.location
        except AttributeError:
            logger.warning(f"User {user.username} doesn't have person record or location")
        
        return None
    
    def _get_all_child_locations(self, location):
        """Get all child locations (including the location itself and all descendants)"""
        locations = []
        
        def get_descendants(loc, depth=0):
            """Recursively get all descendants"""
            # Add current location
            locations.append(self._location_to_dict(loc, depth))
            
            # Get direct children - REMOVED is_active=True
            children = Location.objects.filter(parent=loc)
            
            for child in children:
                get_descendants(child, depth + 1)
        
        # Start with the user's location and all its descendants
        get_descendants(location, depth=0)
        return locations
    
    def _location_to_dict(self, location, depth=0):
        """Convert location object to dictionary"""
        location_data = {
            'id': location.id,
            'name': location.name,
            'code': getattr(location, 'code', ''),
            'type': getattr(location, 'type', None),
            'description': getattr(location, 'description', ''),
            'parent_id': location.parent_id,
            'depth': depth,
            # REMOVED: 'is_active': getattr(location, 'is_active', True),
        }
        
        # Add tags if available
        if hasattr(location, 'tags'):
            location_data['tags'] = [tag.name for tag in location.tags.all()]
        
        return location_data
    
    def _generate_session_token(self):
        """Generate a secure session token"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CompleteLoginAPIView(GenericAPIView):
    """Step 2: Location selection and login completion"""
    serializer_class = serializers.Serializer
    throttle_classes = [AuthenticationThrottle]
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Step 2: Complete login with location selection"""
        try:
            session_token = request.data.get('session_token')
            location_id = request.data.get('location_id')
            remember_me = request.data.get('remember_me', False)
            
            if not session_token or not location_id:
                return Response(
                    {"error": _("Session token and location ID are required")},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate session token
            session_data = cache.get(f"login_session:{session_token}")
            if not session_data:
                return Response(
                    {"error": _("Session expired or invalid. Please login again.")},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Get user
            try:
                user = User.objects.get(id=session_data['user_id'])
            except User.DoesNotExist:
                return Response(
                    {"error": _("User not found")},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Validate location - REMOVED is_active=True
            try:
                selected_location = Location.objects.get(id=location_id)
            except Location.DoesNotExist:
                return Response(
                    {"error": _("Invalid location selected")},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if location is within user's allowed locations
            user_location_id = session_data.get('user_location_id')
            if user_location_id:
                # Get all allowed location IDs (user's location + all descendants)
                allowed_location_ids = self._get_all_descendant_ids(user_location_id)
                
                if selected_location.id not in allowed_location_ids:
                    return Response(
                        {"error": _("You can only login at locations under your registered location.")},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Complete login
            login(request, user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Store login location in session
            request.session['login_location_id'] = selected_location.id
            request.session['login_location_name'] = selected_location.name
            
            # Set session expiry
            if remember_me:
                request.session.set_expiry(1209600)  # 2 weeks
            else:
                request.session.set_expiry(3600)  # 1 hour
            
            # Clear session token
            cache.delete(f"login_session:{session_token}")
            
            # Get user permissions and groups
            permissions = list(user.get_all_permissions())
            groups = list(user.groups.values_list('name', flat=True))
            
            logger.info(
                f"Successful login for user: {user.username} at location: "
                f"{selected_location.name} (ID: {selected_location.id})"
            )
            
            return Response({
                "success": _("Login successful"),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.get_full_name(),
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "groups": groups,
                    "permissions": permissions
                },
                "location": {
                    "id": selected_location.id,
                    "name": selected_location.name,
                    "code": getattr(selected_location, 'code', ''),
                    "type": getattr(selected_location, 'type', None),
                    "description": getattr(selected_location, 'description', ''),
                    "parent_id": selected_location.parent_id
                },
                "session_expiry": request.session.get_expiry_age(),
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Login step 2 error: {e}", exc_info=True)
            return Response(
                {"error": _("Login completion failed")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_all_descendant_ids(self, location_id):
        """Get all descendant location IDs including the location itself"""
        ids = [location_id]
        
        def get_descendants(parent_id):
            children = Location.objects.filter(parent_id=parent_id)  # REMOVED is_active=True
            for child in children:
                ids.append(child.id)
                get_descendants(child.id)
        
        get_descendants(location_id)
        return ids


class LogoutAPIView(GenericAPIView):
    """Enhanced Logout API"""
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            user_info = f"{request.user.username} ({request.user.id})"
            logout(request)
            
            logger.info(f"User logged out: {user_info}")
            
            return Response({
                "success": _("Logged out successfully"),
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Logout error: {e}", exc_info=True)
            return Response(
                {"error": _("Logout failed")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CurrentUserAPIView(GenericAPIView):
    """Enhanced Current User API with comprehensive data"""
    serializer_class = UserWithPermissionsSerializer
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            serializer = self.serializer_class(user, context={'request': request})
            
            # Get current login location from session
            current_location = None
            login_location_id = request.session.get('login_location_id')
            if login_location_id:
                try:
                    location = Location.objects.get(id=login_location_id)
                    current_location = {
                        'id': location.id,
                        'name': location.name,
                        'code': getattr(location, 'code', ''),
                        'type': getattr(location, 'type', None),
                    }
                except Location.DoesNotExist:
                    pass
            
            return Response({
                "user": serializer.data,
                "current_location": current_location,
                "permissions": list(user.get_all_permissions()),
                "timestamp": timezone.now().isoformat()
            })
            
        except User.DoesNotExist:
            return Response(
                {"error": _("User not found")}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Current user error: {e}", exc_info=True)
            return Response(
                {"error": _("Failed to retrieve user data")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChangePasswordAPIView(GenericAPIView):
    """Enhanced Change Password API with security features"""
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserActionThrottle]
    
    @transaction.atomic
    def post(self, request):
        try:
            user = request.user
            serializer = self.serializer_class(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            
            data = serializer.validated_data
            new_password = data['new_password']
            
            # Update password
            user.set_password(new_password)
            user.save(update_fields=['password'])
            
            logger.info(f"Password changed for user: {user.username}")
            return Response({
                "success": _("Password changed successfully"),
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Password change error: {e}", exc_info=True)
            return Response(
                {"error": _("Password change failed")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserAvailableLocationsAPIView(GenericAPIView):
    """Get all available locations for the authenticated user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            user_location = self._get_user_location(user)
            
            if not user_location:
                return Response(
                    {"error": _("User location not configured")},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get all child locations
            available_locations = self._get_all_child_locations(user_location)
            
            return Response({
                "primary_location": {
                    "id": user_location.id,
                    "name": user_location.name,
                    "code": getattr(user_location, 'code', ''),
                },
                "available_locations": available_locations,
                "count": len(available_locations)
            })
            
        except Exception as e:
            logger.error(f"Failed to get user locations: {e}", exc_info=True)
            return Response(
                {"error": _("Failed to retrieve available locations")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_user_location(self, user):
        """Get user's assigned location"""
        try:
            if hasattr(user, 'person') and user.person:
                return user.person.location
        except:
            pass
        return None
    
    def _get_all_child_locations(self, location):
        """Get all child locations"""
        locations = []
        
        def get_descendants(loc, depth=0):
            locations.append({
                'id': loc.id,
                'name': loc.name,
                'code': getattr(loc, 'code', ''),
                'depth': depth
            })
            
            children = Location.objects.filter(parent=loc)  # REMOVED is_active=True
            for child in children:
                get_descendants(child, depth + 1)
        
        get_descendants(location)
        return locations


# =============================================================================
# TOKEN AUTHENTICATION ENDPOINTS (NEW ADDITIONS - ADD THESE AT THE END)
# =============================================================================

class TokenLoginAPIView(GenericAPIView):
    """
    Token-based login for API access (for interoperability and API testing).
    Returns an authentication token that can be used in Authorization header.
    """
    serializer_class = AuthTokenSerializer
    throttle_classes = [AuthenticationThrottle]
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        """
        Authenticate user and return token.
        Usage:
        POST /api/auth/token/login/
        {
            "username": "username",
            "password": "password"
        }
        """
        try:
            serializer = self.serializer_class(data=request.data,
                                             context={'request': request})
            serializer.is_valid(raise_exception=True)
            
            user = serializer.validated_data['user']
            
            # Check if user is active
            if not user.is_active:
                return Response(
                    {'error': _('User account is disabled.')},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Get or create token for the user
            token, created = Token.objects.get_or_create(user=user)
            
            # Get user's default institution/location for API context
            default_institution = self._get_user_default_institution(user)
            
            logger.info(f"Token {'created' if created else 'retrieved'} for user: {user.username}")
            
            return Response({
                'token': token.key,
                'user': {
                    'id': user.pk,
                    'username': user.username,
                    'email': user.email,
                    'full_name': user.get_full_name(),
                    'is_active': user.is_active,
                    'is_staff': user.is_staff,
                    'is_superuser': user.is_superuser,
                },
                'default_institution': default_institution,
                'created': created,
                'message': _('Token created successfully.') if created else _('Using existing token.'),
                'instructions': _('Use this token in Authorization header: Token {token_key}').format(token_key=token.key),
                'expires': None,  # Tokens don't expire unless explicitly deleted
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Token login error: {e}", exc_info=True)
            return Response(
                {'error': _('Authentication failed.')},
                status=status.HTTP_401_UNAUTHORIZED
            )
    
    def _get_user_default_institution(self, user):
        """Get user's default institution/location for API context"""
        try:
            if hasattr(user, 'person') and user.person:
                location = user.person.location
                if location:
                    return {
                        'id': location.id,
                        'name': location.name,
                        'code': getattr(location, 'code', ''),
                        'type': getattr(location, 'type', None),
                    }
        except:
            pass
        return None


class TokenLogoutAPIView(GenericAPIView):
    """
    Logout and delete token.
    Requires token authentication.
    """
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Delete the authentication token.
        Usage:
        POST /api/auth/token/logout/
        Header: Authorization: Token <token_key>
        """
        try:
            user = request.user
            
            # Delete the token
            try:
                # Check if token authentication is being used
                if hasattr(request, 'auth') and request.auth is not None:
                    request.auth.delete()  # Delete the token instance
                    message = _('Token deleted successfully.')
                else:
                    # If using session auth, just log the action
                    message = _('Logged out (session authentication).')
            except Exception as e:
                logger.error(f"Error deleting token: {e}")
                message = _('Token deletion failed.')
            
            logger.info(f"Token logout for user: {user.username}")
            
            return Response({
                'success': True,
                'message': message,
                'user': user.username,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Token logout error: {e}", exc_info=True)
            return Response(
                {'error': _('Logout failed.')},
                status=status.HTTP_400_BAD_REQUEST
            )


class VerifyTokenAPIView(GenericAPIView):
    """
    Verify if a token is valid and get user information.
    """
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Verify token and return user information.
        Usage:
        GET /api/auth/token/verify/
        Header: Authorization: Token <token_key>
        """
        try:
            user = request.user
            
            # Check if token is being used
            is_token_auth = hasattr(request, 'auth') and request.auth is not None
            
            return Response({
                'valid': True,
                'authentication_method': 'token' if is_token_auth else 'session',
                'user': {
                    'id': user.pk,
                    'username': user.username,
                    'email': user.email,
                    'full_name': user.get_full_name(),
                    'is_active': user.is_active,
                    'is_staff': user.is_staff,
                    'is_superuser': user.is_superuser,
                },
                'token_info': {
                    'key': request.auth.key if is_token_auth else None,
                    'created': request.auth.created if is_token_auth else None,
                } if is_token_auth else None,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Token verification error: {e}", exc_info=True)
            return Response(
                {'error': _('Token verification failed.')},
                status=status.HTTP_401_UNAUTHORIZED
            )


class RotateTokenAPIView(GenericAPIView):
    """
    Rotate/refresh authentication token (create new, delete old).
    """
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Create a new token and delete the old one.
        Usage:
        POST /api/auth/token/rotate/
        Header: Authorization: Token <old_token_key>
        """
        try:
            user = request.user
            
            # Delete old token if exists
            try:
                if hasattr(request, 'auth') and request.auth is not None:
                    old_token = request.auth
                    old_key = old_token.key
                    old_token.delete()
                else:
                    old_key = None
            except (AttributeError, Token.DoesNotExist):
                old_key = None
            
            # Create new token
            new_token = Token.objects.create(user=user)
            
            logger.info(f"Token rotated for user: {user.username}")
            
            return Response({
                'success': True,
                'message': _('Token rotated successfully.'),
                'old_token': old_key,
                'new_token': new_token.key,
                'user': user.username,
                'created': new_token.created.isoformat(),
                'instructions': _('Use the new token in Authorization header: Token {token_key}').format(
                    token_key=new_token.key
                ),
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Token rotation error: {e}", exc_info=True)
            return Response(
                {'error': _('Token rotation failed.')},
                status=status.HTTP_400_BAD_REQUEST
            )


class ListUserTokensAPIView(GenericAPIView):
    """
    List all tokens for the current user (admin/superuser can list all).
    """
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        List tokens for the user.
        Superusers can see all tokens.
        """
        try:
            user = request.user
            
            if user.is_superuser:
                # Superuser can see all tokens
                tokens = Token.objects.all().select_related('user')
                tokens_data = [
                    {
                        'id': token.id,
                        'key': token.key[:8] + '...' + token.key[-8:] if len(token.key) > 20 else token.key,
                        'user': {
                            'id': token.user.id,
                            'username': token.user.username,
                        },
                        'created': token.created.isoformat(),
                        'last_used': getattr(token, 'last_used', None),
                    }
                    for token in tokens
                ]
                total_tokens = tokens.count()
            else:
                # Regular users can only see their own tokens
                token = Token.objects.filter(user=user).first()
                if token:
                    tokens_data = [{
                        'id': token.id,
                        'key': token.key[:8] + '...' + token.key[-8:] if len(token.key) > 20 else token.key,
                        'created': token.created.isoformat(),
                        'last_used': getattr(token, 'last_used', None),
                    }]
                    total_tokens = 1
                else:
                    tokens_data = []
                    total_tokens = 0
            
            return Response({
                'tokens': tokens_data,
                'total': total_tokens,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'is_superuser': user.is_superuser,
                },
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"List tokens error: {e}", exc_info=True)
            return Response(
                {'error': _('Failed to list tokens.')},
                status=status.HTTP_400_BAD_REQUEST
            )