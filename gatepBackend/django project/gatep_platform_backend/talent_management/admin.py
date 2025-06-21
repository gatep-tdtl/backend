# File: gatep_platform_backend/talent_management/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
# CHANGED: Import renamed profile models, removed EmployeeProfile
from .models import CustomUser, TalentProfile, EmployerProfile

class CustomUserAdmin(UserAdmin):
    # CHANGED: Update list_display and fieldsets for new boolean role names
    list_display = UserAdmin.list_display + ('user_role', 'is_talent_role', 'is_employer_role', 'phone_number',)
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('user_role', 'phone_number',)}),
    )
    list_filter = UserAdmin.list_filter + ('user_role',)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(TalentProfile)   # Renamed
admin.site.register(EmployerProfile) # Renamed
