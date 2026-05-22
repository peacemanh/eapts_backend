# apps/address/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AddressLevelViewSet, AddressEntryViewSet, AddressCSVUploadView

router = DefaultRouter()
router.register(r'address-levels', AddressLevelViewSet)
router.register(r'address-entries', AddressEntryViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('address-upload/', AddressCSVUploadView.as_view(), name='address-upload'),
]
