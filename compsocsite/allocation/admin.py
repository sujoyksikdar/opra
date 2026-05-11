from django.contrib import admin
from .models import AllocationVoter, AllocationCache

admin.site.register(AllocationVoter)
admin.site.register(AllocationCache)
