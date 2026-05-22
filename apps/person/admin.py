from django.contrib import admin
from .models.user import User
from .models.person import Person, PersonName

admin.site.register(User)
admin.site.register(Person)
admin.site.register(PersonName)
