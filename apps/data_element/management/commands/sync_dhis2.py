# apps/data_element/management/commands/sync_dhis2.py
import requests
import base64
import os
import sys
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from decouple import config

# Add project root to path for direct config access
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from apps.data_element.models import (
    DataElement, 
    DataType, 
    MappingSource, 
    DataElementClass,
    DataElementSourceMapping,
    DataElementValueSet
)
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync data elements and indicators from DHIS2'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Don't load config here to avoid import issues

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['data-elements', 'indicators', 'both'],
            default='both',
            help='Type of resources to sync (data-elements, indicators, or both)'
        )
        parser.add_argument(
            '--page-size',
            type=int,
            default=100,
            help='Page size for DHIS2 API requests'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually saving'
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test connection only'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Show debug information'
        )

    def handle(self, *args, **options):
        # Try to load from settings first, fall back to direct config
        try:
            # Try Django settings
            self.dhis2_config = {
                'base_url': settings.DHIS2_BASE_URL,
                'username': settings.DHIS2_USERNAME,
                'password': settings.DHIS2_PASSWORD,
                'default_datatype': settings.DHIS2_DEFAULT_DATATYPE,
                'mapping_source': settings.DHIS2_MAPPING_SOURCE,
                'data_element_class': settings.DHIS2_DATA_ELEMENT_CLASS,
                'parent_data_element': settings.DHIS2_PARENT_DATA_ELEMENT,
                'parent_indicator': settings.DHIS2_PARENT_INDICATOR,
            }
            config_source = "Django settings"
        except AttributeError:
            # Fall back to direct config from .env
            from decouple import config as env_config
            
            # Load .env file from project root
            env_path = os.path.join(project_root, '.env')
            if os.path.exists(env_path):
                os.environ['ENV_PATH'] = env_path
            
            self.dhis2_config = {
                'base_url': env_config('DHIS2_BASE_URL', default='https://dhisanalytics.moh.gov.et/api/40'),
                'username': env_config('DHIS2_USERNAME', default='EthioDHIS'),
                'password': env_config('DHIS2_PASSWORD', default='EthioDHIS_pass'),
                'default_datatype': env_config('DHIS2_DEFAULT_DATATYPE', default=1, cast=int),
                'mapping_source': env_config('DHIS2_MAPPING_SOURCE', default=2, cast=int),
                'data_element_class': env_config('DHIS2_DATA_ELEMENT_CLASS', default=1, cast=int),
                'parent_data_element': env_config('DHIS2_PARENT_DATA_ELEMENT', default=167, cast=int),
                'parent_indicator': env_config('DHIS2_PARENT_INDICATOR', default=168, cast=int),
            }
            config_source = "Direct .env file"
        
        self.dry_run = options.get('dry_run', False)
        sync_type = options.get('type', 'both')
        test_mode = options.get('test', False)
        page_size = options.get('page_size', 100)
        debug_mode = options.get('debug', False)
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('DHIS2 Synchronization'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.stdout.write(f"Sync Type: {sync_type}")
        self.stdout.write(f"Page Size: {page_size}")
        self.stdout.write(f"Config Source: {config_source}")
        
        if debug_mode:
            self.stdout.write(f"\nDHIS2 Configuration:")
            self.stdout.write(f"  URL: {self.dhis2_config['base_url']}")
            self.stdout.write(f"  Username: {self.dhis2_config['username']}")
            self.stdout.write(f"  Password: {'*' * len(self.dhis2_config['password']) if self.dhis2_config['password'] else 'Not set'}")
            self.stdout.write(f"  Default Datatype: {self.dhis2_config['default_datatype']}")
            self.stdout.write(f"  Mapping Source: {self.dhis2_config['mapping_source']}")
            self.stdout.write(f"  Data Element Class: {self.dhis2_config['data_element_class']}")
            self.stdout.write(f"  Parent Data Element: {self.dhis2_config['parent_data_element']}")
            self.stdout.write(f"  Parent Indicator: {self.dhis2_config['parent_indicator']}")
        
        self.stdout.write('-' * 60)
        
        # Test connection
        if not self.test_connection():
            return
        
        if test_mode:
            self.stdout.write(self.style.SUCCESS("✅ Test completed successfully"))
            return
        
        # Verify models
        try:
            self.initialize_models()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Model initialization failed: {str(e)}"))
            if debug_mode:
                import traceback
                self.stdout.write(traceback.format_exc())
            return
        
        # Start sync
        if sync_type in ['data-elements', 'both']:
            self.sync_data_elements(page_size)
        
        if sync_type in ['indicators', 'both']:
            self.sync_indicators(page_size)
        
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('✅ Synchronization completed!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

    def test_connection(self):
        """Test DHIS2 connection"""
        self.stdout.write("Testing DHIS2 connection...")
        
        try:
            session = requests.Session()
            session.auth = (self.dhis2_config['username'], self.dhis2_config['password'])
            session.headers.update({'Content-Type': 'application/json'})
            
            # Test with a simple endpoint
            response = session.get(
                f"{self.dhis2_config['base_url']}/system/info",
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.stdout.write(self.style.SUCCESS(f"✅ Connection successful!"))
                self.stdout.write(f"  System: {data.get('systemName')}")
                self.stdout.write(f"  Version: {data.get('version')}")
                return True
            else:
                self.stdout.write(self.style.ERROR(
                    f"❌ Connection failed: HTTP {response.status_code}"
                ))
                self.stdout.write(f"  Response: {response.text[:200]}")
                return False
                
        except requests.exceptions.ConnectionError:
            self.stdout.write(self.style.ERROR("❌ Cannot connect to DHIS2. Check network/URL."))
            return False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Connection error: {str(e)}"))
            return False

    def initialize_models(self):
        """Initialize and verify required models"""
        self.stdout.write("\nInitializing models...")
        
        self.default_datatype = DataType.objects.get(id=self.dhis2_config['default_datatype'])
        self.mapping_source = MappingSource.objects.get(id=self.dhis2_config['mapping_source'])
        self.data_element_class = DataElementClass.objects.get(id=self.dhis2_config['data_element_class'])
        self.parent_data_element = DataElement.objects.get(id=self.dhis2_config['parent_data_element'])
        self.parent_indicator = DataElement.objects.get(id=self.dhis2_config['parent_indicator'])
        
        self.stdout.write(self.style.SUCCESS("✅ All models verified"))
        self.stdout.write(f"  Data Type: {self.default_datatype.name}")
        self.stdout.write(f"  Mapping Source: {self.mapping_source.name}")
        self.stdout.write(f"  Data Element Class: {self.data_element_class.name}")
        self.stdout.write(f"  Parent Data Element: {self.parent_data_element.name} (ID: {self.parent_data_element.id})")
        self.stdout.write(f"  Parent Indicator: {self.parent_indicator.name} (ID: {self.parent_indicator.id})")

    def get_dhis2_session(self):
        """Create authenticated session for DHIS2 API"""
        session = requests.Session()
        session.auth = (self.dhis2_config['username'], self.dhis2_config['password'])
        session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        return session

    def fetch_all_items(self, endpoint, page_size=100):
        """Fetch all items from DHIS2 with pagination"""
        session = self.get_dhis2_session()
        url = f"{self.dhis2_config['base_url']}/{endpoint}"
        
        all_items = []
        page = 1
        
        self.stdout.write(f"\nFetching {endpoint}...")
        
        while True:
            params = {
                'fields': 'id,name,shortName',
                'pageSize': page_size,
                'page': page
            }
            
            try:
                self.stdout.write(f"  Page {page}...")
                response = session.get(url, params=params, timeout=60)
                response.raise_for_status()
                data = response.json()
                
                # Get items based on endpoint
                if endpoint == 'dataElements':
                    items = data.get('dataElements', [])
                else:  # indicators
                    items = data.get('indicators', [])
                
                if not items:
                    break
                
                all_items.extend(items)
                self.stdout.write(f"    Retrieved {len(items)} items (Total: {len(all_items)})")
                
                # Check pager
                pager = data.get('pager', {})
                if not pager:
                    break
                
                current_page = int(pager.get('page', 1))
                page_count = int(pager.get('pageCount', 1))
                
                if current_page >= page_count:
                    break
                
                page += 1
                
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"❌ Error fetching page {page}: {str(e)}"))
                raise
        
        self.stdout.write(self.style.SUCCESS(f"✅ Total {len(all_items)} {endpoint} fetched"))
        return all_items

    def sync_data_elements(self, page_size):
        """Sync data elements from DHIS2"""
        self.stdout.write("\n" + "=" * 40)
        self.stdout.write("SYNCING DATA ELEMENTS")
        self.stdout.write("=" * 40)
        
        try:
            items = self.fetch_all_items('dataElements', page_size)
            stats = self.process_items(items, self.parent_data_element, 'data_element')
            
            self.stdout.write("\n📊 Data Elements Sync Summary:")
            self.stdout.write(f"  Total fetched: {stats['total']}")
            self.stdout.write(f"  Created: {stats['created']}")
            self.stdout.write(f"  Updated: {stats['updated']}")
            self.stdout.write(f"  Skipped: {stats['skipped']}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error syncing data elements: {str(e)}"))
            logger.error(f"Error syncing data elements: {str(e)}", exc_info=True)

    def sync_indicators(self, page_size):
        """Sync indicators from DHIS2"""
        self.stdout.write("\n" + "=" * 40)
        self.stdout.write("SYNCING INDICATORS")
        self.stdout.write("=" * 40)
        
        try:
            items = self.fetch_all_items('indicators', page_size)
            stats = self.process_items(items, self.parent_indicator, 'indicator')
            
            self.stdout.write("\n📊 Indicators Sync Summary:")
            self.stdout.write(f"  Total fetched: {stats['total']}")
            self.stdout.write(f"  Created: {stats['created']}")
            self.stdout.write(f"  Updated: {stats['updated']}")
            self.stdout.write(f"  Skipped: {stats['skipped']}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error syncing indicators: {str(e)}"))
            logger.error(f"Error syncing indicators: {str(e)}", exc_info=True)

    def process_items(self, items, parent_element, item_type):
        """Process a list of DHIS2 items"""
        stats = {
            'total': len(items),
            'created': 0,
            'updated': 0,
            'skipped': 0
        }
        
        # Process in batches
        batch_size = 50
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(items) - 1) // batch_size + 1
            
            self.stdout.write(f"\nProcessing batch {batch_num}/{total_batches} "
                           f"(items {i+1}-{min(i+batch_size, len(items))})")
            
            for item in batch:
                result = self.process_single_item(item, parent_element, item_type)
                stats[result] += 1
            
            # Show progress
            processed = stats['created'] + stats['updated'] + stats['skipped']
            self.stdout.write(f"  Progress: {processed}/{stats['total']} "
                           f"({processed/stats['total']*100:.1f}%)")
        
        return stats

    def process_single_item(self, item, parent_element, item_type):
        """Process a single DHIS2 item"""
        dhis2_id = item.get('id', '').strip()
        name = item.get('name', '').strip()
        short_name = item.get('shortName', '').strip()
        
        if not name or not dhis2_id:
            return 'skipped'
        
        # Use shortName as label, fallback to name
        label = short_name if short_name else name
        
        # Truncate if needed
        if len(label) > 255:
            label = label[:252] + '...'
        if len(name) > 255:
            name = name[:252] + '...'
        
        # Check if exists via source mapping
        existing_mapping = DataElementSourceMapping.objects.filter(
            source=self.mapping_source,
            code=dhis2_id
        ).first()
        
        if self.dry_run:
            if existing_mapping:
                self.stdout.write(f"  📝 Would update: {name[:60]}")
                return 'updated'
            else:
                self.stdout.write(f"  ➕ Would create: {name[:60]}")
                return 'created'
        
        # Live processing
        if existing_mapping:
            # Update existing
            data_element = existing_mapping.dataelement
            data_element.name = name
            data_element.label = label
            data_element.description = f"Synced from DHIS2 {item_type}: {dhis2_id}"
            data_element.status = 'active'
            data_element.save()
            
            existing_mapping.description = f"DHIS2 {item_type} - {name}"
            existing_mapping.save()
            
            self.stdout.write(f"  🔄 Updated: {name[:60]}")
            return 'updated'
        else:
            # Create new
            try:
                with transaction.atomic():
                    # Create DataElement
                    data_element = DataElement.objects.create(
                        name=name,
                        label=label,
                        class_id=self.data_element_class,
                        datatype_id=self.default_datatype,
                        description=f"Synced from DHIS2 {item_type}: {dhis2_id}",
                        status='active'
                    )
                    
                    # Create source mapping
                    DataElementSourceMapping.objects.create(
                        dataelement=data_element,
                        source=self.mapping_source,
                        code=dhis2_id,
                        description=f"DHIS2 {item_type} - {name}"
                    )
                    
                    # Add to parent's value set
                    DataElementValueSet.objects.create(
                        parent_element=parent_element,
                        answer_element=data_element,
                        sort_weight=0
                    )
                
                self.stdout.write(f"  ✅ Created: {name[:60]}")
                return 'created'
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Failed: {name[:60]} - {str(e)[:100]}"))
                return 'skipped'