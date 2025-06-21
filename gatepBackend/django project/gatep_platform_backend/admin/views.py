### models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('talent', 'Talent'),
        ('employer', 'Employer'),
        ('admin', 'Admin'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('suspended', 'Suspended'),
    ]

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    location = models.CharField(max_length=100, blank=True, null=True)
    join_date = models.DateField(auto_now_add=True)
    last_login_date = models.DateField(null=True, blank=True)
    performance = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        if self.role == 'admin':
            self.is_staff = True
        else:
            self.is_staff = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"


### serializers.py
from rest_framework import serializers
from .models import CustomUser

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'location',
            'role', 'status', 'join_date', 'last_login_date', 'performance'
        ]


### permissions.py
from rest_framework.permissions import BasePermission

class IsRoleAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


### views.py
from rest_framework import viewsets, filters
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import CustomUser
from .serializers import UserSerializer
from .permissions import IsRoleAdmin

class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsRoleAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email']

    def get_queryset(self):
        queryset = super().get_queryset()
        role = self.request.query_params.get('role')
        status = self.request.query_params.get('status')
        if role and role.lower() != 'all':
            queryset = queryset.filter(role__iexact=role)
        if status and status.lower() != 'all':
            queryset = queryset.filter(status__iexact=status)
        return queryset

@api_view(['GET'])
def get_filter_choices(request):
    return Response({
        "roles": ["all", "talent", "employer", "admin"],
        "statuses": ["all", "active", "pending", "suspended"]
    })
