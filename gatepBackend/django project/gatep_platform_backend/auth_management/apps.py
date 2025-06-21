# File: gatep_platform_backend/auth_management/apps.py

from django.apps import AppConfig


class AuthManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auth_management' # ENSURE THIS MATCHES YOUR APP FOLDER NAME EXACTLY
