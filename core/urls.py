from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from . import views

urlpatterns = [
    # Admin Panel
    path('admin/', admin.site.urls),

    # Health and CSRF endpoints
    path('health/', views.health_check, name='health-check'),
    path('api/user/auth/csrf/', views.get_csrf_token, name='csrf'),
    path('api/user/auth/health/', views.health_check, name='auth-health'),

    # API Routes
    path("api/locations/", include("apps.locations.urls")),
    path("api/person/", include("apps.person.urls.person_urls")),
    path("api/user/", include("apps.person.urls.user_urls")),
    path('api/data-element/', include('apps.data_element.urls')),
    path('api/', include('apps.aggregate.urls')),
    path("api/", include("apps.encounter.urls")),
    path('api/address/', include('apps.address.urls')),

    # OpenAPI Schema & Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Custom error handlers
handler403 = 'core.views.csrf_failure'