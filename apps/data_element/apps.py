from django.apps import AppConfig

class DataElementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.data_element'
    verbose_name = "Data Element Management"
