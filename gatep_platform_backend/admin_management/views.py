
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
    Provides overview statistics for the Global AI Talent Export Dashboard,
    including summary cards, quick actions, recent activity, system health, and KPIs.
    Requires authentication (temporarily for debugging).
    """
    permission_classes = [permissions.IsAuthenticated] 

    def get(self, request):
        print(f"\n--- DEBUGGING GlobalDashboardOverviewAPIView GET ---")
        print(f"DEBUG: Request user: {request.user}")
        print(f"DEBUG: User is authenticated: {request.user.is_authenticated}")
        print(f"DEBUG: User is staff (is_admin): {request.user.is_staff}")
        print(f"DEBUG: User is superuser: {request.user.is_superuser}")
        print(f"DEBUG: User ID: {getattr(request.user, 'id', 'N/A')}")
        print(f"--- END DEBUGGING ---\n")
        # --- END DEBUGGING PRINTS ---

        # Time reference for growth calculations (e.g., "this month" vs "last month")
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)

        # --- Helper for growth calculation ---
        def calculate_growth(current_count, previous_count):
            if previous_count > 0:
                return ((current_count - previous_count) / previous_count) * 100
            return 0 # Or handle as 'N/A' if you prefer for 0 previous count

        # --- Registered AI Talent ---
        # AI keywords for identifying AI talent based on resume skills
        ai_keywords = ['AI', 'Artificial Intelligence', 'Machine Learning', 'Deep Learning', 'NLP', 'Computer Vision', 'Data Science']
        
        # Optimized AI talent count: Filter CustomUser first, then check related Resume skills
        def get_ai_talent_count_optimized(start_date=None, end_date=None):
            talent_users_qs = CustomUser.objects.filter(user_role=UserRole.TALENT)
            
            if start_date:
                talent_users_qs = talent_users_qs.filter(date_joined__date__gte=start_date)
            if end_date:
                talent_users_qs = talent_users_qs.filter(date_joined__date__lte=end_date)
            
            # Filter these talent users to only include those with resumes
            # and where their resume skills contain any of the AI keywords.
            # Using Q objects for OR logic in skills contains check.
            # from django.db.models import Q # Already imported at the top now

            ai_skill_conditions = Q()
            for keyword in ai_keywords:
                ai_skill_conditions |= Q(resumes__skills__icontains=keyword)
            
            # Ensure we only count distinct users, as a user might have multiple resumes or multiple skill matches
            return talent_users_qs.filter(ai_skill_conditions).distinct().count()


        registered_ai_talent_this_month = get_ai_talent_count_optimized(start_date=this_month_start, end_date=today)
        registered_ai_talent_last_month = get_ai_talent_count_optimized(start_date=last_month_start, end_date=last_month_end)
        total_registered_ai_talent = get_ai_talent_count_optimized() # All time
        registered_ai_talent_growth = calculate_growth(registered_ai_talent_this_month, registered_ai_talent_last_month)


        # --- Global Employers ---
        def get_employer_count(start_date=None, end_date=None):
            qs = CustomUser.objects.filter(user_role=UserRole.EMPLOYER)
            if start_date:
                qs = qs.filter(date_joined__date__gte=start_date)
            if end_date:
                qs = qs.filter(date_joined__date__lte=end_date)
            return qs.count()

        global_employers_this_month = get_employer_count(start_date=this_month_start, end_date=today)
        global_employers_last_month = get_employer_count(start_date=last_month_start, end_date=last_month_end)
        total_global_employers = get_employer_count() # All time
        global_employers_growth = calculate_growth(global_employers_this_month, global_employers_last_month)


        # --- Active Placements & Total Placements ---
        # Note: 'Active Placements' in your dashboard refers to 'this month's placements'.
        # 'Total Placements' is 'all time hired applications'.
        def get_placements_count(status_filter=ApplicationStatus.HIRED, start_date=None, end_date=None):
            qs = Application.objects.filter(status=status_filter)
            if start_date:
                qs = qs.filter(application_date__date__gte=start_date)
            if end_date:
                qs = qs.filter(application_date__date__lte=end_date)
            return qs.count()

        active_placements_this_month = get_placements_count(start_date=this_month_start, end_date=today)
        active_placements_last_month = get_placements_count(start_date=last_month_start, end_date=last_month_end)
        total_placements = get_placements_count() # All time hired applications
        active_placements_growth = calculate_growth(active_placements_this_month, active_placements_last_month)

        # --- Regional Performance ---
        # Filter hired applications only
        hired_applications_qs = Application.objects.filter(status=ApplicationStatus.HIRED)

        regional_placements_raw = hired_applications_qs.values(
            'job_posting__location'
        ).annotate(
            placements=Count('id')
        ).order_by('-placements')

        regional_performance_data = []
        for entry in regional_placements_raw:
            region = entry['job_posting__location']
            placements = entry['placements'] # Total placements for this region

            # Placements this month for the region
            region_hired_this_month = hired_applications_qs.filter(
                job_posting__location=region,
                application_date__date__gte=this_month_start,
                application_date__date__lte=today
            ).count()

            # Placements last month for the region
            region_hired_last_month = hired_applications_qs.filter(
                job_posting__location=region,
                application_date__date__gte=last_month_start,
                application_date__date__lte=last_month_end
            ).count()

            region_growth_percent = calculate_growth(region_hired_this_month, region_hired_last_month)
            
            status_text = "Stable"
            if region_hired_this_month > region_hired_last_month:
                status_text = "Active"
            elif region_hired_this_month < region_hired_last_month and region_hired_last_month > 0:
                status_text = "Declining"
            # If both are 0 or equal, it remains "Stable"

            regional_performance_data.append({
                "region": region,
                "placements": placements,
                "growth": f"{region_growth_percent:.0f}%",
                "status": status_text
            })

        # --- Recent System Activity ---
        recent_activities_list = []
        
        def get_time_ago_string(dt):
            # dt can be a datetime object (from date_joined, scheduled_at)
            # or a date object (from application_date.date())
            # For simplicity, convert all to datetime for calculation with timezone.now()
            if isinstance(dt, timezone.datetime):
                time_diff = timezone.now() - dt
            elif isinstance(dt, timezone.date):
                # Convert date to datetime at start of day
                time_diff = timezone.now() - timezone.make_aware(timezone.datetime.combine(dt, timezone.datetime.min.time()))
            else:
                return "N/A" # Should not happen with proper model fields

            if time_diff.days > 0:
                return f"{time_diff.days} {'day' if time_diff.days == 1 else 'days'} ago"
            elif time_diff.seconds >= 3600:
                hours = time_diff.seconds // 3600
                return f"{hours} {'hour' if hours == 1 else 'hours'} ago"
            elif time_diff.seconds >= 60:
                minutes = time_diff.seconds // 60
                return f"{minutes} {'minute' if minutes == 1 else 'minutes'} ago"
            else:
                return "just now"

        # Recent Placements
        # Order by application_date descending, get latest 2
        recent_placements_qs = Application.objects.filter(
            status=ApplicationStatus.HIRED
        ).select_related('talent', 'job_posting').order_by('-application_date')[:2]

        for app in recent_placements_qs:
            recent_activities_list.append({
                "type": "Placement",
                "description": f"{app.talent.username} placed for {app.job_posting.title} in {app.job_posting.location or 'Unknown'}",
                "time_ago": int(app.application_date.timestamp())
            })

        # Recent Registrations
        # Order by date_joined descending, get latest 2 users (talent or employer)
        recent_registrations_qs = CustomUser.objects.order_by('-date_joined')[:2]
        for user in recent_registrations_qs:
            # Ensure user.user_role is a string that can be used directly as a label
            role_label = user.get_user_role_display() if hasattr(user, 'get_user_role_display') else user.user_role
            recent_activities_list.append({
                "type": "Registration",
                "description": f"New {role_label} from {getattr(user, 'location', 'Unknown')} registered", # Assuming CustomUser might have a location field
                "time_ago": get_time_ago_string(user.date_joined)
            })
        
        # Recent Verification (Example: Count recently verified resumes)
        # Assuming `updated_at` on Resume is modified when `document_verification` changes
        recently_verified_count = Resume.objects.filter(
            document_verification='VERIFIED',
            updated_at__gte=timezone.now() - timedelta(days=7) # Verified in the last 7 days
        ).count()
        recent_activities_list.append({
            "type": "Verification",
            "description": f"{recently_verified_count} talent profiles verified via DigiLocker",
            "time_ago": "recently" # Or refine based on average verification time if available
        })

        # Recent Interviews
        # Filter interviews scheduled in the past week (or future interviews scheduled within a week from now)
        recent_interviews_qs = Interview.objects.filter(
            scheduled_at__gte=timezone.now() - timedelta(days=7) # Interviews within the last 7 days
        ).select_related('application__talent', 'application__job_posting').order_by('-scheduled_at')[:2]

        for interview in recent_interviews_qs:
            recent_activities_list.append({
                "type": "Interview",
                "description": f"Interview scheduled for {interview.application.talent.username} for {interview.application.job_posting.title}",
                "time_ago": get_time_ago_string(interview.scheduled_at)
            })

        # --- System Health (Now dynamic from SystemHealthStatus model) ---
        system_health_data = []
        db_health_statuses = SystemHealthStatus.objects.all().order_by('service_name') # Fetch all
        
        # Map DB statuses for quick lookup
        system_health_map = {s.service_name: s.status for s in db_health_statuses}

        # Define expected services and their default statuses if not found in DB
        # Use the ServiceStatusChoices for consistency
        expected_services_definitions = [
            {"service": "Aadhaar Integration", "default_status": SystemHealthStatus.ServiceStatusChoices.ONLINE},
            {"service": "DigiLocker API", "default_status": SystemHealthStatus.ServiceStatusChoices.ONLINE},
            {"service": "NSDC Integration", "default_status": SystemHealthStatus.ServiceStatusChoices.ONLINE},
            {"service": "MEA Services", "default_status": SystemHealthStatus.ServiceStatusChoices.MAINTENANCE},
            {"service": "Notification Service", "default_status": SystemHealthStatus.ServiceStatusChoices.ONLINE},
        ]
        
        for service_info in expected_services_definitions:
            service_name = service_info["service"]
            # Get status from DB, fallback to default if not in DB
            current_status = system_health_map.get(service_name, service_info["default_status"])
            system_health_data.append({
                "service": service_name,
                "status": current_status # This will be the TextChoices value (e.g., 'Online')
            })


        # --- Key Performance Indicators (KPIs) ---
        # Profile Completion (Average for Talent Users)
        # Assuming TalentProfile.profile_completion_percentage is a calculated property or a field
        # For now, let's calculate based on a simplified "completeness" if `profile_completion_percentage` is not a field.
        # If it's a field you add, you can use:
        # avg_profile_completion_raw = TalentProfile.objects.aggregate(avg_completion=Avg('profile_completion_percentage'))

        # To simulate profile completion for demonstration, if not a field:
        # This is a very rough simulation. A real implementation would check mandatory fields.
        total_talent_profiles = TalentProfile.objects.count()
        if total_talent_profiles > 0:
            # Placeholder/mock for actual calculation.
            # In a real scenario, you'd iterate or use annotations if you define completeness logic.
            # For demonstration, let's just make a plausible average or fetch from a field if added.
            # If TalentProfile had a `profile_completion_percentage` field:
            # avg_completion_value = TalentProfile.objects.aggregate(avg=Avg('user__talentprofile__profile_completion_percentage'))['avg']
            # if avg_completion_value is None: # In case no profiles or no completion data
            #      profile_completion = "N/A"
            # else:
            #      profile_completion = f"{avg_completion_value:.0f}%"
            profile_completion = "75%" # Static placeholder
        else:
            profile_completion = "N/A"

        # Interview Success Rate
        total_interviews_count = Interview.objects.count()
        successful_interviews_count = Interview.objects.filter(interview_status=InterviewStatus.COMPLETED).count()
        interview_success_rate = (successful_interviews_count / total_interviews_count * 100) if total_interviews_count > 0 else 0

        # Average Placement Time (e.g., from application_date to hired_date)
        # This requires storing the 'hired_date' or last status change date on the Application model.
        # If Application had a `hired_at` DateTimeField, you'd calculate:
        # avg_time = Application.objects.filter(status=ApplicationStatus.HIRED, hired_at__isnull=False).annotate(
        #     time_to_hire=F('hired_at') - F('application_date')
        # ).aggregate(avg_delta=Avg('time_to_hire'))['avg_delta']
        # if avg_time:
        #     average_placement_time = f"{avg_time.days} Days"
        # else:
        #     average_placement_time = "N/A"
        average_placement_time = "30 Days" # Still a placeholder based on your models

        # Employer Satisfaction (Requires a survey/rating system, placeholder)
        # If you add an EmployerFeedback model, you'd calculate:
        # avg_satisfaction = EmployerFeedback.objects.aggregate(avg=Avg('rating'))['avg']
        # employer_satisfaction = f"{avg_satisfaction * 20:.0f}%" if avg_satisfaction else "N/A" # assuming 1-5 rating -> %
        employer_satisfaction = "92%" # Still a placeholder

        # Prepare the final response data dictionary
        response_data = {
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
            "quick_actions": [
                {"label": "VIEW ANALYTICS", "link": "/analytics/"},
                {"label": "MANAGE USERS", "link": "/analytics/users/"},
                {"label": "SYSTEM SETTINGS", "link": "/settings/"}
            ],
            "regional_performance": regional_performance_data,

            "recent_system_activity": recent_activities_list,
            "system_health": system_health_data,
            "key_performance_indicators": {
                "profile_completion": profile_completion,
                "interview_success_rate": f"{interview_success_rate:.0f}%",
                "average_placement_time": average_placement_time,
                "employer_satisfaction": employer_satisfaction
            }
        }

        # Use the serializer to validate and format the output
        serializer = GlobalDashboardOverviewSerializer(data=response_data)
        serializer.is_valid(raise_exception=True) 
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
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
