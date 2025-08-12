
# admin_management/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status, permissions 
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from collections import Counter
from django.db.models import Count, Avg, Q, F # Ensure F is imported for database functions
 # Your existing model imports
from talent_management.models import CustomUser, UserRole, TalentProfile, Resume 
from employer_management.models import JobPosting, Application, Interview, ApplicationStatus, InterviewStatus
from rest_framework import status, permissions, viewsets # <-- Make sure 'viewsets' is included here
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import (
    UserDashboardSerializer,SystemHealthStatusModelSerializer, # <--- CHANGE THIS LINE
    GlobalDashboardOverviewSerializer,
    # Also include other serializers if they are being used by dashboard_api, etc.
    RegionSerializer,
    SkillSerializer,
    InstitutionSerializer,
    CulturalDataSerializer
)
# ... (other imports like timezone, timedelta, Count, Q, models, serializers) ...

from .permission import IsRoleAdmin 
# NEW: Import SystemHealthStatus from your admin_management app's models
from .models import SystemHealthStatus # Assuming SystemHealthStatus is now in admin_management/models.py

# Your existing serializer


# Your DashboardSummaryAPIView (UNCHANGED as per your request)
class DashboardSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated] # Temp for debugging
    def get(self, request):
        all_users_qs = CustomUser.objects.all()
        total_users = all_users_qs.count()
        active_users = all_users_qs.filter(is_active=True).count()
        pending_users = all_users_qs.filter(is_active=False).count()
        admins = all_users_qs.filter(is_superuser=True).count()
        employers = all_users_qs.filter(user_role=UserRole.EMPLOYER).count()
        ai_talent_count = 0
        ai_keywords = ['AI', 'Artificial Intelligence', 'Machine Learning', 'Deep Learning', 'NLP', 'Computer Vision']
        talent_users_qs = all_users_qs.filter(user_role=UserRole.TALENT)
        for talent_user in talent_users_qs:
            latest_resume = Resume.objects.filter(talent=talent_user, is_deleted=False).order_by('-updated_at').first()
            if latest_resume and latest_resume.skills:
                skills_lower = latest_resume.skills.lower()
                if any(keyword.lower() in skills_lower for keyword in ai_keywords):
                    ai_talent_count += 1
        time_range = request.query_params.get('time_range', 'Last 6 Months')
        end_date = timezone.now()
        date_threshold = {
            'Last Month': end_date - timedelta(days=30),
            'Last 3 Months': end_date - timedelta(days=90),
            'Last 6 Months': end_date - timedelta(days=180),
            'Last Year': end_date - timedelta(days=365)
        }.get(time_range, end_date - timedelta(days=180))
        users_for_trend_qs = all_users_qs.filter(join_date__gte=date_threshold) # Potential issue: 'join_date' vs 'date_joined'
        trend_counter = Counter(users_for_trend_qs.datetimes('join_date', 'month')) # Potential issue: 'join_date' vs 'date_joined'
        user_trend = [
            {"month": dt.strftime("%b %Y"), "user_count": count}
            for dt, count in sorted(trend_counter.items())
        ]
        recent_activities = users_for_trend_qs.order_by('-join_date')[:5] # Potential issue: 'join_date' vs 'date_joined'
        recent_activity_list = [
            {
                "username": user.username,
                "activity": f"New {user.user_role.label} signed up" if hasattr(user.user_role, 'label') else f"New {user.user_role} signed up",
                "time_ago": user.join_date.strftime("%b %d, %Y") # Potential issue: 'join_date' vs 'date_joined'
            }
            for user in recent_activities
        ]
        role_distribution_raw = all_users_qs.values('user_role').annotate(count=Count('user_role'))
        role_distribution = [
            {"role": item['user_role'], "count": item['count']}
            for item in role_distribution_raw
        ]
        return Response({
            "summary_stats": {
                "total_users": total_users,
                "active_users": active_users,
                "pending_users": pending_users, 
                "admins": admins,            
                "employers": employers,        
                "ai_talent": ai_talent_count,  
            },
            "user_trend": user_trend,
            "recent_activity": recent_activity_list,
            "role_distribution": role_distribution,
        }, status=status.HTTP_200_OK)


