# apps/person/models/__init__.py
from .person import Person, PersonName
from .user import User
from .patient import Patient

__all__ = [
    'Person',
    'PersonName', 
    'User',
    'Patient',
]