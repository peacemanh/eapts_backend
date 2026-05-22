# apps/data_element/management/commands/setup_dhis2.py
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.data_element.models import (
    DataElement, 
    DataType, 
    MappingSource, 
    DataElementClass,
    DataElementSourceMapping,
    DataElementValueSet
)
import uuid


class Command(BaseCommand):
    help = 'Setup initial DHIS2 configuration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up DHIS2 configuration...'))
        
        # Create required models if they don't exist
        datatype, _ = DataType.objects.get_or_create(
            id=1,
            defaults={
                'name': 'String',
                'description': 'Text string data type'
            }
        )
        
        mapping_source, _ = MappingSource.objects.get_or_create(
            id=2,
            defaults={
                'name': 'DHIS2',
                'description': 'District Health Information System 2',
                'url': 'https://dhisanalytics.moh.gov.et'
            }
        )
        
        data_element_class, _ = DataElementClass.objects.get_or_create(
            id=1,
            defaults={
                'name': 'DHIS2 Imported',
                'description': 'Data elements imported from DHIS2',
                'status': 'active'
            }
        )
        
        # Create parent data element for DHIS2 data elements
        parent_data_element, _ = DataElement.objects.get_or_create(
            id=167,
            defaults={
                'name': 'DHIS2 Data Elements',
                'label': 'DHIS2 Data Elements',
                'class_id': data_element_class,
                'datatype_id': datatype,
                'description': 'Parent element for all DHIS2 data elements',
                'status': 'active'
            }
        )
        
        # Create parent data element for DHIS2 indicators
        parent_indicator, _ = DataElement.objects.get_or_create(
            id=168,
            defaults={
                'name': 'DHIS2 Indicators',
                'label': 'DHIS2 Indicators',
                'class_id': data_element_class,
                'datatype_id': datatype,
                'description': 'Parent element for all DHIS2 indicators',
                'status': 'active'
            }
        )
        
        self.stdout.write(self.style.SUCCESS('✓ DHIS2 configuration setup completed'))
        self.stdout.write(self.style.SUCCESS(f'✓ Parent Data Element ID: {parent_data_element.id}'))
        self.stdout.write(self.style.SUCCESS(f'✓ Parent Indicator ID: {parent_indicator.id}'))
        
        # Update settings or create a config file
        self.stdout.write(self.style.SUCCESS('\nPlease add these to your .env file:'))
        self.stdout.write(self.style.SUCCESS('DHIS2_BASE_URL=https://dhisanalytics.moh.gov.et/api/40'))
        self.stdout.write(self.style.SUCCESS('DHIS2_USERNAME=admin'))
        self.stdout.write(self.style.SUCCESS('DHIS2_PASSWORD=district'))
        self.stdout.write(self.style.SUCCESS(f'DHIS2_DEFAULT_DATATYPE={datatype.id}'))
        self.stdout.write(self.style.SUCCESS(f'DHIS2_MAPPING_SOURCE={mapping_source.id}'))
        self.stdout.write(self.style.SUCCESS(f'DHIS2_DATA_ELEMENT_CLASS={data_element_class.id}'))
        self.stdout.write(self.style.SUCCESS(f'DHIS2_PARENT_DATA_ELEMENT={parent_data_element.id}'))
        self.stdout.write(self.style.SUCCESS(f'DHIS2_PARENT_INDICATOR={parent_indicator.id}'))