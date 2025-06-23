from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'role', 'status', 'location', 'join_date', 'last_login_date')
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role', 'status', 'location', 'performance')}),
    )