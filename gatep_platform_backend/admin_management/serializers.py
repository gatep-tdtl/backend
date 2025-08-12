# admin_management/serializers.py
from rest_framework import serializers
from talent_management.models import CustomUser
from employer_management.models import Application, JobPosting
from .models import SystemHealthStatus # Make sure this import is correct

# Original User Dashboard Serializer - UNCHANGED
class UserDashboardSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    performance = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'username',
            'email',
            'role',
            'status',
            'date_joined',
            'last_login',
            'performance',
            'actions'
        ]

    def get_role(self, obj):
        return "Admin" if obj.is_superuser else obj.user_role

    def get_status(self, obj):
        if getattr(obj, 'is_suspended', False):
            return "suspended"
        return "active" if obj.is_active else "pending"

    def get_performance(self, obj):
        if obj.user_role == 'TALENT':
            applications = Application.objects.filter(talent=obj).count()
            return {
                'profile': "95%",  # if you have actual profile logic, replace this
                'applications': applications
            }
        elif obj.user_role == 'EMPLOYER':
            job_posts = JobPosting.objects.filter(company__user=obj).count()
            hires = Application.objects.filter(job_posting__company__user=obj, status='HIRED').count()
            return {
                'jobs_posted': job_posts,
                'hires': hires
            }
        return {}

    def get_actions(self, obj):
        return {
            'edit': True,
            'suspend': True,
            'delete': True,
            'patch_url': f"/api/admin/analytics/users/{obj.id}/"
        }

# Corrected SystemHealthStatusSerializer (ModelSerializer version) - Use this one consistently
class SystemHealthStatusModelSerializer(serializers.ModelSerializer):
    """
    Serializer for the SystemHealthStatus model.
    Used for both the ViewSet and the GlobalDashboardOverviewSerializer.
    """
    # Optional: If you want the display value instead of the raw choice value
    # status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SystemHealthStatus
        fields = '__all__' # Include all fields for CRUD operations
        read_only_fields = ['last_checked'] # last_checked is auto_now, don't allow setting from input

# --- Nested Serializers for GlobalDashboardOverviewSerializer ---
class CountGrowthSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    growth_percent = serializers.CharField()

class QuickActionSerializer(serializers.Serializer):
    label = serializers.CharField()
    link = serializers.CharField()

class RegionalPerformanceSerializer(serializers.Serializer):
    region = serializers.CharField()
    placements = serializers.IntegerField()
    growth = serializers.CharField()
    status = serializers.CharField() # Ensure status is always present from your view

class SkillInDemandSerializer(serializers.Serializer):
    skill = serializers.CharField()
    placements = serializers.IntegerField()
    growth = serializers.CharField()

class TopInstitutionSerializer(serializers.Serializer):
    institution = serializers.CharField()
    graduates = serializers.IntegerField()
    placements = serializers.IntegerField()
    success_rate = serializers.CharField()

class RecentSystemActivitySerializer(serializers.Serializer):
    type = serializers.CharField()
    description = serializers.CharField()
    time_ago = serializers.CharField()

class KeyPerformanceIndicatorsSerializer(serializers.Serializer):
    profile_completion = serializers.CharField()
    interview_success_rate = serializers.CharField()
    average_placement_time = serializers.CharField()
    employer_satisfaction = serializers.CharField()

# Main Global Dashboard Overview Serializer - CORRECTED
class GlobalDashboardOverviewSerializer(serializers.Serializer):
    
    # These fields directly match the top-level keys in your response_data
    registered_ai_talent = CountGrowthSerializer()
    global_employers = CountGrowthSerializer()
    active_placements = CountGrowthSerializer()
    total_placements = serializers.IntegerField() # This is a direct count, not a dict

    quick_actions = QuickActionSerializer(many=True)
    regional_performance = RegionalPerformanceSerializer(many=True) # Renamed to match views.py

    # These fields are currently placeholders in views.py, so they are required=False or handle empty list
    skills_in_high_demand = SkillInDemandSerializer(many=True, required=False) # Add required=False
    top_performing_institutions = TopInstitutionSerializer(many=True, required=False) # Add required=False

    # This now uses the ModelSerializer for SystemHealthStatus
   
    recent_system_activity = RecentSystemActivitySerializer(many=True)
    key_performance_indicators = KeyPerformanceIndicatorsSerializer() # Nested serializer for KPIs


# You had these duplicate serializers at the end. They seem to belong to the `dashboard_api`
# function which is also a separate, likely older, dashboard view.
# If you intend to use `dashboard_api`, you should place these serializers logically with it,
# perhaps in a separate `dashboard_serializers.py` or just keep them if they are not conflicting.
# For now, I'm keeping them as is, assuming they are for a different endpoint,
# but it's good to be aware of the redundancy.
class RegionSerializer(serializers.Serializer):
    code = serializers.CharField()
    placements = serializers.IntegerField()
    growth = serializers.CharField()
    avg_salary = serializers.IntegerField()
    demand_score = serializers.CharField()
    top_roles = serializers.ListField(child=serializers.CharField())

class SkillSerializer(serializers.Serializer):
    name = serializers.CharField()
    growth = serializers.CharField()
    placements = serializers.IntegerField()

class InstitutionSerializer(serializers.Serializer):
    name = serializers.CharField()
    graduates = serializers.IntegerField()
    placements = serializers.IntegerField()
    success_rate = serializers.CharField()

class CulturalDataSerializer(serializers.Serializer):
    languages = serializers.ListField(child=serializers.CharField())
    adaptation_rates = serializers.DictField(child=serializers.CharField())
    retention_rate = serializers.CharField()







###################### Rahul's Code Snippet ######################

# from rest_framework import serializers
# from .models import CustomUser

# class UserSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = CustomUser
#         fields = [
#             'id', 'username', 'email', 'location',
#             'role', 'status', 'join_date', 'last_login_date', 'performance'
#         ]


# ### permissions.py
# from rest_framework.permissions import BasePermission

# class IsRoleAdmin(BasePermission):
#     def has_permission(self, request, view):
#         return request.user.is_authenticated and request.user.role == 'admin'




 

 
 
class LanguageFitSerializer(serializers.Serializer):
    language = serializers.CharField()
    count = serializers.IntegerField()
 
 
class CulturalAdaptationSerializer(serializers.Serializer):
    country = serializers.CharField(allow_null=True, allow_blank=True)
    success_rate = serializers.FloatField()
 
 

 
class SkillsDemandSerializer(serializers.Serializer):
    skill = serializers.CharField()
    count = serializers.IntegerField()
 
 
# ------------------ Main Dashboard Serializer ------------------
 
class AdminAnalyticsDashboardSerializer(serializers.Serializer):
    total_ai_talent = serializers.IntegerField()
    active_placements = serializers.IntegerField()
    global_employers = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_days_to_place = serializers.IntegerField()
 
    top_institutions = TopInstitutionSerializer(many=True)
    language_fit = LanguageFitSerializer(many=True)
    cultural_adaptation = CulturalAdaptationSerializer(many=True)
    regional_performance = RegionalPerformanceSerializer(many=True)
    skills_demand = SkillsDemandSerializer(many=True)