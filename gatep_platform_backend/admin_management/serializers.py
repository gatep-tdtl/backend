from rest_framework import serializers
from talent_management.models import CustomUser
from employer_management.models import Application, JobPosting
from .models import SystemHealthStatus
 
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
        return "Admin" if obj.is_superuser else obj.get_user_role_display()
 
    def get_status(self, obj):
        # Assuming you might add an 'is_suspended' field later.
        # For now, it's based on 'is_active'.
        if getattr(obj, 'is_suspended', False):
            return "suspended"
        return "active" if obj.is_active else "pending"
 
    def get_performance(self, obj):
        if obj.user_role == 'TALENT':
            applications = Application.objects.filter(talent=obj).count()
            # Placeholder for profile completion logic
            return {
                'profile': "95%",
                'applications': applications
            }
        elif obj.user_role == 'EMPLOYER':
            # Note: The original JobPosting model doesn't link directly to a user, but to a Company.
            # This assumes a link `company.user` exists.
            job_posts = JobPosting.objects.filter(company__user=obj).count()
            hires = Application.objects.filter(job_posting__company__user=obj, status='HIRED').count()
            return {
                'jobs_posted': job_posts,
                'hires': hires
            }
        return {}
 
    def get_actions(self, obj):
        # Example actions
        return {
            'edit': True,
            'suspend': True,
            'delete': True,
            'patch_url': f"/api/admin/users/{obj.id}/" # Adjust URL as needed
        }
 
# --- NEW/UPDATED SERIALIZERS FOR THE DYNAMIC DASHBOARD ---
 
# Serializer for the new SystemHealthStatus model
class SystemHealthStatusModelSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
 
    class Meta:
        model = SystemHealthStatus
        fields = ['id', 'service_name', 'status', 'status_display', 'details', 'last_checked']
 
# --- Nested Serializers for GlobalDashboardOverviewSerializer ---
class CountGrowthSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    growth_percent = serializers.FloatField()
 
class RegionalPerformanceSerializer(serializers.Serializer):
    region = serializers.CharField()
    placements = serializers.IntegerField()
    growth = serializers.FloatField()
    status = serializers.CharField()
 
class SkillInDemandSerializer(serializers.Serializer):
    skill = serializers.CharField()
    placements = serializers.IntegerField()
    growth = serializers.FloatField()
 
class TopInstitutionSerializer(serializers.Serializer):
    institution = serializers.CharField()
    graduates = serializers.IntegerField()
    placements = serializers.IntegerField()
    success_rate = serializers.FloatField()
 
class RecentSystemActivitySerializer(serializers.Serializer):
    type = serializers.CharField()
    description = serializers.CharField()
    time_ago = serializers.CharField()
 
class KeyPerformanceIndicatorsSerializer(serializers.Serializer):
    profile_completion_rate = serializers.FloatField()
    interview_success_rate = serializers.FloatField()
    average_placement_time_days = serializers.FloatField()
    employer_satisfaction_rate = serializers.FloatField()
 
# Main Global Dashboard Overview Serializer - FULLY UPDATED
class GlobalDashboardOverviewSerializer(serializers.Serializer):
    registered_ai_talent = CountGrowthSerializer()
    global_employers = CountGrowthSerializer()
    active_placements = CountGrowthSerializer()
    total_placements = serializers.IntegerField()

    regional_performance = RegionalPerformanceSerializer(many=True)
    skills_in_high_demand = SkillInDemandSerializer(many=True)
    top_performing_institutions = TopInstitutionSerializer(many=True)








class KPISerializer(serializers.Serializer):
    profile_completion_rate = serializers.FloatField()
    interview_success_rate = serializers.FloatField()
    average_placement_time_days = serializers.FloatField()
    employer_satisfaction_rate = serializers.FloatField()

class RecentActivitySerializer(serializers.Serializer):
    type = serializers.CharField()
    description = serializers.CharField()
    time_ago = serializers.CharField()

# class GlobalDashboardOverviewSerializer(serializers.Serializer):
#     registered_ai_talent = serializers.DictField()
#     global_employers = serializers.DictField()
#     active_placements = serializers.DictField()
#     total_placements = serializers.IntegerField()
#     regional_performance = serializers.ListField()
    
#     # --- THESE FIELDS ARE CAUSING THE ERROR ---
#     skills_in_high_demand = serializers.ListField(child=serializers.DictField())
#     top_performing_institutions = serializers.ListField(child=serializers.DictField())
#     system_health = serializers.ListField(child=serializers.DictField())
#     recent_system_activity = RecentActivitySerializer(many=True)
#     key_performance_indicators = KPISerializer()







class TalentDistributionSerializer(serializers.Serializer):
    """
    Serializer for the state-wise talent distribution data.
    """
    state = serializers.CharField(source='current_state')
    count = serializers.IntegerField()

class TalentFilterOptionsSerializer(serializers.Serializer):
    """
    Serializer for the available filter options (roles and certifications).
    """
    roles = serializers.ListField(child=serializers.CharField())
    certifications = serializers.ListField(child=serializers.CharField())