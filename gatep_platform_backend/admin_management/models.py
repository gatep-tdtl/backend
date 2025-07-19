# admin_management/models.py
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
# Assuming CustomUser is available from talent_management.models if you want to link logs to users
# from talent_management.models import CustomUser 

class SystemHealthStatus(models.Model):
    """
    Model to store the health status of various system services.
    This replaces the static list in the dashboard view and allows dynamic updates.
    """
    class ServiceStatusChoices(models.TextChoices):
        ONLINE = 'ONLINE', _('Online')
        OFFLINE = 'OFFLINE', _('Offline')
        MAINTENANCE = 'MAINTENANCE', _('Maintenance')
        DEGRADED = 'DEGRADED', _('Degraded')
        UNKNOWN = 'UNKNOWN', _('Unknown') # Added UNKNOWN for initial states

    service_name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Name of the system service (e.g., 'Aadhaar Integration', 'DigiLocker API')")
    )
    status = models.CharField(
        max_length=20,
        choices=ServiceStatusChoices.choices,
        default=ServiceStatusChoices.UNKNOWN, # Default to UNKNOWN for new services
        help_text=_("Current health status of the service")
    )
    last_checked = models.DateTimeField(
        auto_now=True, # Automatically updates on each save
        help_text=_("Timestamp of the last status update")
    )
    message = models.TextField(
        blank=True,
        null= True,
        help_text=_("Optional message about the service status (e.g., reason for downtime)")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this service status is actively monitored and displayed.")
    )

    class Meta:
        verbose_name = _("System Health Status")
        verbose_name_plural = _("System Health Statuses")
        ordering = ['service_name'] # Order alphabetically by service name

    def __str__(self):
        return f"{self.service_name}: {self.get_status_display()}"


class AdminActivityLog(models.Model):
    """
    Model to log administrative actions performed in the system.
    This can be useful for auditing and tracking changes by admins.
    """
    # If you want to link to a specific admin user, uncomment the import and this field
    # user = models.ForeignKey(
    #     CustomUser,
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name='admin_activities',
    #     limit_choices_to={'user_role': 'ADMIN'} # Or is_staff=True
    # )
    action = models.CharField(
        max_length=255,
        help_text=_("Description of the administrative action performed.")
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the action was performed.")
    )
    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        help_text=_("IP address from which the action was initiated.")
    )
    details = models.JSONField(
        blank=True,
        null=True,
        help_text=_("Additional JSON details about the action (e.g., old_value, new_value, affected_object_id).")
    )

    class Meta:
        verbose_name = _("Admin Activity Log")
        verbose_name_plural = _("Admin Activity Logs")
        ordering = ['-timestamp'] # Order by most recent activity first

    def __str__(self):
        return f"{self.action} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"




























################## rahul's old code below ############################



# ### models.py
# from django.contrib.auth.models import AbstractUser
# from django.db import models

# class CustomUser(AbstractUser):
#     ROLE_CHOICES = [
#         ('talent', 'Talent'),
#         ('employer', 'Employer'),
#         ('admin', 'Admin'),
#     ]

#     STATUS_CHOICES = [
#         ('active', 'Active'),
#         ('pending', 'Pending'),
#         ('suspended', 'Suspended'),
#     ]

#     email = models.EmailField(unique=True)
#     role = models.CharField(max_length=20, choices=ROLE_CHOICES)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
#     location = models.CharField(max_length=100, blank=True, null=True)
#     join_date = models.DateField(auto_now_add=True)
#     last_login_date = models.DateField(null=True, blank=True)
#     performance = models.JSONField(default=dict, blank=True)

#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = ['username']

#     def save(self, *args, **kwargs):
#         if self.role == 'admin':
#             self.is_staff = True
#         else:
#             self.is_staff = False
#         super().save(*args, **kwargs)

#     def __str__(self):
#         return f"{self.username} ({self.role})"
