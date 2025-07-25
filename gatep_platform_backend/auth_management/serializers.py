
# --- START OF FILE serializers.py ---

from django.contrib.auth import authenticate
from requests import Response
from rest_framework import serializers
import re
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import status
from django.db import transaction  # Import transaction for atomic operations

# IMPORTANT: Import CustomUser and UserRole from talent_management.models
from talent_management.models import CustomUser, UserRole, TalentProfile, EmployerProfile


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    user_role = serializers.ChoiceField(
        choices=[
            (UserRole.ADMIN.value, UserRole.ADMIN.label),
            (UserRole.TALENT.value, UserRole.TALENT.label),
            (UserRole.EMPLOYER.value, UserRole.EMPLOYER.label)
        ],
        required=True
    )

    class Meta:
        model = CustomUser
        fields = (
            'username',
            'email',
            'phone_number',
            'password',
            'confirm_password',
            'user_role',
            'first_name',
            'last_name',
        )

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        if CustomUser.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError({"username": "A user with that username already exists."})

        if CustomUser.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError({"email": "A user with that email already exists."})

        # Check for phone number uniqueness only if it's provided and not blank
        if data.get('phone_number') and CustomUser.objects.filter(phone_number=data['phone_number']).exists():
            raise serializers.ValidationError({"phone_number": "A user with that phone number already exists."})

        return data

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'[0-9]', value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?`~]', value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        return value

    # FIX 1: Wrap the entire creation process in a transaction
    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user_role = validated_data.pop('user_role')

        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            phone_number=validated_data.get('phone_number'),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            user_role=user_role,
            is_active=False
        )

        if user_role == UserRole.TALENT:
            TalentProfile.objects.create(user=user)
        elif user_role == UserRole.EMPLOYER:
            EmployerProfile.objects.create(user=user)

        otp = user.generate_otp()

        subject = 'Your OTP for Registration Verification'
        message = f'Hi {user.username},\n\nYour One-Time Password (OTP) for registration is: {otp}\n\nThis OTP is valid for 5 minutes.'
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [user.email]
        try:
            send_mail(subject, message, from_email, recipient_list, fail_silently=False)
        except Exception as e:
            # Because of @transaction.atomic, we don't need to manually delete the user.
            # The transaction will be rolled back automatically if an exception is raised.
            print(f"Error sending OTP email to {user.email}: {e}")
            raise serializers.ValidationError(
                {'email': "Failed to send OTP email. Please ensure your email configuration is correct and try again."},
                code='email_send_failure'
            )

        return user


# FIX 2: Changed from 'phone_or_email' to 'username_or_email'
class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username_or_email = data.get('username_or_email')
        password = data.get('password')

        user = None
        if username_or_email and password:
            # First, try to authenticate with the input as a username
            user = authenticate(username=username_or_email, password=password)

            # If that fails and it's an email, try to find the user by email
            # and then authenticate with their actual username.
            if not user and '@' in username_or_email:
                try:
                    user_by_email = CustomUser.objects.get(email=username_or_email)
                    user = authenticate(username=user_by_email.username, password=password)
                except CustomUser.DoesNotExist:
                    pass # We will raise the 'Invalid credentials' error below

            # Final validation checks
            if not user:
                raise serializers.ValidationError('Invalid credentials.')
            
            if user.user_role not in [UserRole.TALENT.value, UserRole.EMPLOYER.value, UserRole.ADMIN.value]:
                raise serializers.ValidationError('User role is invalid or not recognized.')

            if not user.is_active:
                raise serializers.ValidationError('Account not verified. Please verify your email.')
        else:
            raise serializers.ValidationError('Must include "username_or_email" and "password".')

        data['user'] = user
        return data


class OTPVerificationSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    otp = serializers.CharField(required=True, max_length=6)

    def validate(self, data):
        username = data.get('username')
        otp_received = data.get('otp')

        try:
            user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({'username': 'Invalid username or user not found.'})

        if user.is_active:
            raise serializers.ValidationError({'message': 'Account already verified.'})

        if not user.otp or not user.otp_created_at:
            raise serializers.ValidationError({'otp': 'No OTP generated for this user. Please register again or request a new OTP.'})

        if not user.is_otp_valid():
            raise serializers.ValidationError({'otp': 'OTP has expired. Please request a new OTP.'})

        if user.otp != otp_received:
            raise serializers.ValidationError({'otp': 'Invalid OTP.'})

        data['user'] = user
        return data

class CustomUserAdminSerializer(serializers.ModelSerializer):
    """
    Serializer for Admin to view, create, and update CustomUser objects.
    Excludes sensitive fields like password for retrieval.
    Includes all relevant user details and role information.
    """
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    is_talent_role = serializers.BooleanField(read_only=True)
    is_employer_role = serializers.BooleanField(read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'id', 'username', 'email', 'phone_number', 'first_name', 'last_name',
            'user_role', 'is_talent_role', 'is_employer_role', 'is_staff',
            'is_active', 'date_joined', 'last_login', 'password', 'groups', 'user_permissions'
        )
        read_only_fields = ('date_joined', 'last_login', 'id', 'is_talent_role', 'is_employer_role')
        extra_kwargs = {
            'password': {'write_only': True, 'required': False} # Password is optional for updates
        }

    def validate_password(self, value):
        # Only validate password if it's provided (for updates or creation)
        if value:
            if len(value) < 8:
                raise serializers.ValidationError("Password must be at least 8 characters long.")
            if not re.search(r'[A-Z]', value):
                raise serializers.ValidationError("Password must contain at least one uppercase letter.")
            if not re.search(r'[a-z]', value):
                raise serializers.ValidationError("Password must contain at least one lowercase letter.")
            if not re.search(r'[0-9]', value):
                raise serializers.ValidationError("Password must contain at least one digit.")
            if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?`~]', value):
                raise serializers.ValidationError("Password must contain at least one special character.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user_role = validated_data.get('user_role', UserRole.TALENT.value) # Default to TALENT if not provided
        is_active = validated_data.get('is_active', True) # Default to active when Admin creates

        # Remove fields not part of the create_user method to avoid errors
        validated_data.pop('groups', None)
        validated_data.pop('user_permissions', None)

        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=password, # Use create_user for password hashing
            **validated_data # Pass remaining validated data
        )
        user.user_role = user_role # Set user role after creation
        user.is_active = is_active # Set active status
        user.save()

        # Create associated profiles based on role
        if user_role == UserRole.TALENT.value and not hasattr(user, 'talentprofile'):
            TalentProfile.objects.create(user=user)
        elif user_role == UserRole.EMPLOYER.value and not hasattr(user, 'employerprofile'):
            EmployerProfile.objects.create(user=user)

        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user_role = validated_data.get('user_role')
        
        # Update password if provided
        if password:
            instance.set_password(password)

        # Handle user role change and profile creation/deletion
        if user_role and user_role != instance.user_role:
            # Delete old profile if exists
            if instance.user_role == UserRole.TALENT.value and hasattr(instance, 'talentprofile'):
                instance.talentprofile.delete()
            elif instance.user_role == UserRole.EMPLOYER.value and hasattr(instance, 'employerprofile'):
                instance.employerprofile.delete()

            # Create new profile if needed
            if user_role == UserRole.TALENT.value and not hasattr(instance, 'talentprofile'):
                TalentProfile.objects.create(user=instance)
            elif user_role == UserRole.EMPLOYER.value and not hasattr(instance, 'employerprofile'):
                EmployerProfile.objects.create(user=instance)

        # Update other fields
        # Remove fields that shouldn't be mass-assigned
        validated_data.pop('groups', None)
        validated_data.pop('user_permissions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

class UserRoleUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer specifically for an admin to update a user's role and active status.
    """
    class Meta:
        model = CustomUser
        fields = ['user_role', 'is_active']

    def validate_user_role(self, value):
        if value not in [UserRole.ADMIN.value, UserRole.TALENT.value, UserRole.EMPLOYER.value]:
            raise serializers.ValidationError("Invalid user role.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        new_user_role = validated_data.get('user_role', instance.user_role)
        instance.is_active = validated_data.get('is_active', instance.is_active)

        if new_user_role != instance.user_role:
            # Delete old profile if exists
            if instance.user_role == UserRole.TALENT.value and hasattr(instance, 'talentprofile'):
                instance.talentprofile.delete()
            elif instance.user_role == UserRole.EMPLOYER.value and hasattr(instance, 'employerprofile'):
                instance.employerprofile.delete()

            # Create new profile if needed
            if new_user_role == UserRole.TALENT.value and not hasattr(instance, 'talentprofile'):
                TalentProfile.objects.create(user=instance)
            elif new_user_role == UserRole.EMPLOYER.value and not hasattr(instance, 'employerprofile'):
                EmployerProfile.objects.create(user=instance)
        
        instance.user_role = new_user_role
        instance.save()
        return instance

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
        read_only_fields = ('username', 'email')  # Usually, username/email are not updatable

    def update(self, instance, validated_data):
        instance.phone_number = validated_data.get('phone_number', instance.phone_number)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.save()
        return instance





# from django.contrib.auth import authenticate
# from rest_framework import serializers
# import re
# from django.core.mail import send_mail
# from django.conf import settings
# from rest_framework import status
# from django.db import transaction  # Import transaction for atomic operations

# # IMPORTANT: Import CustomUser and UserRole from talent_management.models
# from talent_management.models import CustomUser, UserRole, TalentProfile, EmployerProfile


# class RegisterSerializer(serializers.ModelSerializer):
#     password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
#     confirm_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
#     phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

#     user_role = serializers.ChoiceField(
#         choices=[
#             (UserRole.ADMIN.value, UserRole.ADMIN.label),
#             (UserRole.TALENT.value, UserRole.TALENT.label),
#             (UserRole.EMPLOYER.value, UserRole.EMPLOYER.label)
#         ],
#         required=True
#     )

#     class Meta:
#         model = CustomUser
#         # CORRECTED: Explicitly list only the fields a user should provide during registration.
#         # Ensure these fields are also present in your CustomUser model.
#         fields = (
#             'username',
#             'email',
#             'phone_number', # If it's a field on CustomUser
#             'password',
#             'confirm_password',
#             'user_role',
#             # Add any other fields from CustomUser that should be settable during registration.
#             # For example, if CustomUser has 'first_name' and 'last_name' that you want users to fill:
#             'first_name',
#             'last_name',
#             # If your CustomUser has a field like 'is_active', do NOT include it here as it's set in create()
#             # If your CustomUser has 'otp' or 'otp_created_at', do NOT include them here.
#         )
#         # You can remove extra_kwargs for password if you set write_only=True directly on the field
#         # extra_kwargs = {
#         #     'password': {'write_only': True}
#         # }

#     def validate(self, data):
#         if data['password'] != data['confirm_password']:
#             raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

#         # Changed to use filter().exists() for better performance and consistency
#         if CustomUser.objects.filter(username=data['username']).exists():
#             raise serializers.ValidationError({"username": "A user with that username already exists."})

#         if CustomUser.objects.filter(email=data['email']).exists():
#             raise serializers.ValidationError({"email": "A user with that email already exists."})

#         if data.get('phone_number'):
#             if CustomUser.objects.filter(phone_number=data['phone_number']).exists():
#                 raise serializers.ValidationError({"phone_number": "A user with that phone number already exists."})

#         return data

#     def validate_password(self, value):
#         if len(value) < 8:
#             raise serializers.ValidationError("Password must be at least 8 characters long.")
#         if not re.search(r'[A-Z]', value):
#             raise serializers.ValidationError("Password must contain at least one uppercase letter.")
#         if not re.search(r'[a-z]', value):
#             raise serializers.ValidationError("Password must contain at least one lowercase letter.")
#         if not re.search(r'[0-9]', value):
#             raise serializers.ValidationError("Password must contain at least one digit.")
#         if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?`~]', value):
#             raise serializers.ValidationError("Password must contain at least one special character.")
#         return value

#     def create(self, validated_data):
#         validated_data.pop('confirm_password')
#         user_role = validated_data.pop('user_role')

#         user = CustomUser.objects.create_user(
#             username=validated_data['username'],
#             email=validated_data['email'],
#             password=validated_data['password'],
#             phone_number=validated_data.get('phone_number'),
#             # Ensure 'first_name' and 'last_name' are passed if they are in 'fields' and present in validated_data
#             first_name=validated_data.get('first_name', ''), # Added
#             last_name=validated_data.get('last_name', ''),   # Added
#             user_role=user_role,
#             is_active=False
#         )

#         if user_role == UserRole.TALENT:
#             TalentProfile.objects.create(user=user)
#         elif user_role == UserRole.EMPLOYER:
#             EmployerProfile.objects.create(user=user)

#         otp = user.generate_otp()

#         subject = 'Your OTP for Registration Verification'
#         message = f'Hi {user.username},\n\nYour One-Time Password (OTP) for registration is: {otp}\n\nThis OTP is valid for 5 minutes.'
#         from_email = settings.DEFAULT_FROM_EMAIL
#         recipient_list = [user.email]
#         try:
#             send_mail(subject, message, from_email, recipient_list, fail_silently=False)
#         except Exception as e:
#             user.delete()
#             print(f"Error sending OTP email to {user.email}: {e}")
#             raise serializers.ValidationError(
#                 {'email': "Failed to send OTP email. Please ensure your email configuration is correct and try again."},
#                 code='email_send_failure'
#             )

#         return user


# class LoginSerializer(serializers.Serializer):
#     phone_or_email = serializers.CharField(required=True)
#     password = serializers.CharField(write_only=True)

#     def validate(self, data):
#         phone_or_email = data.get('phone_or_email')
#         password = data.get('password')

#         user = None
#         if phone_or_email and password:
#             user = authenticate(username=phone_or_email, password=password)

#             if not user and '@' in phone_or_email:
#                 try:
#                     user_by_email = CustomUser.objects.get(email=phone_or_email)
#                     user = authenticate(username=user_by_email.username, password=password)
#                     if user and user.user_role not in [UserRole.TALENT.value, UserRole.EMPLOYER.value, UserRole.ADMIN.value]:
#                         raise serializers.ValidationError('User role is invalid or not recognized.')
#                 except CustomUser.DoesNotExist:
#                     pass

#             if not user and not '@' in phone_or_email:
#                 try:
#                     user_by_phone = CustomUser.objects.get(phone_number=phone_or_email)
#                     user = authenticate(username=user_by_phone.username, password=password)
#                     if user and user.user_role not in [UserRole.TALENT.value, UserRole.EMPLOYER.value, UserRole.ADMIN.value]:
#                         raise serializers.ValidationError('User role is invalid or not recognized.')
#                 except CustomUser.DoesNotExist:
#                     pass

#             if not user:
#                 raise serializers.ValidationError('Invalid credentials.')
#             if not user.is_active:
#                 raise serializers.ValidationError('Account not verified. Please verify your email.')
#         else:
#             raise serializers.ValidationError('Must include "phone_or_email" and "password".')

#         data['user'] = user
#         return data


# class OTPVerificationSerializer(serializers.Serializer):
#     username = serializers.CharField(required=True)
#     otp = serializers.CharField(required=True, max_length=6)

#     def validate(self, data):
#         username = data.get('username')
#         otp_received = data.get('otp')

#         try:
#             user = CustomUser.objects.get(username=username)
#         except CustomUser.DoesNotExist:
#             raise serializers.ValidationError({'username': 'Invalid username or user not found.'})

#         if user.is_active:
#             raise serializers.ValidationError({'message': 'Account already verified.'})

#         if not user.otp or not user.otp_created_at:
#             raise serializers.ValidationError({'otp': 'No OTP generated for this user. Please register again or request a new OTP.'})

#         if not user.is_otp_valid():
#             raise serializers.ValidationError({'otp': 'OTP has expired. Please request a new OTP.'})

#         if user.otp != otp_received:
#             raise serializers.ValidationError({'otp': 'Invalid OTP.'})

#         data['user'] = user
#         return data

# class CustomUserAdminSerializer(serializers.ModelSerializer):
#     """
#     Serializer for Admin to view, create, and update CustomUser objects.
#     Excludes sensitive fields like password for retrieval.
#     Includes all relevant user details and role information.
#     """
#     password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
#     is_talent_role = serializers.BooleanField(read_only=True)
#     is_employer_role = serializers.BooleanField(read_only=True)

#     class Meta:
#         model = CustomUser
#         fields = (
#             'id', 'username', 'email', 'phone_number', 'first_name', 'last_name',
#             'user_role', 'is_talent_role', 'is_employer_role', 'is_staff',
#             'is_active', 'date_joined', 'last_login', 'password', 'groups', 'user_permissions'
#         )
#         read_only_fields = ('date_joined', 'last_login', 'id', 'is_talent_role', 'is_employer_role')
#         extra_kwargs = {
#             'password': {'write_only': True, 'required': False} # Password is optional for updates
#         }

#     def validate_password(self, value):
#         # Only validate password if it's provided (for updates or creation)
#         if value:
#             if len(value) < 8:
#                 raise serializers.ValidationError("Password must be at least 8 characters long.")
#             if not re.search(r'[A-Z]', value):
#                 raise serializers.ValidationError("Password must contain at least one uppercase letter.")
#             if not re.search(r'[a-z]', value):
#                 raise serializers.ValidationError("Password must contain at least one lowercase letter.")
#             if not re.search(r'[0-9]', value):
#                 raise serializers.ValidationError("Password must contain at least one digit.")
#             if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'\",.<>/?`~]', value):
#                 raise serializers.ValidationError("Password must contain at least one special character.")
#         return value

#     def create(self, validated_data):
#         password = validated_data.pop('password', None)
#         user_role = validated_data.get('user_role', UserRole.TALENT.value) # Default to TALENT if not provided
#         is_active = validated_data.get('is_active', False) # Default to inactive unless specified

#         user = CustomUser.objects.create_user(
#             username=validated_data['username'],
#             email=validated_data['email'],
#             password=password, # Use create_user for password hashing
#             **validated_data # Pass remaining validated data
#         )
#         user.user_role = user_role # Set user role after creation
#         user.is_active = is_active # Set active status
#         user.save()

#         # Create associated profiles based on role
#         if user_role == UserRole.TALENT and not hasattr(user, 'talentprofile'):
#             TalentProfile.objects.create(user=user)
#         elif user_role == UserRole.EMPLOYER and not hasattr(user, 'employerprofile'):
#             EmployerProfile.objects.create(user=user)

#         return user

#     def update(self, instance, validated_data):
#         password = validated_data.pop('password', None)
#         user_role = validated_data.get('user_role')
#         is_active = validated_data.get('is_active')

#         # Update password if provided
#         if password:
#             instance.set_password(password)

#         # Handle user role change and profile creation/deletion
#         if user_role and user_role != instance.user_role:
#             with transaction.atomic():
#                 # Delete old profile if exists
#                 if instance.user_role == UserRole.TALENT and hasattr(instance, 'talentprofile'):
#                     instance.talentprofile.delete()
#                 elif instance.user_role == UserRole.EMPLOYER and hasattr(instance, 'employerprofile'):
#                     instance.employerprofile.delete()

#                 instance.user_role = user_role # Update the user's role

#                 # Create new profile if needed
#                 if user_role == UserRole.TALENT and not hasattr(instance, 'talentprofile'):
#                     TalentProfile.objects.create(user=instance)
#                 elif user_role == UserRole.EMPLOYER and not hasattr(instance, 'employerprofile'):
#                     EmployerProfile.objects.create(user=instance)

#         # Update other fields
#         for attr, value in validated_data.items():
#             setattr(instance, attr, value)

#         instance.save()
#         return instance

# class UserRoleUpdateSerializer(serializers.ModelSerializer):
#     """
#     Serializer specifically for an admin to update a user's role and active status.
#     """
#     class Meta:
#         model = CustomUser
#         fields = ['user_role', 'is_active']

#     def validate_user_role(self, value):
#         if value not in [UserRole.ADMIN.value, UserRole.TALENT.value, UserRole.EMPLOYER.value]:
#             raise serializers.ValidationError("Invalid user role.")
#         return value

#     def update(self, instance, validated_data):
#         new_user_role = validated_data.get('user_role')
#         new_is_active = validated_data.get('is_active')

#         if new_user_role and new_user_role != instance.user_role:
#             with transaction.atomic():
#                 # Delete old profile if exists
#                 if instance.user_role == UserRole.TALENT and hasattr(instance, 'talentprofile'):
#                     instance.talentprofile.delete()
#                 elif instance.user_role == UserRole.EMPLOYER and hasattr(instance, 'employerprofile'):
#                     instance.employerprofile.delete()

#                 instance.user_role = new_user_role

#                 # Create new profile if needed
#                 if new_user_role == UserRole.TALENT and not hasattr(instance, 'talentprofile'):
#                     TalentProfile.objects.create(user=instance)
#                 elif new_user_role == UserRole.EMPLOYER and not hasattr(instance, 'employerprofile'):
#                     EmployerProfile.objects.create(user=instance)

#         if new_is_active is not None:
#             instance.is_active = new_is_active

#         instance.save()
#         return instance

# class UserUpdateSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = CustomUser
#         fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
#         read_only_fields = ('username', 'email')  # Usually, username/email are not updatable

#     def update(self, instance, validated_data):
#         instance.phone_number = validated_data.get('phone_number', instance.phone_number)
#         instance.first_name = validated_data.get('first_name', instance.first_name)
#         instance.last_name = validated_data.get('last_name', instance.last_name)
#         instance.save()
#         return instance
