from django.urls import path
from apps.person.views.person_view import (
    PersonListCreateView, PersonDetailView,
    PersonNameListCreateView, PersonNameDetailView
)

urlpatterns = [
    # Person endpoints
    path('', PersonListCreateView.as_view(), name='person-list'),
    path('<int:pk>/', PersonDetailView.as_view(), name='person-detail'),

    # Person name endpoints
    path('names/', PersonNameListCreateView.as_view(), name='personname-list'),
    path('names/<int:pk>/', PersonNameDetailView.as_view(), name='personname-detail'),
]
