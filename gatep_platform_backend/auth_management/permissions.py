# File: gatep_platform_backend/auth_management/permissions.py

from rest_framework import permissions # <--- ADD THIS LINE
from talent_management.models import UserRole

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access.
    """
    def has_permission(self, request, view):
        # Check if the user is authenticated and has the ADMIN role
        return request.user and request.user.is_authenticated and request.user.user_role == UserRole.ADMIN

    def has_object_permission(self, request, view, obj):
        # For object-level permissions, ensure the request user is an ADMIN
        # and they are not trying to delete/deactivate themselves (optional, but good practice)
        if request.user and request.user.is_authenticated and request.user.user_role == UserRole.ADMIN:
            # Admins can manage other users. You might add a rule here to prevent an admin from deleting the last admin account or their own.
            return True
        return False