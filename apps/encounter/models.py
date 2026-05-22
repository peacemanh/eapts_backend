from django.db import models
import uuid

class Encounter(models.Model):
    uuid = models.UUIDField(
        default=uuid.uuid4, 
        editable=False, 
        unique=True,
        help_text="Unique identifier for the encounter"
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    # Add more fields here as needed in future
    # patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    # location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-date_created']
        verbose_name = "Encounter"
        verbose_name_plural = "Encounters"

    def __str__(self):
        return str(self.uuid)
