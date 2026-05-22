from django.db import models
from .person import Person


class Patient(models.Model):
    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name='patient')
    medical_record_number = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.medical_record_number


class PatientAttributeType(models.Model):
    """
    Defines the type of additional information that can be associated with a patient.
    Example: Phone Number, Marital Status, Blood Type, Occupation, etc.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    datatype = models.CharField(
        max_length=50,
        choices=[
            ('text', 'Text'),
            ('number', 'Number'),
            ('date', 'Date'),
            ('boolean', 'Boolean'),
            ('select', 'Select'),
        ],
        default='text'
    )
    options = models.TextField(
        blank=True,
        null=True,
        help_text="Comma-separated values for 'select' datatype options (e.g. 'Single,Married,Divorced')."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PatientAttribute(models.Model):
    """
    Stores the actual value of a given attribute type for a patient.
    Example:
      type = 'Phone Number', value = '+251912345678'
      type = 'Marital Status', value = 'Married'
    """
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='attributes')
    attribute_type = models.ForeignKey(PatientAttributeType, on_delete=models.CASCADE, related_name='attributes')
    value = models.TextField(blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('patient', 'attribute_type')  # Prevent duplicate types per patient

    def __str__(self):
        return f"{self.patient.medical_record_number} - {self.attribute_type.name}: {self.value}"
