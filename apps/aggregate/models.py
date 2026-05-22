from django.db import models
import uuid
from apps.data_element.models import DataElement
from apps.locations.models import Location 
from apps.person.models.user import User

# apps/aggregate/models.py
class AggregateRecord(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    record_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Record identifier sent from the front-end; not unique."
    )

    data_element = models.ForeignKey(
        DataElement,
        on_delete=models.PROTECT,
        related_name='aggregate_records'
    )
    form = models.ForeignKey(
        DataElement,
        on_delete=models.PROTECT,
        related_name='aggregate_forms'
    )
    
    # group field - refers to DataElement id (section/group)
    group = models.ForeignKey(
        DataElement,
        on_delete=models.PROTECT,
        related_name='aggregate_groups',
        null=True,
        blank=True,
        help_text="Group/Section ID that this data belongs to"
    )

    institution = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='institution_aggregates',
        null=True,
        blank=True,
        help_text="Institution location where the data was collected"
    )
    
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='location_aggregates',
        null=True,
        blank=True,
        help_text="Specific location within institution"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_aggregates',
        null=True,
        blank=True,
        help_text="User who created this record"
    )
    
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='updated_aggregates',
        null=True,
        blank=True,
        help_text="User who last updated this record"
    )

    value_text = models.TextField(blank=True, null=True)
    value_numeric = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    value_coded = models.ForeignKey(
        DataElement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='aggregate_coded_answers'
    )
    value_datetime = models.DateTimeField(blank=True, null=True)

    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'aggregate_record'
        indexes = [
            models.Index(fields=['form', 'data_element'], name='idx_agg_form_de'),
            models.Index(fields=['group'], name='idx_agg_group'),
            models.Index(fields=['form', 'group'], name='idx_agg_form_group'),
            models.Index(fields=['value_coded'], name='idx_agg_value_coded'),
            models.Index(fields=['record_id'], name='idx_agg_record_id'),
            models.Index(fields=['institution'], name='idx_agg_institution'),
            models.Index(fields=['location'], name='idx_agg_location'),
            models.Index(fields=['created_by'], name='idx_agg_created_by'),
            models.Index(fields=['updated_by'], name='idx_agg_updated_by'),
        ]

    def __str__(self):
        group_info = f" - Group: {self.group.name}" if self.group else ""
        return f"{self.form.name}{group_info} - {self.data_element.name}"