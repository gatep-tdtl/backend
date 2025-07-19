# File: gatep_platform_backend/auth_management/urls.py

from django.urls import path
from .views import (
    DeleteUserForTestingView, RegisterView, LoginView, OTPVerificationView, resend_otp, UserUpdateView,
    ForgotPasswordView, PasswordResetConfirmView,
    CustomUserListCreateAdminView, CustomUserRetrieveUpdateDestroyAdminView, CustomUserRoleUpdateAdminView
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Auth URLs
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('testing/delete-user/', DeleteUserForTestingView.as_view(), name='testing-delete-user'),
    path('verify-otp/', OTPVerificationView.as_view(), name='verify-otp'),
    path('resend-otp/', resend_otp, name='resend-otp'),
    path('update-profile/', UserUpdateView.as_view(), name='update-profile'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Admin User Management URLs
    path('admin/users/', CustomUserListCreateAdminView.as_view(), name='admin-user-list-create'),
    path('admin/users/<int:pk>/', CustomUserRetrieveUpdateDestroyAdminView.as_view(), name='admin-user-detail'),
    path('admin/users/<int:pk>/update-role/', CustomUserRoleUpdateAdminView.as_view(), name='admin-user-update-role'),

    # Password Reset URLs
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/<uidb64>/<token>/', PasswordResetConfirmView.as_view(), name='reset-password-confirm'),
]
