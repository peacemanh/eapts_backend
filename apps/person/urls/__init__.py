from django.urls import path, include

urlpatterns = [
    path('person/', include('apps.person.urls.person_urls')),
    path('patient/', include('apps.person.urls.patient_urls')),
    path('user/', include('apps.person.urls.user_urls')),
    path('patient-attribute/', include('apps.person.urls.patient_attribute_urls')),  # ✅ new
]
