 #admin_management/views.py

from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from collections import Counter, defaultdict
import json
from django.db.models import Count, Q, Avg, F
from django.utils.timesince import timesince

from talent_management.models import CustomUser, UserRole, Resume
from employer_management.models import JobPosting, Application, ApplicationStatus, Interview, InterviewStatus

from .models import SystemHealthStatus
from .serializers import (
    UserDashboardSerializer,
    SystemHealthStatusModelSerializer,
    GlobalDashboardOverviewSerializer
)


# --- DashboardSummaryAPIView and UserDashboardAPIView remain unchanged ---
# (You can copy them from your original file)
class DashboardSummaryAPIView(APIView):
    # Your existing code for this view
    pass

class UserDashboardAPIView(APIView):
    # Your existing code for this view
    pass


# --- NEW: ViewSet for managing SystemHealthStatus ---
class SystemHealthStatusViewSet(viewsets.ModelViewSet):
    """
    API endpoint for CRUD operations on SystemHealthStatus.
    Accessible only by admins.
    """
    queryset = SystemHealthStatus.objects.all().order_by('service_name')
    serializer_class = SystemHealthStatusModelSerializer
    permission_classes = [permissions.IsAdminUser] # Use Django's built-in admin permission


# --- REWRITTEN: The main dynamic analytics dashboard view ---
class GlobalDashboardOverviewAPIView(APIView):
    """
    Provides a fully dynamic, data-driven overview for the Global AI Talent Export Dashboard.
    """
 #   permission_classes = [permissions.IsAdminUser]

    def _calculate_growth(self, current_period_count, prev_period_count):
        if prev_period_count > 0:
            return round(((current_period_count - prev_period_count) / prev_period_count) * 100, 1)
        return 100.0 if current_period_count > 0 else 0.0

    def get(self, request):
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        last_month_end = this_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        # 1. --- CORE METRICS ---
        talent_qs = CustomUser.objects.filter(user_role=UserRole.TALENT)
        employer_qs = CustomUser.objects.filter(user_role=UserRole.EMPLOYER)
        hired_app_qs = Application.objects.filter(status=ApplicationStatus.HIRED)

        talent_this_month = talent_qs.filter(date_joined__date__gte=this_month_start).count()
        talent_last_month = talent_qs.filter(date_joined__date__range=(last_month_start, last_month_end)).count()
        
        employers_this_month = employer_qs.filter(date_joined__date__gte=this_month_start).count()
        employers_last_month = employer_qs.filter(date_joined__date__range=(last_month_start, last_month_end)).count()

        placements_this_month = hired_app_qs.filter(updated_at__date__gte=this_month_start).count()
        placements_last_month = hired_app_qs.filter(updated_at__date__range=(last_month_start, last_month_end)).count()

        # 2. --- TOP PERFORMING INSTITUTIONS ---
        institution_stats = defaultdict(lambda: {'graduates': 0, 'placements': 0})
        all_resumes = Resume.objects.filter(is_deleted=False).prefetch_related('talent_id__applications')

        for resume in all_resumes:
            # Consolidate degree and diploma details
            education_details = []
            if isinstance(resume.degree_details, list):
                education_details.extend(resume.degree_details)
            if isinstance(resume.diploma_details, list):
                education_details.extend(resume.diploma_details)
            
            processed_institutions = set() # To count a graduate only once per resume
            for edu in education_details:
                # Handle inconsistent keys ('institution_name')
                inst_name = edu.get('institution_name', '').strip()
                if inst_name and inst_name not in processed_institutions:
                    institution_stats[inst_name]['graduates'] += 1
                    processed_institutions.add(inst_name)
        
        # Correlate with placements
        hired_resumes = Resume.objects.filter(talent_id__applications__status=ApplicationStatus.HIRED, is_deleted=False).distinct()
        for resume in hired_resumes:
            education_details = (resume.degree_details or []) + (resume.diploma_details or [])
            processed_placement_institutions = set()
            for edu in education_details:
                inst_name = edu.get('institution_name', '').strip()
                if inst_name and inst_name not in processed_placement_institutions:
                    institution_stats[inst_name]['placements'] += 1
                    processed_placement_institutions.add(inst_name)

        top_institutions = sorted(
            [
                {
                    'institution': name,
                    'graduates': data['graduates'],
                    'placements': data['placements'],
                    'success_rate': round((data['placements'] / data['graduates']) * 100, 1) if data['graduates'] > 0 else 0.0,
                }
                for name, data in institution_stats.items() if data['graduates'] > 0
            ],
            key=lambda x: x['placements'],
            reverse=True
        )[:10] # Top 10

        # 3. --- SKILLS IN HIGH DEMAND ---
        skill_counts = Counter()
        hired_resumes_with_skills = hired_resumes.exclude(skills__isnull=True).exclude(skills__exact='')
        for resume in hired_resumes_with_skills:
            try:
                # Handles both JSON array string '["Python", "Django"]' and simple CSV "Python,Django"
                skills_list = json.loads(resume.skills) if resume.skills.strip().startswith('[') else [s.strip() for s in resume.skills.split(',')]
                skill_counts.update(s.title() for s in skills_list if s)
            except (json.JSONDecodeError, AttributeError):
                continue # Skip malformed skill entries

        top_skills = [
            {'skill': skill, 'placements': count, 'growth': 0.0} # Growth calculation is complex, keeping as placeholder
            for skill, count in skill_counts.most_common(10)
        ]
        
        # 4. --- REGIONAL PERFORMANCE ---
        regional_placements = hired_app_qs.values('job_posting__location').annotate(total=Count('id')).order_by('-total')
        regional_performance_data = []
        for region in regional_placements:
            location = region['job_posting__location']
            if not location: continue

            this_month = hired_app_qs.filter(job_posting__location=location, updated_at__date__gte=this_month_start).count()
            last_month = hired_app_qs.filter(job_posting__location=location, updated_at__date__range=(last_month_start, last_month_end)).count()
            growth = self._calculate_growth(this_month, last_month)
            
            regional_performance_data.append({
                'region': location,
                'placements': region['total'],
                'growth': growth,
                'status': 'Active' if growth > 5 else ('Declining' if growth < -5 else 'Stable')
            })

        # 5. --- RECENT ACTIVITY ---
        recent_users = CustomUser.objects.order_by('-date_joined')[:3]
        recent_placements = hired_app_qs.select_related('talent', 'job_posting').order_by('-updated_at')[:3]
        recent_jobs = JobPosting.objects.select_related('company').order_by('-posted_date')[:3]
        
        activities = []
        for user in recent_users:
            activities.append({'type': 'Registration', 'desc': f"New {user.get_user_role_display()} '{user.username}' signed up.", 'time': user.date_joined})
        for app in recent_placements:
            activities.append({'type': 'Placement', 'desc': f"'{app.talent.username}' was hired for '{app.job_posting.title}'.", 'time': app.updated_at})
        for job in recent_jobs:
            activities.append({'type': 'Job Posting', 'desc': f"'{job.company.company_name}' posted '{job.title}'.", 'time': job.posted_date})

        recent_activity_list = sorted(activities, key=lambda x: x['time'], reverse=True)[:5]
        recent_system_activity = [
            {'type': item['type'], 'description': item['desc'], 'time_ago': timesince(item['time'])}
            for item in recent_activity_list
        ]
        
        # 6. --- KPIs ---
        total_talent = talent_qs.count()
        talent_with_resumes = Resume.objects.filter(is_deleted=False).values_list('talent_id', flat=True).distinct().count()
        
        total_interviews = Interview.objects.count()
        completed_interviews = Interview.objects.filter(interview_status=InterviewStatus.COMPLETED).count()

        placement_time_agg = hired_app_qs.annotate(
            time_diff=F('updated_at') - F('job_posting__posted_date')
        ).aggregate(avg_time=Avg('time_diff'))
        avg_placement_days = placement_time_agg['avg_time'].days if placement_time_agg['avg_time'] else 0.0

        # --- FINAL RESPONSE ASSEMBLY ---
        response_data = {
            "registered_ai_talent": {
                "count": total_talent,
                "growth_percent": self._calculate_growth(talent_this_month, talent_last_month)
            },
            "global_employers": {
                "count": employer_qs.count(),
                "growth_percent": self._calculate_growth(employers_this_month, employers_last_month)
            },
            "active_placements": {
                "count": placements_this_month,
                "growth_percent": self._calculate_growth(placements_this_month, placements_last_month)
            },
            "total_placements": hired_app_qs.count(),
            "regional_performance": regional_performance_data[:10],
            "skills_in_high_demand": top_skills,
            "top_performing_institutions": top_institutions,
            "system_health": SystemHealthStatusModelSerializer(SystemHealthStatus.objects.all(), many=True).data,
            "recent_system_activity": recent_system_activity,
            "key_performance_indicators": {
                "profile_completion_rate": round((talent_with_resumes / total_talent) * 100, 1) if total_talent > 0 else 0.0,
                "interview_success_rate": round((completed_interviews / total_interviews) * 100, 1) if total_interviews > 0 else 0.0,
                "average_placement_time_days": round(avg_placement_days, 1),
                "employer_satisfaction_rate": 92.5 # Placeholder - requires a feedback model
            }
        }
        
        # Validate and return
        serializer = GlobalDashboardOverviewSerializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)
    






    
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



