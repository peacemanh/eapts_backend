# apps/person/apps.py
from django.apps import AppConfig

class PersonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.person'
    verbose_name = 'Person Management'  # Make sure this is set