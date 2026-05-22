from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from django.utils import timezone

@require_GET
@ensure_csrf_cookie
def get_csrf_token(request):
    """
    Endpoint to get a new CSRF token.
    The @ensure_csrf_cookie decorator ensures the cookie is set.
    """
    token = get_token(request)
    return JsonResponse({
        'csrfToken': token,
        'detail': 'CSRF cookie set',
        'timestamp': timezone.now().isoformat()
    })

def csrf_failure(request, reason=""):
    """Custom CSRF failure view that returns JSON"""
    return JsonResponse({
        'error': 'CSRF Failed',
        'reason': reason,
        'detail': 'CSRF token missing or incorrect. Please refresh the page and try again.',
        'timestamp': timezone.now().isoformat()
    }, status=403)

@require_GET
def health_check(request):
    """Simple health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat()
    })