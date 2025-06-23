# File: gatep_platform_backend/talent_management/apps.py

from django.apps import AppConfig


class TalentManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'talent_management' # ENSURE THIS MATCHES YOUR APP FOLDER NAME EXACTLY