class AnalyticsCountAPIView(APIView):
    """
    API: /api/admin/analytics-count/
    Fetches overall analytics counts from gatep_platform_db
    """
 
    def get(self, request):
        data = {}
 
        with connection.cursor() as cursor:
            #  Total AI Talent Count
            cursor.execute("""
                SELECT COUNT(*) 
                FROM talent_management_customuser 
                WHERE user_role = 'TALENT';
            """)
            data['total_ai_talent'] = cursor.fetchone()[0]
 
            # Global Employer Count
            cursor.execute("""
                SELECT COUNT(*) 
                FROM talent_management_customuser 
                WHERE user_role = 'EMPLOYER';
            """)
            data['global_employer_count'] = cursor.fetchone()[0]
 
            #  Active Placements Count (HIRED)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM employer_management_application 
                WHERE status = 'HIRED';
            """)
            hired_count = cursor.fetchone()[0]
            data['active_placements'] = hired_count
 
            #  Total Applications Count
            cursor.execute("""
                SELECT COUNT(*) 
                FROM employer_management_application;
            """)
            total_applications = cursor.fetchone()[0]
 
            # Success Rate Calculation
            if total_applications > 0:
                data['success_rate'] = round((hired_count / total_applications) * 100, 2)
            else:
                data['success_rate'] = 0.0
 
            #  Average Days to Place
            cursor.execute("""
                SELECT AVG(DATEDIFF(updated_at, created_at)) 
                FROM employer_management_application 
                WHERE status = 'HIRED';
            """)
            avg_days = cursor.fetchone()[0]
            data['average_days_to_place'] = round(avg_days, 2) if avg_days else 0.0
 
        return Response(data)
    

    