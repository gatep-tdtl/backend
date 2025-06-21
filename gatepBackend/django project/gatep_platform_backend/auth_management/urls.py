# File: gatep_platform_backend/auth_management/urls.py

from django.urls import path
from .views import (
    RegisterView, LoginView, OTPVerificationView,
    CustomUserListCreateAdminView, CustomUserRetrieveUpdateDestroyAdminView,#resend_otp,
    CustomUserRoleUpdateAdminView # Import new views
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Existing Auth URLs
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('verify-otp/', OTPVerificationView.as_view(), name='verify_otp'),
    # path('request-new-otp/', resend_otp.as_view(), name='request_new_otp'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Admin User Management URLs
    path('admin/users/', CustomUserListCreateAdminView.as_view(), name='admin-user-list-create'),
    path('admin/users/<int:pk>/', CustomUserRetrieveUpdateDestroyAdminView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:pk>/update-role/', CustomUserRoleUpdateAdminView.as_view(), name='admin-user-update-role'),
]