# apps/person/models/person.py

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

class Person(models.Model):
    class Gender(models.TextChoices):
        MALE = 'M', _('Male')
        FEMALE = 'F', _('Female')
        OTHER = 'O', _('Other')
        PREFER_NOT_TO_SAY = 'U', _('Prefer not to say')
    
    gender = models.CharField(
        max_length=1,
        choices=Gender.choices,
        db_index=True
    )
    birthdate = models.DateField(null=True, blank=True, db_index=True)
    contact_info = models.TextField(blank=True)
    
    # Updated location relationship with correct app name
    location = models.ForeignKey(
        'locations.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='persons',
        db_index=True,
        help_text=_("Primary location associated with this person")
    )
    
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['gender', 'birthdate']),
            models.Index(fields=['location', 'created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(birthdate__lte=timezone.now().date()),
                name='birthdate_not_in_future'
            ),
        ]

    def clean(self):
        super().clean()
        if self.birthdate and self.birthdate > timezone.now().date():
            raise ValidationError({'birthdate': _('Birthdate cannot be in the future.')})

    def get_preferred_name(self):
        try:
            return self.names.get(preferred=True)
        except PersonName.DoesNotExist:
            return self.names.order_by('-created_at').first()

    def __str__(self):
        preferred_name = self.get_preferred_name()
        if preferred_name:
            return f"{preferred_name.given_name} {preferred_name.last_name}"
        return f"Person {self.id}"


class PersonName(models.Model):
    person = models.ForeignKey(
        Person, 
        on_delete=models.CASCADE, 
        related_name='names',
        db_index=True
    )
    given_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    preferred = models.BooleanField(default=False, db_index=True)
    
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'preferred'],
                condition=models.Q(preferred=True),
                name='unique_preferred_name_per_person'
            ),
        ]
        indexes = [
            models.Index(fields=['given_name', 'last_name']),
            models.Index(fields=['last_name', 'given_name']),
        ]

    def save(self, *args, **kwargs):
        if not self.pk and not self.person.names.filter(preferred=True).exists():
            self.preferred = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.given_name} {self.last_name}"