# Your UserDashboardAPIView (UNCHANGED as per your request, except for necessary import adjustment)
class UserDashboardAPIView(APIView):
    """
    API for managing users in the dashboard.
    Supports GET (list/retrieve), POST (create), PUT (full update), PATCH (partial update), DELETE (soft delete).
    Requires authentication (temporarily for debugging).
    """
    permission_classes = [permissions.IsAuthenticated] # Keep this temporarily for debugging
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    def get(self, request, pk=None):
        if pk: # Retrieve single user by ID
            user = get_object_or_404(CustomUser, pk=pk)
            serializer = UserDashboardSerializer(user)
            return Response(serializer.data)

        # List users with filters
        role_filter = request.GET.get('role')
        status_filter = request.GET.get('status')
        users_qs = CustomUser.objects.all()

        if role_filter and role_filter.lower() != 'all roles':
            if role_filter.lower() == 'admins':
                users_qs = users_qs.filter(is_superuser=True)
            else:
                users_qs = users_qs.filter(user_role__iexact=role_filter)

        if status_filter and status_filter.lower() != 'all status':
            if status_filter.lower() == 'active':
                users_qs = users_qs.filter(is_active=True)
            elif status_filter.lower() == 'pending':
                users_qs = users_qs.filter(is_active=False)
            # Removed 'suspended' filter as 'is_suspended' is not a field.
            # If you need to filter by 'suspended', ensure you add an 'is_suspended' field
            # to CustomUser or define 'suspended' by other means (e.g., a custom status CharField).
            # elif status_filter.lower() == 'suspended':
            #     users_qs = users_qs.filter(is_suspended=True) 
        
        serializer = UserDashboardSerializer(users_qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserDashboardSerializer(data=request.data)
        if serializer.is_valid():
            password = serializer.validated_data.pop('password', None)
            user = serializer.save()
            if password:
                user.set_password(password)
                user.save()
            return Response(UserDashboardSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None):
        if not pk:
            return Response({"error": "User ID (pk) is required for PUT."}, status=status.HTTP_400_BAD_REQUEST)
        user = get_object_or_404(CustomUser, pk=pk)

        serializer = UserDashboardSerializer(user, data=request.data)
        if serializer.is_valid():
            password = serializer.validated_data.pop('password', None)
            user = serializer.save()
            if password:
                user.set_password(password)
                user.save()
            return Response(UserDashboardSerializer(user).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk=None):
        if not pk:
            return Response({"error": "User ID (pk) is required for PATCH."}, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(CustomUser, pk=pk)
        data = request.data

        if 'password' in data:
            user.set_password(data['password'])
            data.pop('password')

        if 'status' in data:
            status_value = data['status'].lower()
            if status_value == 'active':
                user.is_active = True
            elif status_value == 'pending':
                user.is_active = False
            elif status_value == 'suspended':
                user.is_active = False # Mark as inactive if suspended
                # If you have a dedicated 'is_suspended' field, set it here: user.is_suspended = True
            else:
                return Response({"error": "Invalid status value."}, status=status.HTTP_400_BAD_REQUEST)
            data.pop('status') # Remove status from data as it's handled manually

        serializer = UserDashboardSerializer(user, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            user.save() # Save user object for password/status changes
            return Response(UserDashboardAPIView(user).data, status=status.HTTP_200_OK) # Potential issue: should be serializer.data
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        """
        Performs a soft delete on a user by setting is_active to False.
        Requires admin authentication.
        """
        if not pk:
            return Response({"error": "User ID (pk) is required for DELETE."}, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(CustomUser, pk=pk)
        
        user.is_active = False
        user.save()

        return Response({"message": f"User '{user.username}' (ID: {pk}) soft-deleted successfully (is_active set to False)."}, status=status.HTTP_200_OK)

 
class GlobalDashboardOverviewAPIView(APIView):
    """
    Provides overview statistics for the Global AI Talent Export Dashboard.
    Static system health (no DB model used).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)

        def calculate_growth(current_count, previous_count):
            if previous_count > 0:
                return ((current_count - previous_count) / previous_count) * 100
            return 0

        ai_keywords = ['AI', 'Artificial Intelligence', 'Machine Learning', 'Deep Learning', 'NLP', 'Computer Vision', 'Data Science']

        # def get_ai_talent_count(start_date=None, end_date=None):
        #     qs = CustomUser.objects.filter(user_role=UserRole.TALENT)
        #     if start_date:
        #         qs = qs.filter(date_joined__date__gte=start_date)
        #     if end_date:
        #         qs = qs.filter(date_joined__date__lte=end_date)

        #     # ➕ Ensure users have resumes
        #     qs = qs.filter(resumes__isnull=False)

        #     ai_skill_conditions = Q()
        #     for keyword in ai_keywords:
        #         ai_skill_conditions |= Q(resumes__skills__icontains=keyword)

        #     matching = qs.filter(ai_skill_conditions).distinct()
        #     print("DEBUG AI Talent Count →", matching.count())
        #     return matching.count()
        def get_ai_talent_count(start_date=None, end_date=None):
            qs = CustomUser.objects.filter(user_role=UserRole.TALENT)
            if start_date:
                qs = qs.filter(date_joined__date__gte=start_date)
            if end_date:
                qs = qs.filter(date_joined__date__lte=end_date)
            return qs.count()
        registered_ai_talent_this_month = get_ai_talent_count(start_date=this_month_start, end_date=today)
        registered_ai_talent_last_month = get_ai_talent_count(start_date=last_month_start, end_date=last_month_end)
        total_registered_ai_talent = get_ai_talent_count()
        registered_ai_talent_growth = calculate_growth(registered_ai_talent_this_month, registered_ai_talent_last_month)

        def get_employer_count(start_date=None, end_date=None):
            qs = CustomUser.objects.filter(user_role=UserRole.EMPLOYER)
            if start_date:
                qs = qs.filter(date_joined__date__gte=start_date)
            if end_date:
                qs = qs.filter(date_joined__date__lte=end_date)
            return qs.count()

        global_employers_this_month = get_employer_count(start_date=this_month_start, end_date=today)
        global_employers_last_month = get_employer_count(start_date=last_month_start, end_date=last_month_end)
        total_global_employers = get_employer_count()
        global_employers_growth = calculate_growth(global_employers_this_month, global_employers_last_month)

        def get_placements_count(status_filter=ApplicationStatus.HIRED, start_date=None, end_date=None):
            qs = Application.objects.filter(status=status_filter)
            if start_date:
                qs = qs.filter(application_date__date__gte=start_date)
            if end_date:
                qs = qs.filter(application_date__date__lte=end_date)
            return qs.count()

        active_placements_this_month = get_placements_count(start_date=this_month_start, end_date=today)
        active_placements_last_month = get_placements_count(start_date=last_month_start, end_date=last_month_end)
        total_placements = get_placements_count()
        active_placements_growth = calculate_growth(active_placements_this_month, active_placements_last_month)

        hired_apps = Application.objects.filter(status=ApplicationStatus.HIRED)

        regional_performance_raw = hired_apps.values('job_posting__location').annotate(placements=Count('id')).order_by('-placements')
        regional_performance_data = []
        for entry in regional_performance_raw:
            region = entry['job_posting__location']
            placements = entry['placements']
            this_month_count = hired_apps.filter(
                job_posting__location=region,
                application_date__date__gte=this_month_start,
                application_date__date__lte=today
            ).count()
            last_month_count = hired_apps.filter(
                job_posting__location=region,
                application_date__date__gte=last_month_start,
                application_date__date__lte=last_month_end
            ).count()
            growth = calculate_growth(this_month_count, last_month_count)
            status_text = "Stable"
            if this_month_count > last_month_count:
                status_text = "Active"
            elif this_month_count < last_month_count and last_month_count > 0:
                status_text = "Declining"

            regional_performance_data.append({
                "region": region,
                "placements": placements,
                "growth": f"{growth:.0f}%",
                "status": status_text
            })

        def get_time_ago_string(dt):
            if isinstance(dt, timezone.datetime):
                diff = timezone.now() - dt
            elif isinstance(dt, timezone.date):
                dt = timezone.make_aware(timezone.datetime.combine(dt, timezone.datetime.min.time()))
                diff = timezone.now() - dt
            else:
                return "N/A"

            if diff.days > 0:
                return f"{diff.days} day(s) ago"
            elif diff.seconds >= 3600:
                return f"{diff.seconds // 3600} hour(s) ago"
            elif diff.seconds >= 60:
                return f"{diff.seconds // 60} minute(s) ago"
            return "just now"

        recent_activities = []
        recent_placements = Application.objects.filter(status=ApplicationStatus.HIRED).select_related('talent', 'job_posting').order_by('-application_date')[:2]
        for app in recent_placements:
            recent_activities.append({
                "type": "Placement",
                "description": f"{app.talent.username} placed for {app.job_posting.title} in {app.job_posting.location or 'Unknown'}",
                "time_ago": get_time_ago_string(app.application_date)
            })

        recent_users = CustomUser.objects.order_by('-date_joined')[:2]
        for user in recent_users:
            role_label = user.get_user_role_display() if hasattr(user, 'get_user_role_display') else user.user_role
            recent_activities.append({
                "type": "Registration",
                "description": f"New {role_label} from {getattr(user, 'location', 'Unknown')} registered",
                "time_ago": get_time_ago_string(user.date_joined)
            })

        verified_count = Resume.objects.filter(
            document_verification='VERIFIED',
            updated_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        recent_activities.append({
            "type": "Verification",
            "description": f"{verified_count} talent profiles verified via DigiLocker",
            "time_ago": "recently"
        })

        recent_interviews = Interview.objects.filter(
            scheduled_at__gte=timezone.now() - timedelta(days=7)
        ).select_related('application__talent', 'application__job_posting').order_by('-scheduled_at')[:2]
        for interview in recent_interviews:
            recent_activities.append({
                "type": "Interview",
                "description": f"Interview scheduled for {interview.application.talent.username} for {interview.application.job_posting.title}",
                "time_ago": get_time_ago_string(interview.scheduled_at)
            })

        system_health_data = [
            {"service": "Aadhaar Integration", "status": "Online"},
            {"service": "DigiLocker API", "status": "Online"},
            {"service": "NSDC Integration", "status": "Online"},
            {"service": "MEA Services", "status": "Maintenance"},
            {"service": "Notification Service", "status": "Online"}
        ]

        total_profiles = TalentProfile.objects.count()
        profile_completion = "75%" if total_profiles > 0 else "N/A"
        total_interviews = Interview.objects.count()
        successful_interviews = Interview.objects.filter(interview_status=InterviewStatus.COMPLETED).count()
        interview_success_rate = (successful_interviews / total_interviews * 100) if total_interviews > 0 else 0
        average_placement_time = "30 Days"
        employer_satisfaction = "92%"

        response_data =  {
            "registered_ai_talent": {
                "count": total_registered_ai_talent,
                "growth_percent": f"{registered_ai_talent_growth:.0f}%"
            },
            "global_employers": {
                "count": total_global_employers,
                "growth_percent": f"{global_employers_growth:.0f}%"
            },
            "active_placements": {
                "count": active_placements_this_month,
                "growth_percent": f"{active_placements_growth:.0f}%"
            },
            "total_placements": total_placements,
            "regional_performance": regional_performance_data,
            "recent_system_activity": recent_activities,
            "SystemHealthStatus": system_health_data,
            "key_performance_indicators": {
                "profile_completion": profile_completion,
                "interview_success_rate": f"{interview_success_rate:.0f}%",
                "average_placement_time": average_placement_time,
                "employer_satisfaction": employer_satisfaction
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)    
# class SystemHealthStatuSViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint that allows SystemHealthStatus to be viewed or edited.
#     Provides CRUD operations for system health statuses.
#     """
#     queryset = SystemHealthStatus.objects.all().order_by('service_name')
#     serializer_class =SystemHealthStatusModelSerializer
#     permission_classes = [permissions.IsAuthenticated,IsRoleAdmin] # Use your custom admin permission




@api_view(['GET'])
def dashboard_api(request):
    # 1. Core Metrics from database
    talent_count = CustomUser.objects.filter(user_role='talent').count()
    employer_count = CustomUser.objects.filter(user_role='employee').count()

    # 2. Sample data - replace with your actual data sources
    regions_data = [{
        'code': 'AE',
        'placements': 1200,
        'growth': '+15%',
        'avg_salary': 85000,
        'demand_score': '95%',
        'top_roles': ['AI Engineer', 'Data Scientist']
    }]

    skills_data = [
        {'name': 'Python', 'growth': '+12%', 'placements': 2340},
        {'name': 'Machine Learning', 'growth': '+18%', 'placements': 2180},
        {'name': 'TensorFlow', 'growth': '+15%', 'placements': 1890},
        {'name': 'AWS', 'growth': '+25%', 'placements': 1650},
        {'name': 'PyTorch', 'growth': '+20%', 'placements': 1420},
        {'name': 'NLP', 'growth': '+30%', 'placements': 0}
    ]

    institutions_data = [
        {'name': 'IIT Bangalore', 'graduates': 245, 'placements': 198, 'success_rate': '81%'},
        {'name': 'IIT Delhi', 'graduates': 220, 'placements': 176, 'success_rate': '80%'},
        {'name': 'IIT Mumbai', 'graduates': 210, 'placements': 163, 'success_rate': '78%'},
        {'name': 'IISC Bangalore','graduates': 180, 'placements': 144, 'success_rate': '80%'},
        {'name': 'IIT Hyderabad','graduates': 165, 'placements': 125, 'success_rate': '76%'},
        {'name': 'IIT Chennai', 'graduates': 155, 'placements': 117, 'success_rate': '75%'}
        
    ]

    cultural_data = {
        'languages': ['English', 'Hindi', 'Tamil', 'Telugu', 'Kannada', 'Marathi'],
        'adaptation_rates': {
            'UAE': '92%',
            'USA': '88%',
            'Singapore': '95%'

        },
        'retention_rate': '87%'
    }

    # 3. Serialize the data
    regions = RegionSerializer(regions_data, many=True)
    skills = SkillSerializer(skills_data, many=True)
    institutions = InstitutionSerializer(institutions_data, many=True)
    cultural = CulturalDataSerializer(cultural_data)

    return Response({
        'metrics': {
            'total_AItalent': talent_count,
            'global_employers': employer_count,
            'Active_placements': 809,  # Example static value
            'success_rate': '3%',
            'avg_placement_days': 45
        },
        'regions': regions.data,
        'skills': skills.data,
        'institutions': institutions.data,
        'cultural_data': cultural.data
    })

from django.db import connections
from datetime import datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
 
 
class TalentHeatmapAPIView(APIView):
    permission_classes = [IsAuthenticated]
 
    def get_statewise_data(self, role=None):
        # Base query
        query = """
            SELECT current_state, COUNT(id) AS professionals
            FROM gatep_platform_db.talent_management_resume
            WHERE current_state IS NOT NULL AND TRIM(current_state) != ''
        """
        params = []
        # Add role filter if present
        if role:
            query += " AND LOWER(TRIM(user_role)) = LOWER(%s)"
            params.append(role.strip())
        query += " GROUP BY current_state"
 
        # Execute query
        with connections['default'].cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
 
        # Clean result
        result = []
        for row in rows:
            state = row[0].strip().title()
            count = row[1]
            result.append({"state": state, "professionals": count})
 
        # Optional: sort by count
        result.sort(key=lambda x: x["professionals"], reverse=True)
        return result
 
    def get(self, request):
        # 1. Overall statewise professionals
        overall_data = self.get_statewise_data()
 
        # 2. Role-specific data
        roles = ["AI/ML Engineer", "Data Scientist", "Business Analyst"]
        rolewise_data = {}
        for role in roles:
            rolewise_data[role] = self.get_statewise_data(role=role)
 
        # 3. Final response
        response = {
            "overall": overall_data,
            "roles": rolewise_data
        }
        return Response(response)



 
from datetime import datetime
from collections import Counter
import json
 
from django.db import connections
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
 
import json
from collections import defaultdict
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
 
class TalentHeatmapInstituteWiseAPIView(APIView):
    def get(self, request):
        institution_counts = defaultdict(int)
 
        # 1. Fetch data from your existing table
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT degree_details, diploma_details
                FROM talent_management_resume
                WHERE degree_details IS NOT NULL OR diploma_details IS NOT NULL
            """)
            rows = cursor.fetchall()
 
        # 2. Loop through each row
        for degree_details, diploma_details in rows:
            # Parse degree details
            if degree_details:
                try:
                    degree_data = json.loads(degree_details)
                    for degree in degree_data:
                        name = degree.get("institution_name")
                        if name:
                            institution_counts[name.strip().lower()] += 1
                except json.JSONDecodeError:
                    pass
 
            # Parse diploma details
            if diploma_details:
                try:
                    diploma_data = json.loads(diploma_details)
                    for diploma in diploma_data:
                        name = diploma.get("institution_name")
                        if name:
                            institution_counts[name.strip().lower()] += 1
                except json.JSONDecodeError:
                    pass
 
        # 3. Format the result
        result = [{"institution": inst, "graduates": count} 
                  for inst, count in institution_counts.items()]
 
        return Response(result)

















############################rahul's old code below ############################


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


# ### serializers.py
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


# ### views.py
# from rest_framework import viewsets, filters
# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from .models import CustomUser
# from .serializers import UserSerializer
# from .permissions import IsRoleAdmin

# class UserViewSet(viewsets.ModelViewSet):
#     queryset = CustomUser.objects.all().order_by('-id')
#     serializer_class = UserSerializer
#     permission_classes = [IsRoleAdmin]
#     filter_backends = [filters.SearchFilter]
#     search_fields = ['username', 'email']

#     def get_queryset(self):
#         queryset = super().get_queryset()
#         role = self.request.query_params.get('role')
#         status = self.request.query_params.get('status')
#         if role and role.lower() != 'all':
#             queryset = queryset.filter(role__iexact=role)
#         if status and status.lower() != 'all':
#             queryset = queryset.filter(status__iexact=status)
#         return queryset

# @api_view(['GET'])
# def get_filter_choices(request):
#     return Response({
#         "roles": ["all", "talent", "employer", "admin"],
#         "statuses": ["all", "active", "pending", "suspended"]
#     })


from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from datetime import datetime
from collections import Counter
import json
 
from .serializers import (
    TopInstitutionSerializer,
    LanguageFitSerializer,
    CulturalAdaptationSerializer,
    RegionalPerformanceSerializer,
    SkillsDemandSerializer
)
 
class AdminAnalyticsDashboardAPIView(APIView):
    def get(self, request):
        current_year = datetime.now().year
        resume_table = "talent_management_resume"
        application_table = "employer_management_application"
 
        # ------------------ Total AI Talent ------------------
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM talent_management_customuser 
                WHERE user_role = 'TALENT'
            """)
            total_ai_talent = cursor.fetchone()[0]
 
        # ------------------ Active Placements ------------------
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM {application_table}
                WHERE status = 'HIRED'
            """)
            active_placements = cursor.fetchone()[0]
 
        # ------------------ Global Employers ------------------
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM talent_management_customuser
                WHERE user_role = 'EMPLOYER'
            """)
            global_employers = cursor.fetchone()[0]
 
        # ------------------ Top Performing Institutions ------------------
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT 
                    CASE
                        WHEN degree_institution_name IS NOT NULL AND degree_institution_name != '' 
                            THEN degree_institution_name
                        WHEN diploma_institution_name IS NOT NULL AND diploma_institution_name != '' 
                            THEN diploma_institution_name
                        ELSE NULL
                    END AS institution_name,
                    COUNT(*) AS graduates
                FROM {resume_table}
                WHERE 
                    (
                        (degree_year_passing IS NOT NULL AND degree_year_passing != '' 
                         AND CAST(degree_year_passing AS UNSIGNED) <= {current_year})
                        OR
                        (diploma_year_passing IS NOT NULL AND diploma_year_passing != '' 
                         AND CAST(diploma_year_passing AS UNSIGNED) <= {current_year})
                    )
                GROUP BY institution_name
            """)
            graduates_data = cursor.fetchall()
 
        institution_list = []
        total_graduates_all = 0
        total_placements_all = 0
 
        for institution_name, graduates_count in graduates_data:
            total_graduates_all += graduates_count
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT COUNT(*)
                    FROM {application_table} e
                    JOIN {resume_table} r ON r.talent_id_id = e.talent_id
                    WHERE e.status = 'HIRED'
                    AND (
                        r.degree_institution_name = %s OR 
                        r.diploma_institution_name = %s
                    )
                """, [institution_name, institution_name])
                placements_count = cursor.fetchone()[0]
                total_placements_all += placements_count
 
            success_rate = (placements_count / graduates_count) * 100 if graduates_count else 0
            institution_list.append({
                "institution_name": institution_name,
                "graduates": graduates_count,
                "placements": placements_count,
                "success_rate": round(success_rate, 2)
            })
 
        # ------------------ Language Fit ------------------
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT languages FROM {resume_table}")
            lang_rows = cursor.fetchall()
 
        lang_counter = Counter()
        for (lang_json,) in lang_rows:
            if lang_json:
                try:
                    langs = json.loads(lang_json)
                    if isinstance(langs, list):
                        lang_counter.update(langs)
                except:
                    pass
        language_list = [{"language": k, "count": v} for k, v in lang_counter.most_common(10)]
 
        # ------------------ Cultural Adaptation ------------------
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT current_country, COUNT(*) as graduates
                FROM {resume_table}
                GROUP BY current_country
            """)
            country_rows = cursor.fetchall()
 
        cultural_list = []
        for country, graduates_count in country_rows:
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT COUNT(*)
                    FROM {application_table} e
                    JOIN {resume_table} r ON r.talent_id_id = e.talent_id
                    WHERE e.status = 'HIRED' AND r.current_country = %s
                """, [country])
                placements_count = cursor.fetchone()[0]
 
            success_rate = (placements_count / graduates_count) * 100 if graduates_count else 0
            cultural_list.append({
                "country": country,
                "success_rate": round(success_rate, 2)
            })
 
        # ------------------ Regional Performance ------------------
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT current_state, COUNT(*) as graduates
                FROM {resume_table}
                WHERE 
                    (
                        (degree_year_passing IS NOT NULL AND degree_year_passing != '' 
                         AND CAST(degree_year_passing AS UNSIGNED) <= {current_year})
                        OR
                        (diploma_year_passing IS NOT NULL AND diploma_year_passing != '' 
                         AND CAST(diploma_year_passing AS UNSIGNED) <= {current_year})
                    )
                GROUP BY current_state
            """)
            state_rows = cursor.fetchall()
 
        regional_list = []
        for state, graduates_count in state_rows:
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT COUNT(*)
                    FROM {application_table} e
                    JOIN {resume_table} r ON r.talent_id_id = e.talent_id
                    WHERE e.status = 'HIRED' AND r.current_state = %s
                """, [state])
                placements_count = cursor.fetchone()[0]
 
            success_rate = (placements_count / graduates_count) * 100 if graduates_count else 0
            regional_list.append({
                "state": state,
                "graduates": graduates_count,
                "placements": placements_count,
                "success_rate": round(success_rate, 2)
            })
 
        # ------------------ Skills in High Demand ------------------
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT skills FROM {resume_table}")
            skill_rows = cursor.fetchall()
 
        skill_counter = Counter()
        for (skills,) in skill_rows:
            if skills:
                try:
                    skill_list = json.loads(skills) if skills.strip().startswith("[") else [s.strip() for s in skills.split(",")]
                    skill_counter.update(skill_list)
                except:
                    pass
        skills_list = [{"skill": k, "count": v} for k, v in skill_counter.most_common(10)]
 
        # ------------------ Final Response ------------------
        success_rate_total = (total_placements_all / total_graduates_all) * 100 if total_graduates_all else 0
 
        return Response({
            "total_ai_talent": total_ai_talent,
            "active_placements": active_placements,
            "global_employers": global_employers,
            "success_rate": round(success_rate_total, 2),
            "avg_days_to_place": 45,
            "top_institutions": TopInstitutionSerializer(institution_list, many=True).data,
            "language_fit": LanguageFitSerializer(language_list, many=True).data,
            "cultural_adaptation": CulturalAdaptationSerializer(cultural_list, many=True).data,
            "regional_performance": RegionalPerformanceSerializer(regional_list, many=True).data,
            "skills_demand": SkillsDemandSerializer(skills_list, many=True).data
        })