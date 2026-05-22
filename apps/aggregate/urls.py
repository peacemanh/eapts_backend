# apps/aggregate/urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import AggregateRecordViewSet

router = DefaultRouter()
router.register(r'aggregate-records', AggregateRecordViewSet, basename='aggregate-record')

urlpatterns = [
    path('', include(router.urls)),
]
