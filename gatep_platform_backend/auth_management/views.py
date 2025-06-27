# File: gatep_platform_backend/auth_management/views.py

from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenBlacklistView
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from talent_management.models import CustomUser, UserRole
from auth_management.permissions import IsAdminUser
from .serializers import (
    RegisterSerializer, LoginSerializer, OTPVerificationSerializer,
    CustomUserAdminSerializer, UserRoleUpdateSerializer, UserUpdateSerializer
)
from auth_management import serializers

# Register View
class RegisterView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        response_data = {
            "message": "User registered. Please check your email for OTP verification.",
            "username": serializer.data['username'],
            "email": serializer.data['email'],
            "phone_number": serializer.data.get('phone_number'),
            "user_role": serializer.data.get('user_role')
        }
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

# Login View
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        jwt_token_serializer = TokenObtainPairSerializer(data={
            'username': user.username,
            'password': request.data.get('password')
        })
        jwt_token_serializer.is_valid(raise_exception=True)
        response_data = {
            "message": "Login successful",
            "username": user.username,
            "email": user.email,
            "phone_number": user.phone_number,
            "user_role": user.user_role,
            "access": jwt_token_serializer.validated_data["access"],
            "refresh": jwt_token_serializer.validated_data["refresh"],
        }
        # Add company info if user is employer
        if user.user_role == UserRole.EMPLOYER:
            from employer_management.models import Company
            company = Company.objects.filter(user=user).first()
            if company:
                response_data["company"] = company.id
            else:
                response_data["company"] = "register your company"
        return Response(response_data, status=status.HTTP_200_OK)

# OTP Verification View
class OTPVerificationView(generics.GenericAPIView):
    serializer_class = OTPVerificationSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        user.is_active = True
        user.save()
        user.otp = None
        user.otp_created_at = None
        user.save()
        return Response({'message': 'Account verified successfully!'}, status=status.HTTP_200_OK)

@api_view(['POST'])
def resend_otp(request):
    username = request.data.get('username')
    if not username:
        return Response({'message': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = CustomUser.objects.get(username=username)
    except CustomUser.DoesNotExist:
        return Response({'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
    if user.is_active:
        return Response({'message': 'Account is already verified.'}, status=status.HTTP_200_OK)
    otp = user.generate_otp()
    subject = 'Your New OTP for Registration'
    message = f'Hi {user.username},\n\nYour new One-Time Password (OTP) for registration is: {otp}\n\nThis OTP is valid for 5 minutes.'
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]
    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
    except Exception as e:
        print(f"Error sending email to {user.email}: {e}")
        return Response({"message": "Failed to send new OTP email. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({'message': 'New OTP sent successfully. Check your email.'}, status=status.HTTP_200_OK)

# Logout View
class CustomLogoutView(TokenBlacklistView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK or response.status_code == status.HTTP_205_RESET_CONTENT:
            return Response({"message": "Token destroyed, logged out successfully!"}, status=status.HTTP_200_OK)
        return response

# Admin: List/Create Users
class CustomUserListCreateAdminView(generics.ListCreateAPIView):
    queryset = CustomUser.objects.all().order_by('username')
    serializer_class = CustomUserAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    def perform_create(self, serializer):
        user = serializer.save()
        # Optionally send OTP for newly created users by admin, or mark them active directly
        # If admin is creating, perhaps they want to activate immediately.
        # This current setup will send an OTP and set is_active=False by default in serializer create.
        # If you want admin-created users to be active immediately without OTP:
        # user.is_active = True
        # user.save()

# Admin: Retrieve/Update/Delete User
class CustomUserRetrieveUpdateDestroyAdminView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint for Admin users to retrieve, update, or delete a specific CustomUser.
    Requires ADMIN role.
    """
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    lookup_field = 'pk'
    def perform_destroy(self, instance):
        # Prevent deleting the last admin
        if instance.user_role == UserRole.ADMIN and CustomUser.objects.filter(user_role=UserRole.ADMIN).count() == 1:
            raise serializers.ValidationError({"detail": "Cannot delete the last admin user."})
        instance.delete()

# Admin: Update User Role/Active Status
class CustomUserRoleUpdateAdminView(generics.UpdateAPIView):
    """
    API endpoint for Admin users to update a specific CustomUser's role and active status.
    Uses a more specific serializer for focused updates.
    Requires ADMIN role.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserRoleUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    lookup_field = 'pk'
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)

# User: Update Own Profile
class UserUpdateView(generics.UpdateAPIView):
    serializer_class = UserUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user

# Forgot Password View
class ForgotPasswordView(APIView):
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'email': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return Response({'email': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        reset_link = f"http://localhost:8000/api/reset-password/{uid}/{token}/"
        send_mail(
            'Password Reset Request',
            f'Click the link to reset your password: {reset_link}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return Response({'message': 'Password reset link sent to your email.'}, status=status.HTTP_200_OK)

# Password Reset Confirm View
class PasswordResetConfirmView(APIView):
    def post(self, request, uidb64, token):
        password = request.data.get('password')
        if not password:
            return Response({'password': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            return Response({'error': 'Invalid link.'}, status=status.HTTP_400_BAD_REQUEST)
        if not default_token_generator.check_token(user, token):
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save()
        return Response({'message': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)






