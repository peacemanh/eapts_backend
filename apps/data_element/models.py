# apps/data_element/models.py
from django.db import models
import uuid


class DataElementClass(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['status']),
        ]


class DataType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['name']),
        ]


class MappingSource(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['name']),
        ]


class DataElement(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=255)
    class_id = models.ForeignKey(DataElementClass, on_delete=models.CASCADE, related_name='data_elements')
    datatype_id = models.ForeignKey(DataType, on_delete=models.CASCADE, related_name='data_elements')
    unit = models.CharField(max_length=50, blank=True, null=True)
    length = models.IntegerField(blank=True, null=True)
    default_value = models.CharField(max_length=255, blank=True, null=True)
    required = models.BooleanField(default=False)
    multi_value = models.BooleanField(default=False)
    normal_min_value = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    normal_max_value = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['status']),
            models.Index(fields=['class_id']),
            models.Index(fields=['datatype_id']),
            models.Index(fields=['created_date']),
            models.Index(fields=['name', 'status']),
        ]


class DataElementSourceMapping(models.Model):
    """
    Maps DataElements to MappingSources with additional metadata.
    A DataElement can have multiple source mappings.
    """
    dataelement = models.ForeignKey(DataElement, on_delete=models.CASCADE, related_name='source_mappings')
    source = models.ForeignKey(MappingSource, on_delete=models.CASCADE, related_name='element_mappings')
    code = models.CharField(max_length=255, blank=True, null=True, help_text="Source-specific code/identifier")
    description = models.TextField(blank=True, null=True, help_text="Additional description from the source")
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('dataelement', 'source', 'code')
        verbose_name = "Data Element Source Mapping"
        verbose_name_plural = "Data Element Source Mappings"
        ordering = ['source__name', 'code']
        indexes = [
            models.Index(fields=['dataelement', 'source']),
            models.Index(fields=['code']),
            models.Index(fields=['dataelement']),
            models.Index(fields=['source']),
        ]

    def __str__(self):
        return f"{self.dataelement.name} -> {self.source.name} ({self.code or 'No Code'})"


class DataElementValueSet(models.Model):
    """
    Relationship: a parent DataElement may have many answer elements (answer_element).
    sort_weight describes ordering of answer_element within the context of parent_element.
    """
    parent_element = models.ForeignKey(DataElement, on_delete=models.CASCADE, related_name='value_set_parents')
    answer_element = models.ForeignKey(DataElement, on_delete=models.CASCADE, related_name='value_set_answers')
    sort_weight = models.IntegerField(default=0)

    class Meta:
        unique_together = ('parent_element', 'answer_element')
        ordering = ['sort_weight', 'id']
        indexes = [
            models.Index(fields=['parent_element']),
            models.Index(fields=['answer_element']),
            models.Index(fields=['parent_element', 'sort_weight']),
        ]

    def __str__(self):
        return f"{self.parent_element.name} -> {self.answer_element.name}"


class DataElementSetMember(models.Model):
    """
    Relationship: a section (section_element) contains many member_element entries.
    sort_weight describes ordering of member_element inside the section (section_element).
    """
    section_element = models.ForeignKey(
        DataElement,
        on_delete=models.CASCADE,
        related_name='section_set_members'
    )
    member_element = models.ForeignKey(
        DataElement,
        on_delete=models.CASCADE,
        related_name='included_in_sections'
    )
    sort_weight = models.IntegerField(default=0)

    class Meta:
        unique_together = ('section_element', 'member_element')
        verbose_name = "Data Element Set Member"
        verbose_name_plural = "Data Element Set Members"
        ordering = ['sort_weight', 'id']
        indexes = [
            models.Index(fields=['section_element']),
            models.Index(fields=['member_element']),
            models.Index(fields=['section_element', 'sort_weight']),
        ]

    def __str__(self):
        return f"{self.section_element.name} → {self.member_element.name}"