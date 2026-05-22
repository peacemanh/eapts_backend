from django.urls import path
from apps.person.views.patient_view import PatientListCreateView, PatientDetailView

urlpatterns = [
    path('', PatientListCreateView.as_view(), name='patient-list'),
    path('<int:pk>/', PatientDetailView.as_view(), name='patient-detail'),
]
