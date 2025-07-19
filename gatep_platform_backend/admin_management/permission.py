from rest_framework.permissions import BasePermission

class IsRoleAdmin(BasePermission):
    def has_permission(self, request, view):
        # THIS IS THE FIX: Changed 'role' to 'user_role'
        return request.user.is_authenticated and request.user.user_role == 'ADMIN'













# from rest_framework.permissions import BasePermission

# class IsRoleAdmin(BasePermission):
#     def has_permission(self, request, view):
#         return request.user.is_authenticated and request.user.role == 'admin'
