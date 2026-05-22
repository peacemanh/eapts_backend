# apps/person/models/user.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from .person import Person

class User(AbstractUser):
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
        SUSPENDED = 'suspended', _('Suspended')
        PENDING = 'pending', _('Pending')
    
    person = models.OneToOneField(
        Person, 
        on_delete=models.CASCADE, 
        related_name='user',
        verbose_name=_('Person'),
        null=True,
        blank=True
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name=_('Status')
    )
    
    # Explicitly define email field to avoid conflicts
    email = models.EmailField(
        _('email address'),
        blank=True,
        null=True,
        help_text=_('User email address')
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        indexes = [
            models.Index(fields=['username', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['last_login']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.username

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    def get_email(self):
        """Get email from person's contact info if available, fallback to user email"""
        if hasattr(self.person, 'email') and self.person.email:
            return self.person.email
        return self.email