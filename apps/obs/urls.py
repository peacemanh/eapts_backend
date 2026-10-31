# apps/obs/urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import ObsViewSet

router = DefaultRouter()
router.register(r'obs', ObsViewSet, basename='obs')

urlpatterns = [
    path('', include(router.urls)),
]