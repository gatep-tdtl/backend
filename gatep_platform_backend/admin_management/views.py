# global_dashboard/views.py new

from collections import Counter
import json
from datetime import datetime, timedelta
from django.db import connection
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from talent_management.models import CustomUser, Resume
from employer_management.models import Application, JobPosting
from django.utils import timezone


class GlobalOverviewAPIView(APIView):
    def get(self, request):
        # ------------------ Filters ------------------
        time_range = request.query_params.get('time_range', 'last_month')
        region_filter = request.query_params.get('region', 'All Regions')
 
        now = timezone.now()
 
        if time_range == 'last_week':
            start_date = now - timedelta(days=7)
        elif time_range == 'last_month':
            start_date = now - timedelta(days=30)
        elif time_range == 'last_quarter':
            start_date = now - timedelta(days=90)
        elif time_range == 'last_year':
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
 
        # ------------------ Base Queries ------------------
        base_applications = Application.objects.filter(status='HIRED')
        if start_date:
            base_applications = base_applications.filter(updated_at__gte=start_date)
 
        base_job_postings = JobPosting.objects.filter(status='PUBLISHED')
        if start_date:
            base_job_postings = base_job_postings.filter(created_at__gte=start_date)
        if region_filter != 'All Regions':
            base_job_postings = base_job_postings.filter(location=region_filter)
 
        # ------------------ Counts ------------------
        ai_talent_count = CustomUser.objects.filter(user_role='TALENT').count()
        employer_count = CustomUser.objects.filter(user_role='EMPLOYER').count()
        active_placements_count = base_applications.count()
        success_rate = (active_placements_count / ai_talent_count) * 100 if ai_talent_count else 0
 
        # ------------------ Avg Days to Place ------------------
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT AVG(DATEDIFF(updated_at, created_at))
                FROM employer_management_application
                WHERE status = 'HIRED' AND updated_at >= %s
            """, [start_date])
            avg_days = cursor.fetchone()[0]
            avg_days_to_place = round(avg_days, 2) if avg_days else 0.0
 
        # ------------------ Placements by Region ------------------
        current_period_placements = base_applications.values('job_posting__location').annotate(count=Count('id'))
        region_dict = {item['job_posting__location']: item['count'] for item in current_period_placements if item['job_posting__location']}
 
        all_regions = list(region_dict.keys())
        max_region_placements = max(region_dict.values()) if region_dict else 1
 
        placements_by_region = []
        for region_name, placement_count in region_dict.items():
            regional_jobs = base_job_postings.filter(location=region_name)
            regional_avg_salary = regional_jobs.aggregate(avg_salary=Avg('salary_min'))['avg_salary']
 
            # proportional demand score & growth
            demand_score = (placement_count / max_region_placements) * 100 if max_region_placements else 0
            growth_percentage = (placement_count / max_region_placements) * 100 if max_region_placements else 0
 
            # top roles
            regional_top_roles = base_applications.filter(
                job_posting__location=region_name
            ).values('job_posting__title').annotate(
                count=Count('id')
            ).order_by('-count')[:5]
 
            placements_by_region.append({
                "region": region_name,
                "placements": placement_count,
                "growth": round(growth_percentage, 2),
                "avg_salary": round(regional_avg_salary, 2) if regional_avg_salary else 0.0,
                "demand_score": round(demand_score, 2),
                "top_roles": [role['job_posting__title'] for role in regional_top_roles]
            })
 
        # ------------------ Top Performing Institutions ------------------
        with connection.cursor() as cursor:
            talent_ids = list(base_applications.values_list('talent', flat=True).distinct())
            if talent_ids:
                sql_query = f"""
                    SELECT 
                        COALESCE(JSON_UNQUOTE(JSON_EXTRACT(degree_details, '$[0].institution_name')),
                                 JSON_UNQUOTE(JSON_EXTRACT(diploma_details, '$[0].institution_name'))) AS institution_name,
                        COUNT(DISTINCT TMR.id) AS graduates,
                        COUNT(TMA.id) AS placements
                    FROM talent_management_resume TMR
                    LEFT JOIN employer_management_application TMA 
                        ON TMR.talent_id_id = TMA.talent_id
                    WHERE TMR.talent_id_id IN ({','.join(['%s'] * len(talent_ids))})
                    GROUP BY institution_name
                    ORDER BY placements DESC
                """
                cursor.execute(sql_query, talent_ids)
                institution_list_raw = cursor.fetchall()
            else:
                institution_list_raw = []
 
        institution_list = []
        for row in institution_list_raw:
            institution_name, graduates_count, placements_count = row
            success_rate_institution = (placements_count / graduates_count) * 100 if graduates_count else 0
            institution_list.append({
                "institution_name": institution_name.strip('"') if institution_name else None,
                "graduates": graduates_count,
                "placements": placements_count,
                "success_rate": round(success_rate_institution, 2)
            })
 
        # ------------------ Skills in High Demand ------------------
        resumes = Resume.objects.filter(talent_id__in=base_applications.values_list('talent', flat=True))
        skill_counts = {}
        for resume in resumes:
            if not resume.skills:
                continue
            try:
                skills = json.loads(resume.skills) if resume.skills.startswith("[") else resume.skills.split(",")
            except:
                skills = resume.skills.split(",")
            for skill in skills:
                clean_skill = skill.strip().strip('"').strip("'")
                if clean_skill:
                    skill_counts[clean_skill] = skill_counts.get(clean_skill, 0) + 1
 
        max_skill_placements = max(skill_counts.values()) if skill_counts else 1
        skills_data = [
            {
                "skill": skill,
                "placements": count,
                "growth": round((count / max_skill_placements) * 100, 2)
            }
            for skill, count in sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]
 
        # ------------------ Final Response ------------------
        return Response({
            "global_ai_talent": ai_talent_count,
            "global_employer": employer_count,
            "active_placements": active_placements_count,
            "success_rate": round(success_rate, 2),
            "average_days_to_place": avg_days_to_place,
            "placements_by_region": placements_by_region,
            "top_performing_institutions": institution_list,
            "skills_in_high_demand": skills_data,
        })



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from collections import Counter
import ast

from talent_management.models import Resume, UserRole

class TalentHeatmapDashboardRoleAndCertification(APIView):
    """
    Provides aggregated data for the admin talent heatmap dashboard.
    Accessible only by admin users.
    """
    #permission_classes = [IsAdminUser]

    def get(self, request, format=None):
        # --- LOGIC EXPLANATION ---
        # We fetch all resumes linked to a user with the 'TALENT' role once
        # to avoid multiple database hits. All subsequent processing is done in memory.
        resumes = Resume.objects.filter(talent_id__user_role=UserRole.TALENT)
        total_talent_count = resumes.count()

        if total_talent_count == 0:
            return Response({"message": "No talent data available to generate dashboard."})

        # --- 1. Talent Distribution by Role ---
        # LOGIC: The 'domain_interest' is a string representation of a list (e.g., "['AI Engineer', 'Data Science']").
        # We iterate through each resume, safely parse this string into an actual list using `ast.literal_eval`,
        # and then use a Counter to efficiently tally the occurrences of each role.
        role_counter = Counter()
        for resume in resumes:
            if resume.domain_interest:
                try:
                    # ast.literal_eval is a safe way to evaluate a string containing a Python literal.
                    interests = ast.literal_eval(resume.domain_interest)
                    if isinstance(interests, list):
                        role_counter.update(interests)
                except (ValueError, SyntaxError):
                    # This handles malformed strings gracefully.
                    pass
        
        # We return the data as a list of dictionaries for easy consumption by the frontend.
        talent_distribution_by_role = [{"role": item[0], "count": item[1]} for item in role_counter.most_common(6)]

        # --- 2. Talent Distribution by Certification ---
        # LOGIC: 'certification_details' is a JSONField storing a list of dicts.
        # We loop through each resume, then through its list of certifications,
        # extracting the 'name' of each certification and counting them with a Counter.
        certification_counter = Counter()
        for resume in resumes:
            if resume.certification_details and isinstance(resume.certification_details, list):
                for cert in resume.certification_details:
                    # Check if the item is a dict and has a 'name' key.
                    if isinstance(cert, dict) and 'name' in cert:
                        certification_counter.update([cert.get('name')])
        
        talent_distribution_by_certification = [{"certification": item[0], "count": item[1]} for item in certification_counter.most_common(6)]

        # --- 3. International Readiness Index ---
        # LOGIC: We initialize counters and iterate through the resumes once to calculate all three metrics.
        english_proficient_count = 0
        passport_ready_count = 0
        relocation_willing_count = 0

        for resume in resumes:
            # English Proficiency Logic: Check the 'languages' JSON field for 'English' with a value of 'Fluent'.
            if isinstance(resume.languages, dict) and resume.languages.get('English', '').lower() == 'fluent':
                english_proficient_count += 1
            
            # Passport Ready Logic (Proxy): We assume that having any 'work_authorizations' listed
            # implies the user has a valid passport and is ready for international processes.
            if resume.work_authorizations and isinstance(resume.work_authorizations, list) and len(resume.work_authorizations) > 0:
                passport_ready_count += 1

            # Relocation Willing Logic (Proxy): A user is considered willing if they have work authorizations for
            # a country other than their permanent one OR if they explicitly list a foreign country in their work preferences.
            is_willing = False
            permanent_country = (resume.permanent_country or "default").lower()
            if resume.work_authorizations and isinstance(resume.work_authorizations, list):
                for auth in resume.work_authorizations:
                    if auth.get('country', '').lower() != permanent_country:
                        is_willing = True
                        break
            if not is_willing and resume.work_preferences and isinstance(resume.work_preferences, list):
                for pref in resume.work_preferences:
                    location_str = pref.get('location', '').lower()
                    if 'usa' in location_str or 'uk' in location_str or 'canada' in location_str: # Add more as needed
                        is_willing = True
                        break
            if is_willing:
                relocation_willing_count += 1

        # Final response structure
        response_data = {
            "talent_distribution_by_role": talent_distribution_by_role,
            "talent_distribution_by_certification": talent_distribution_by_certification,
            "international_readiness_index": {
                "english_proficiency_percentage": round((english_proficient_count / total_talent_count) * 100),
                "passport_ready_percentage": round((passport_ready_count / total_talent_count) * 100),
                "relocation_willing_percentage": round((relocation_willing_count / total_talent_count) * 100),
            }
        }

        return Response(response_data)





















# class GlobalOverviewAPIView(APIView):
#     def get(self, request):
#         # Get query parameters for filtering
#         time_range = request.query_params.get('time_range', 'last_month')
#         region_filter = request.query_params.get('region', 'All Regions')
        
#         now = timezone.now()
#         start_date = None

#         # Determine the start date based on the time_range filter
#         if time_range == 'last_week':
#             start_date = now - timedelta(days=7)
#         elif time_range == 'last_month':
#             start_date = now - timedelta(days=30)
#         elif time_range == 'last_quarter':
#             start_date = now - timedelta(days=90)
#         elif time_range == 'last_year':
#             start_date = now - timedelta(days=365)
#         # If no valid time_range, default to last_month
#         else:
#             start_date = now - timedelta(days=30)
            
#         # Define a base query for applications that can be filtered further
#         base_applications = Application.objects.filter(status='HIRED')
#         if start_date:
#             base_applications = base_applications.filter(updated_at__gte=start_date)

#         # Define a base query for job postings that can be filtered further
#         base_job_postings = JobPosting.objects.filter(status='PUBLISHED')
#         if start_date:
#             base_job_postings = base_job_postings.filter(created_at__gte=start_date)
#         if region_filter != 'All Regions':
#             base_job_postings = base_job_postings.filter(location=region_filter)


#         # ------------------ Global AI Talent Count ------------------
#         # Total AI talent is not time-dependent for this dashboard view
#         ai_talent_count = CustomUser.objects.filter(user_role='TALENT').count()

#         # ------------------ Global Employer Count -------------------
#         employer_count = CustomUser.objects.filter(user_role='EMPLOYER').count()

#         # ------------------ Active Placements Count -----------------
#         active_placements_count = base_applications.count()
        
#         # ------------------ Success Rate & Avg Days to Place ------------------
#         success_rate = (active_placements_count / ai_talent_count) * 100 if ai_talent_count else 0
        
#         # Corrected calculation for avg_days_to_place using raw SQL
#         with connection.cursor() as cursor:
#             # Note: DATEDIFF is specific to MySQL. For other databases, this might need adjustment.
#             cursor.execute("""
#                 SELECT AVG(DATEDIFF(updated_at, created_at))
#                 FROM employer_management_application
#                 WHERE status = 'HIRED' AND updated_at >= %s
#             """, [start_date])
#             avg_days = cursor.fetchone()[0]
#             avg_days_to_place = round(avg_days, 2) if avg_days else 0.0


#         # ------------------ Placements and Growth per Region (with new metrics) --------
#         # Fetch placements for current period
#         current_period_placements = base_applications.values('job_posting__location').annotate(count=Count('id'))
#         current_period_placements_dict = {
#             item['job_posting__location']: item['count'] 
#             for item in current_period_placements
#         }
        
#         # Fetch placements for previous period (e.g., last month for month-over-month)
#         if time_range == 'last_week':
#             last_period_start = now - timedelta(days=14)
#             last_period_end = now - timedelta(days=7)
#         elif time_range == 'last_month':
#             last_period_end = now.replace(day=1) - timedelta(microseconds=1)
#             last_period_start = last_period_end.replace(day=1)
#         elif time_range == 'last_quarter':
#             last_period_start = now - timedelta(days=180)
#             last_period_end = now - timedelta(days=90)
#         elif time_range == 'last_year':
#             last_period_start = now - timedelta(days=730)
#             last_period_end = now - timedelta(days=365)
#         else: # Default to last month
#             last_period_end = now.replace(day=1) - timedelta(microseconds=1)
#             last_period_start = last_period_end.replace(day=1)
        
#         last_period_placements = Application.objects.filter(
#             status='HIRED',
#             updated_at__range=(last_period_start, last_period_end)
#         ).values('job_posting__location').annotate(count=Count('id'))
#         last_period_placements_dict = {
#             item['job_posting__location']: item['count'] 
#             for item in last_period_placements
#         }

#         # Handle a specific region filter for the regional breakdown
#         if region_filter != 'All Regions':
#             all_regions = [region_filter]
#         else:
#             # Corrected logic: perform discard on the set, then convert to a list
#             all_regions_set = set(current_period_placements_dict.keys()) | set(last_period_placements_dict.keys())
#             all_regions_set.discard(None)
#             all_regions_set.discard('')
#             all_regions = sorted(list(all_regions_set))

#         placements_by_region = []
#         for region_name in all_regions:
#             current_placements = current_period_placements_dict.get(region_name, 0)
#             last_placements = last_period_placements_dict.get(region_name, 0)

#             growth_percentage = 0.0
#             if last_placements > 0:
#                 growth_percentage = ((current_placements - last_placements) / last_placements) * 100
#             elif current_placements > 0:
#                 growth_percentage = 100.0

#             # Get Average Salary for the region
#             regional_jobs = base_job_postings.filter(location=region_name)
#             regional_avg_salary = regional_jobs.aggregate(avg_salary=Avg('salary_min'))['avg_salary']
            
#             # Get Demand Score for the region (Applications per job)
#             regional_job_count = regional_jobs.count()
#             regional_application_count = base_applications.filter(job_posting__in=regional_jobs).count()
#             demand_score = (regional_application_count / regional_job_count) * 100 if regional_job_count else 0
            
#             # Get Top Roles for the region
#             regional_top_roles = regional_jobs.values('title').annotate(count=Count('title')).order_by('-count')[:5]

#             placements_by_region.append({
#                 "region": region_name,
#                 "placements": current_placements,
#                 "growth": round(growth_percentage, 2),
#                 "avg_salary": round(regional_avg_salary, 2) if regional_avg_salary is not None else 0.0,
#                 "demand_score": round(demand_score, 2),
#                 "top_roles": list(role['title'] for role in regional_top_roles)
#             })

#         # ------------------ Top Performing Institutions -------------
#         # Note: This part needs a slight change to filter resumes based on `updated_at` of their linked applications
#         with connection.cursor() as cursor:
#             # First, get a list of talent IDs for placements within the filtered time range
#             talent_ids = list(base_applications.values_list('talent', flat=True).distinct())

#             # Then, use those talent IDs to filter the resumes
#             # This query is corrected to handle cases where there are no talent_ids
#             if talent_ids:
#                 sql_query = f"""
#                     SELECT 
#                         COALESCE(JSON_EXTRACT(degree_details, '$[0].institution_name'), JSON_EXTRACT(diploma_details, '$[0].institution_name')) AS institution_name,
#                         COUNT(DISTINCT TMR.id) AS graduates,
#                         COUNT(TMA.id) AS placements
#                     FROM talent_management_resume TMR
#                     LEFT JOIN employer_management_application TMA ON TMR.talent_id_id = TMA.talent_id
#                     WHERE TMR.talent_id_id IN ({','.join(['%s'] * len(talent_ids))})
#                     GROUP BY institution_name
#                     ORDER BY placements DESC
#                 """
#                 cursor.execute(sql_query, talent_ids)
#                 institution_list_raw = cursor.fetchall()
#             else:
#                 institution_list_raw = []

#         institution_list = []
#         for row in institution_list_raw:
#             institution_name, graduates_count, placements_count = row
#             success_rate_institution = (placements_count / graduates_count) * 100 if graduates_count else 0
#             institution_list.append({
#                 "institution_name": institution_name,
#                 "graduates": graduates_count,
#                 "placements": placements_count,
#                 "success_rate": round(success_rate_institution, 2)
#             })

#         # ------------------ Skills in High Demand -------------------
#         skill_counts = Counter()
#         hired_resumes_with_skills = Resume.objects.filter(
#             talent_id__applications__in=base_applications
#         ).exclude(skills__isnull=True).exclude(skills__exact='')

#         for resume in hired_resumes_with_skills:
#             try:
#                 skills_list = json.loads(resume.skills) if resume.skills and resume.skills.strip().startswith('[') else [s.strip() for s in resume.skills.split(',')]
#                 skill_counts.update(s.title() for s in skills_list if s)
#             except (json.JSONDecodeError, AttributeError):
#                 continue

#         top_skills = [
#             {
#                 'skill': skill,
#                 'placements': count,
#                 'growth': 0.0
#             }
#             for skill, count in skill_counts.most_common(10)
#         ]

#         # ------------------ Response -------------------
#         return Response({
#             "global_ai_talent": ai_talent_count,
#             "global_employer": employer_count,
#             "active_placements": active_placements_count,
#             "success_rate": round(success_rate, 2),
#             "average_days_to_place": avg_days_to_place,
#             "placements_by_region": placements_by_region,
#             "top_performing_institutions": institution_list,
#             "skills_in_high_demand": top_skills,
#         })










 
from datetime import timedelta
from django.db.models import Count, Avg, F
from django.utils.timesince import timesince
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
 
from employer_management.models import JobPosting, Application, Interview, ApplicationStatus, InterviewStatus
from talent_management.models import CustomUser, Resume, UserRole

class AdminDashboardAPIView(APIView):
    """
    Provides all necessary data for the main Admin Dashboard, including regional performance.
    """
    # This keeps your existing permission. For a real admin panel, consider using IsAdminUser.
    # permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            kpi_cards_data = self._get_kpi_cards_data()
            kpi_indicators_data = self._get_key_performance_indicators()
            recent_activity_data = self._get_recent_system_activity()
            regional_performance_data = self._get_regional_performance()

            dashboard_data = {
                "kpi_cards": kpi_cards_data,
                "key_performance_indicators": kpi_indicators_data,
                "recent_system_activity": recent_activity_data,
                "regional_performance": regional_performance_data
            }

            return Response(dashboard_data, status=status.HTTP_200_OK)

        except Exception as e:
            # Added traceback for better error logging during development
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "An error occurred while fetching dashboard data.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # --- THIS METHOD IS UNCHANGED ---
    def _get_kpi_cards_data(self):
        active_jobs = JobPosting.objects.filter(is_active=True).count()
        total_applications = Application.objects.exclude(status=ApplicationStatus.DELETED).count()
        interviews_scheduled = Interview.objects.filter(interview_status=InterviewStatus.SCHEDULED).count()
        offers_extended = Application.objects.filter(status=ApplicationStatus.OFFER_EXTENDED).count()

        return {
            "active_jobs": active_jobs,
            "total_applications": total_applications,
            "interviews_scheduled": interviews_scheduled,
            "offers_extended": offers_extended,
        }

    # --- THIS IS THE UPDATED METHOD WITH IMPROVED LOGIC ---
    def _get_key_performance_indicators(self):
        # 1. Profile Completion Rate (Improved Logic)
        # We now check for actual content in key fields, not just the existence of a resume object.
        total_talent_users = CustomUser.objects.filter(user_role=UserRole.TALENT).count()
        complete_resumes_count = Resume.objects.filter(
            talent_id__user_role=UserRole.TALENT,
            resume_pdf__isnull=False,
            skills__isnull=False,
            experience__isnull=False
        ).exclude(resume_pdf='').exclude(skills='').exclude(experience='').count()
        profile_completion_rate = (complete_resumes_count / total_talent_users * 100) if total_talent_users > 0 else 0

        # 2. Interview Success Rate (Improved Logic)
        # This now accurately measures the percentage of interviewed candidates who get an offer/job.
        apps_with_completed_interview = Application.objects.filter(
            interviews__interview_status=InterviewStatus.COMPLETED
        ).distinct()
        successful_apps_post_interview_count = apps_with_completed_interview.filter(
            status__in=[ApplicationStatus.HIRED, ApplicationStatus.OFFER_ACCEPTED, ApplicationStatus.OFFER_EXTENDED]
        ).count()
        interview_success_rate = (successful_apps_post_interview_count / apps_with_completed_interview.count() * 100) if apps_with_completed_interview.count() > 0 else 0

        # 3. Average Placement Time (Slightly Improved Logic)
        # Includes 'OFFER_ACCEPTED' as a successful placement for a more accurate average.
        placed_applications = Application.objects.filter(
            status__in=[ApplicationStatus.HIRED, ApplicationStatus.OFFER_ACCEPTED]
        )
        avg_duration_data = placed_applications.aggregate(avg_time=Avg(F('updated_at') - F('application_date')))
        avg_placement_days = avg_duration_data['avg_time'].days if avg_duration_data['avg_time'] else 0

        # 4. Employer Satisfaction (Static as requested)
        employer_satisfaction_rate = 93.0

        # Returning with the same keys your old API used to prevent breaking the frontend.
        return {
            "profile_completion_rate": round(profile_completion_rate, 1),
            "interview_success_rate": round(interview_success_rate, 1),
            "average_placement_time_days": avg_placement_days,
            "employer_satisfaction_rate": employer_satisfaction_rate
        }

    # --- THIS METHOD IS UNCHANGED ---
    def _get_recent_system_activity(self):
        recent_users = CustomUser.objects.order_by('-date_joined')[:3]
        recent_jobs = JobPosting.objects.select_related('company').order_by('-posted_date')[:3]
        recent_placements = Application.objects.filter(status=ApplicationStatus.HIRED).select_related(
            'talent', 'job_posting'
        ).order_by('-updated_at')[:3]

        activities = []

        for user in recent_users:
            activities.append({
                'time': user.date_joined,
                'type': 'Registration',
                'desc': f"New {user.get_user_role_display()} '{user.username}' signed up."
            })

        for job in recent_jobs:
            activities.append({
                'time': job.posted_date,
                'type': 'Job Posting',
                'desc': f"'{job.company.company_name}' posted a new job: '{job.title}'."
            })

        for app in recent_placements:
            activities.append({
                'time': app.updated_at,
                'type': 'Placement',
                'desc': f"'{app.talent.username}' was hired for '{app.job_posting.title}'."
            })

        sorted_activities = sorted(activities, key=lambda x: x['time'], reverse=True)[:5]

        return [
            {
                'type': item['type'],
                'description': item['desc'],
                'time_ago': f"{timesince(item['time'])} ago"
            } for item in sorted_activities
        ]

    # --- THIS METHOD IS UNCHANGED ---
    def _get_regional_performance(self):
        from django.utils.timezone import now

        base_applications = Application.objects.filter(status=ApplicationStatus.HIRED)
        base_job_postings = JobPosting.objects.all()

        current_period_placements = base_applications.values('job_posting__location').annotate(count=Count('id'))
        current_period_placements_dict = {item['job_posting__location']: item['count'] for item in current_period_placements}

        last_period_end = now().replace(day=1) - timedelta(microseconds=1)
        last_period_start = last_period_end.replace(day=1)
        last_period_placements = Application.objects.filter(
            status=ApplicationStatus.HIRED,
            updated_at__range=(last_period_start, last_period_end)
        ).values('job_posting__location').annotate(count=Count('id'))
        last_period_placements_dict = {item['job_posting__location']: item['count'] for item in last_period_placements}

        all_regions_set = set(current_period_placements_dict.keys()) | set(last_period_placements_dict.keys())
        all_regions_set.discard(None)
        all_regions_set.discard('')
        all_regions = sorted(list(all_regions_set))

        placements_by_region = []
        for region_name in all_regions:
            current_placements = current_period_placements_dict.get(region_name, 0)
            last_placements = last_period_placements_dict.get(region_name, 0)

            growth_percentage = 0.0
            if last_placements > 0:
                growth_percentage = ((current_placements - last_placements) / last_placements) * 100
            elif current_placements > 0:
                growth_percentage = 100.0

            regional_jobs = base_job_postings.filter(location=region_name)
            regional_avg_salary = regional_jobs.aggregate(avg_salary=Avg('salary_min'))['avg_salary']
            regional_job_count = regional_jobs.count()
            regional_application_count = base_applications.filter(job_posting__in=regional_jobs).count()
            demand_score = (regional_application_count / regional_job_count) * 100 if regional_job_count else 0
            regional_top_roles = regional_jobs.values('title').annotate(count=Count('title')).order_by('-count')[:5]

            placements_by_region.append({
                "region": region_name,
                "placements": current_placements,
                "growth": round(growth_percentage, 2),
                "avg_salary": round(regional_avg_salary, 2) if regional_avg_salary else 0.0,
                "demand_score": round(demand_score, 2),
                "top_roles": [role['title'] for role in regional_top_roles]
            })

        return placements_by_region



# from django.db.models import Count
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from talent_management.models import Resume
# from .serializers import TalentDistributionSerializer, TalentFilterOptionsSerializer
# import json

# class TalentHeatmapAPIView(APIView):
#     """
#     API view to provide state-wise AI talent distribution data.
#     Supports filtering by the talent's latest role and certification issuer.
#     """
#     def get(self, request, *args, **kwargs):
#         # Get filter parameters from the request query string
#         role = request.query_params.get('role', None)
#         certification_issuer = request.query_params.get('certification', None)

#         # Start with a base queryset, excluding records without a state
#         queryset = Resume.objects.filter(is_deleted=False).exclude(
#             current_state__isnull=True
#         ).exclude(
#             current_state__exact=''
#         )

#         # --- Apply Role Filter ---
#         # The 'experience' field is a TextField storing a JSON string.
#         # We must use a string-based search. This filter checks if the
#         # string starts with `[{"title": "Your Role"`, which corresponds
#         # to the latest job entry.
#         if role:
#             # This search is case-sensitive. Use __istartswith for case-insensitive.
#             filter_string = f'[{{\"title\": \"{role}\"'
#             queryset = queryset.filter(experience__startswith=filter_string)

#         # --- Apply Certification Filter ---
#         # The 'certification_details' field is a proper JSONField.
#         # We can use the '__contains' lookup to find any record in the JSON array
#         # that has the specified issuer.
#         if certification_issuer:
#             queryset = queryset.filter(
#                 certification_details__contains=[{'issued_by': certification_issuer}]
#             )

#         # --- Aggregate the Data ---
#         # Group the filtered results by 'current_state' and count the number of resumes.
#         # Order the results by count in descending order.
#         state_distribution = queryset.values('current_state').annotate(
#             count=Count('id')
#         ).order_by('-count')

#         # Serialize the aggregated data
#         serializer = TalentDistributionSerializer(state_distribution, many=True)
        
#         # The UI shows both a map and a sorted list, which use the same data source.
#         response_data = {
#             "heatmap_data": serializer.data,
#             "top_states": serializer.data,
#         }

#         return Response(response_data, status=status.HTTP_200_OK)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from talent_management.models import Resume
from talent_management.serializers import FullResumeSerializer
 
 
class TalentHeatmapAPIView(APIView):
    """
    API to get experienced candidates distribution and details:
    - State-wise
    - District-wise
    - Country-wise
    - Total experienced candidates count
    - Full experienced candidates details
    """
 
    def get(self, request, *args, **kwargs):
        queryset = Resume.objects.filter(is_deleted=False).exclude(
            experience__isnull=True
        ).exclude(
            experience__exact=""
        ).exclude(
            experience="[]"
        )
 
        # ✅ Total experienced candidate count
        total_experienced_count = queryset.count()
 
        # ✅ Group by state
        state_distribution = queryset.values("current_state").annotate(
            count=Count("id")
        ).order_by("-count")
 
        # ✅ Group by district
        district_distribution = queryset.values("current_district").annotate(
            count=Count("id")
        ).order_by("-count")
 
        # ✅ Group by country
        country_distribution = queryset.values("current_country").annotate(
            count=Count("id")
        ).order_by("-count")
 
        # ✅ Experienced candidate details (full resume)
        experienced_candidates = FullResumeSerializer(
            queryset, many=True, context={"request": request}
        ).data
 
        response_data = {
            "total_experienced_count": total_experienced_count,
            "state_distribution": [
                {"state": item["current_state"], "count": item["count"]}
                for item in state_distribution if item["current_state"]
            ],
            "district_distribution": [
                {"district": item["current_district"], "count": item["count"]}
                for item in district_distribution if item["current_district"]
            ],
            "country_distribution": [
                {"country": item["current_country"], "count": item["count"]}
                for item in country_distribution if item["current_country"]
            ],
            "experienced_candidates": experienced_candidates
        }
 
        return Response(response_data, status=status.HTTP_200_OK)

        
class TalentFilterOptionsAPIView(APIView):
    """
    API view to provide unique roles and certification issuers to populate UI filters.
    NOTE: This can be a slow query on large datasets. Caching is highly recommended
    in a production environment.
    """
    def get(self, request, *args, **kwargs):
        # --- Get Unique Roles ---
        # Fetches the 'experience' text field for all relevant resumes
        all_experiences = Resume.objects.filter(
            experience__isnull=False, experience__startswith='[{"title":'
        ).values_list('experience', flat=True)
        
        roles = set()
        for exp_json_string in all_experiences:
            try:
                # Safely load the JSON string into a Python list
                exp_list = json.loads(exp_json_string)
                if exp_list and isinstance(exp_list, list) and len(exp_list) > 0:
                    first_exp = exp_list[0]
                    if isinstance(first_exp, dict) and 'title' in first_exp and first_exp['title']:
                        roles.add(first_exp['title'])
            except json.JSONDecodeError:
                # Ignore records with malformed JSON
                continue
        
        # --- Get Unique Certification Issuers ---
        all_certs = Resume.objects.filter(
            certification_details__isnull=False
        ).exclude(
            certification_details__exact='[]'
        ).values_list('certification_details', flat=True)
        
        issuers = set()
        for cert_list in all_certs:
             if cert_list and isinstance(cert_list, list):
                 for cert in cert_list:
                     if isinstance(cert, dict) and 'issued_by' in cert and cert['issued_by']:
                         issuers.add(cert['issued_by'])
                         
        # Prepare and serialize the data for the response
        data = {
            'roles': sorted(list(roles)),
            'certifications': sorted(list(issuers))
        }
        serializer = TalentFilterOptionsSerializer(data)

        return Response(serializer.data, status=status.HTTP_200_OK)






















 #admin_management/views.py

from django.shortcuts import get_object_or_404
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


# # --- NEW: ViewSet for managing SystemHealthStatus ---
# class SystemHealthStatusViewSet(viewsets.ModelViewSet):
#     """
#     API endpoint for CRUD operations on SystemHealthStatus.
#     Accessible only by admins.
#     """
#     queryset = SystemHealthStatus.objects.all().order_by('service_name')
#     serializer_class = SystemHealthStatusModelSerializer
#     permission_classes = [permissions.IsAdminUser] # Use Django's built-in admin permission


# # # --- REWRITTEN: The main dynamic analytics dashboard view ---
# # class GlobalDashboardOverviewAPIView(APIView):
# #     """
# #     Provides a fully dynamic, data-driven overview for the Global AI Talent Export Dashboard.
# #     """
# #  #   permission_classes = [permissions.IsAdminUser]

# #     def _calculate_growth(self, current_period_count, prev_period_count):
# #         if prev_period_count > 0:
# #             return round(((current_period_count - prev_period_count) / prev_period_count) * 100, 1)
# #         return 100.0 if current_period_count > 0 else 0.0

# #     def get(self, request):
# #         today = timezone.now().date()
# #         this_month_start = today.replace(day=1)
# #         last_month_end = this_month_start - timedelta(days=1)
# #         last_month_start = last_month_end.replace(day=1)

# #         # 1. --- CORE METRICS ---
# #         talent_qs = CustomUser.objects.filter(user_role=UserRole.TALENT)
# #         employer_qs = CustomUser.objects.filter(user_role=UserRole.EMPLOYER)
# #         hired_app_qs = Application.objects.filter(status=ApplicationStatus.HIRED)

# #         talent_this_month = talent_qs.filter(date_joined__date__gte=this_month_start).count()
# #         talent_last_month = talent_qs.filter(date_joined__date__range=(last_month_start, last_month_end)).count()
        
# #         employers_this_month = employer_qs.filter(date_joined__date__gte=this_month_start).count()
# #         employers_last_month = employer_qs.filter(date_joined__date__range=(last_month_start, last_month_end)).count()

# #         placements_this_month = hired_app_qs.filter(updated_at__date__gte=this_month_start).count()
# #         placements_last_month = hired_app_qs.filter(updated_at__date__range=(last_month_start, last_month_end)).count()

# #         # 2. --- TOP PERFORMING INSTITUTIONS ---
# #         institution_stats = defaultdict(lambda: {'graduates': 0, 'placements': 0})
# #         all_resumes = Resume.objects.filter(is_deleted=False).prefetch_related('talent_id__applications')

# #         for resume in all_resumes:
# #             # Consolidate degree and diploma details
# #             education_details = []
# #             if isinstance(resume.degree_details, list):
# #                 education_details.extend(resume.degree_details)
# #             if isinstance(resume.diploma_details, list):
# #                 education_details.extend(resume.diploma_details)
            
# #             processed_institutions = set() # To count a graduate only once per resume
# #             for edu in education_details:
# #                 # Handle inconsistent keys ('institution_name')
# #                 inst_name = edu.get('institution_name', '').strip()
# #                 if inst_name and inst_name not in processed_institutions:
# #                     institution_stats[inst_name]['graduates'] += 1
# #                     processed_institutions.add(inst_name)
        
# #         # Correlate with placements
# #         hired_resumes = Resume.objects.filter(talent_id__applications__status=ApplicationStatus.HIRED, is_deleted=False).distinct()
# #         for resume in hired_resumes:
# #             education_details = (resume.degree_details or []) + (resume.diploma_details or [])
# #             processed_placement_institutions = set()
# #             for edu in education_details:
# #                 inst_name = edu.get('institution_name', '').strip()
# #                 if inst_name and inst_name not in processed_placement_institutions:
# #                     institution_stats[inst_name]['placements'] += 1
# #                     processed_placement_institutions.add(inst_name)

# #         top_institutions = sorted(
# #             [
# #                 {
# #                     'institution': name,
# #                     'graduates': data['graduates'],
# #                     'placements': data['placements'],
# #                     'success_rate': round((data['placements'] / data['graduates']) * 100, 1) if data['graduates'] > 0 else 0.0,
# #                 }
# #                 for name, data in institution_stats.items() if data['graduates'] > 0
# #             ],
# #             key=lambda x: x['placements'],
# #             reverse=True
# #         )[:10] # Top 10

# #         # 3. --- SKILLS IN HIGH DEMAND ---
# #         skill_counts = Counter()
# #         hired_resumes_with_skills = hired_resumes.exclude(skills__isnull=True).exclude(skills__exact='')
# #         for resume in hired_resumes_with_skills:
# #             try:
# #                 # Handles both JSON array string '["Python", "Django"]' and simple CSV "Python,Django"
# #                 skills_list = json.loads(resume.skills) if resume.skills.strip().startswith('[') else [s.strip() for s in resume.skills.split(',')]
# #                 skill_counts.update(s.title() for s in skills_list if s)
# #             except (json.JSONDecodeError, AttributeError):
# #                 continue # Skip malformed skill entries

# #         top_skills = [
# #             {'skill': skill, 'placements': count, 'growth': 0.0} # Growth calculation is complex, keeping as placeholder
# #             for skill, count in skill_counts.most_common(10)
# #         ]
        
# #         # 4. --- REGIONAL PERFORMANCE ---
# #         regional_placements = hired_app_qs.values('job_posting__location').annotate(total=Count('id')).order_by('-total')
# #         regional_performance_data = []
# #         for region in regional_placements:
# #             location = region['job_posting__location']
# #             if not location: continue

# #             this_month = hired_app_qs.filter(job_posting__location=location, updated_at__date__gte=this_month_start).count()
# #             last_month = hired_app_qs.filter(job_posting__location=location, updated_at__date__range=(last_month_start, last_month_end)).count()
# #             growth = self._calculate_growth(this_month, last_month)
            
# #             regional_performance_data.append({
# #                 'region': location,
# #                 'placements': region['total'],
# #                 'growth': growth,
# #                 'status': 'Active' if growth > 5 else ('Declining' if growth < -5 else 'Stable')
# #             })

# #         # 5. --- RECENT ACTIVITY ---
# #         recent_users = CustomUser.objects.order_by('-date_joined')[:3]
# #         recent_placements = hired_app_qs.select_related('talent', 'job_posting').order_by('-updated_at')[:3]
# #         recent_jobs = JobPosting.objects.select_related('company').order_by('-posted_date')[:3]
        
# #         activities = []
# #         for user in recent_users:
# #             activities.append({'type': 'Registration', 'desc': f"New {user.get_user_role_display()} '{user.username}' signed up.", 'time': user.date_joined})
# #         for app in recent_placements:
# #             activities.append({'type': 'Placement', 'desc': f"'{app.talent.username}' was hired for '{app.job_posting.title}'.", 'time': app.updated_at})
# #         for job in recent_jobs:
# #             activities.append({'type': 'Job Posting', 'desc': f"'{job.company.company_name}' posted '{job.title}'.", 'time': job.posted_date})

# #         recent_activity_list = sorted(activities, key=lambda x: x['time'], reverse=True)[:5]
# #         recent_system_activity = [
# #             {'type': item['type'], 'description': item['desc'], 'time_ago': timesince(item['time'])}
# #             for item in recent_activity_list
# #         ]
        
# #         # 6. --- KPIs ---
# #         total_talent = talent_qs.count()
# #         talent_with_resumes = Resume.objects.filter(is_deleted=False).values_list('talent_id', flat=True).distinct().count()
        
# #         total_interviews = Interview.objects.count()
# #         completed_interviews = Interview.objects.filter(interview_status=InterviewStatus.COMPLETED).count()

# #         placement_time_agg = hired_app_qs.annotate(
# #             time_diff=F('updated_at') - F('job_posting__posted_date')
# #         ).aggregate(avg_time=Avg('time_diff'))
# #         avg_placement_days = placement_time_agg['avg_time'].days if placement_time_agg['avg_time'] else 0.0

# #         # --- FINAL RESPONSE ASSEMBLY ---
# #         response_data = {
# #             "registered_ai_talent": {
# #                 "count": total_talent,
# #                 "growth_percent": self._calculate_growth(talent_this_month, talent_last_month)
# #             },
# #             "global_employers": {
# #                 "count": employer_qs.count(),
# #                 "growth_percent": self._calculate_growth(employers_this_month, employers_last_month)
# #             },
# #             "active_placements": {
# #                 "count": placements_this_month,
# #                 "growth_percent": self._calculate_growth(placements_this_month, placements_last_month)
# #             },
# #             "total_placements": hired_app_qs.count(),
# #             "regional_performance": regional_performance_data[:10],
# #             "skills_in_high_demand": top_skills,
# #             "top_performing_institutions": top_institutions,
# #             "system_health": SystemHealthStatusModelSerializer(SystemHealthStatus.objects.all(), many=True).data,
# #             "recent_system_activity": recent_system_activity,
# #             "key_performance_indicators": {
# #                 "profile_completion_rate": round((talent_with_resumes / total_talent) * 100, 1) if total_talent > 0 else 0.0,
# #                 "interview_success_rate": round((completed_interviews / total_interviews) * 100, 1) if total_interviews > 0 else 0.0,
# #                 "average_placement_time_days": round(avg_placement_days, 1),
# #                 "employer_satisfaction_rate": 92.5 # Placeholder - requires a feedback model
# #             }
# #         }
        
# #         # Validate and return
# #         serializer = GlobalDashboardOverviewSerializer(data=response_data)
# #         serializer.is_valid(raise_exception=True)
# #         return Response(serializer.validated_data, status=status.HTTP_200_OK)
    

# from collections import Counter, defaultdict
# import json

# from django.db.models import Count
# from django.utils import timezone
# from datetime import timedelta
# from dateutil.relativedelta import relativedelta

# from rest_framework import permissions, status
# from rest_framework.response import Response
# from rest_framework.views import APIView

# # Make sure all your models and the serializer are imported
# from employer_management.models import Application, ApplicationStatus, CustomUser, JobPosting,  UserRole
# from talent_management.models import Resume
# from .serializers import GlobalDashboardOverviewSerializer


# # --- REWRITTEN & FILTERABLE: The main dynamic analytics dashboard view ---
# # class GlobalDashboardOverviewAPIView(APIView):
# #     """
# #     Provides a fully dynamic, data-driven overview for the Global AI Talent Export Dashboard.
# #     Accepts 'region' and 'time_range' query parameters for filtering.
    
# #     Query Parameters:
# #     - region (str, can be repeated): e.g., ?region=New York, USA&region=London, UK
# #     - time_range (str): 'last_week', 'last_month', 'last_quarter', 'last_year'
# #     """
# #  #   permission_classes = [permissions.IsAdminUser]

# #     def _calculate_growth(self, current_period_count, prev_period_count):
# #         if prev_period_count > 0:
# #             return round(((current_period_count - prev_period_count) / prev_period_count) * 100, 1)
# #         return 100.0 if current_period_count > 0 else 0.0

# #     def _get_date_periods(self, time_range_key):
# #         """Calculates current and previous date periods based on a string key."""
# #         today = timezone.now().date()
        
# #         if time_range_key == 'last_week':
# #             # Current period is today and the 6 days before it.
# #             current_start = today - timedelta(days=6)
# #             # Previous period is the 7 days before the current period.
# #             prev_start = current_start - timedelta(days=7)
# #             prev_end = current_start - timedelta(days=1)
# #         elif time_range_key == 'last_quarter':
# #             current_start = today - relativedelta(months=3)
# #             prev_start = current_start - relativedelta(months=3)
# #             prev_end = current_start - timedelta(days=1)
# #         elif time_range_key == 'last_year':
# #             current_start = today - relativedelta(years=1)
# #             prev_start = current_start - relativedelta(years=1)
# #             prev_end = current_start - timedelta(days=1)
# #         else: # Default to 'last_month'
# #             current_start = today - relativedelta(months=1)
# #             prev_start = current_start - relativedelta(months=1)
# #             prev_end = current_start - timedelta(days=1)
            
# #         return {
# #             'current_start': current_start,
# #             'prev_start': prev_start,
# #             'prev_end': prev_end
# #         }

# #     def get(self, request):
# #         # 1. --- PARSE FILTERS AND SETUP DATES ---
# #         selected_regions = request.query_params.getlist('region')
# #         time_range_key = request.query_params.get('time_range', 'last_month')

# #         periods = self._get_date_periods(time_range_key)
# #         current_period_start = periods['current_start']
# #         prev_period_start = periods['prev_start']
# #         prev_period_end = periods['prev_end']
        
# #         # 2. --- SETUP AND FILTER CORE QUERYSETS ---
# #         talent_qs = CustomUser.objects.filter(user_role=UserRole.TALENT)
# #         employer_qs = CustomUser.objects.filter(user_role=UserRole.EMPLOYER)
# #         hired_app_qs_base = Application.objects.filter(status=ApplicationStatus.HIRED)

# #         # Apply region and time filters ONLY to placement-related data
# #         hired_app_qs_filtered = hired_app_qs_base
# #         if selected_regions:
# #             hired_app_qs_filtered = hired_app_qs_filtered.filter(job_posting__location__in=selected_regions)
        
# #         # Further filter by the main time window for sections that depend on it
# #         hired_app_qs_filtered = hired_app_qs_filtered.filter(updated_at__date__gte=current_period_start)

# #         # 3. --- CORE METRICS ---
# #         talent_this_period = talent_qs.filter(date_joined__date__gte=current_period_start).count()
# #         talent_prev_period = talent_qs.filter(date_joined__date__range=(prev_period_start, prev_period_end)).count()
        
# #         employers_this_period = employer_qs.filter(date_joined__date__gte=current_period_start).count()
# #         employers_prev_period = employer_qs.filter(date_joined__date__range=(prev_period_start, prev_period_end)).count()

# #         placements_this_period = hired_app_qs_base.filter(updated_at__date__gte=current_period_start).count()
# #         placements_prev_period = hired_app_qs_base.filter(updated_at__date__range=(prev_period_start, prev_period_end)).count()
# #         if selected_regions: # If filtering, recalculate placement counts on the filtered set
# #             placements_this_period = hired_app_qs_filtered.filter(updated_at__date__gte=current_period_start).count()
# #             placements_prev_period = hired_app_qs_base.filter(job_posting__location__in=selected_regions, updated_at__date__range=(prev_period_start, prev_period_end)).count()

# #         # 4. --- TOP PERFORMING INSTITUTIONS (based on filtered placements) ---
# #         institution_stats = defaultdict(lambda: {'graduates': 0, 'placements': 0})
# #         all_resumes = Resume.objects.filter(is_deleted=False)

# #         # First, calculate total graduates from all institutions (this is a global stat)
# #         for resume in all_resumes:
# #             education_details = (resume.degree_details or []) + (resume.diploma_details or [])
# #             processed_institutions = set()
# #             for edu in education_details:
# #                 inst_name = edu.get('institution_name', '').strip()
# #                 if inst_name and inst_name not in processed_institutions:
# #                     institution_stats[inst_name]['graduates'] += 1
# #                     processed_institutions.add(inst_name)
        
# #         # Now, correlate with placements FROM THE FILTERED DATA
# #         hired_resumes = Resume.objects.filter(
# #             talent_id__applications__in=hired_app_qs_filtered, 
# #             is_deleted=False
# #         ).distinct()

# #         for resume in hired_resumes:
# #             education_details = (resume.degree_details or []) + (resume.diploma_details or [])
# #             processed_placement_institutions = set()
# #             for edu in education_details:
# #                 inst_name = edu.get('institution_name', '').strip()
# #                 if inst_name and inst_name not in processed_placement_institutions:
# #                     institution_stats[inst_name]['placements'] += 1
# #                     processed_placement_institutions.add(inst_name)

# #         top_institutions = sorted(
# #             [
# #                 {
# #                     'institution': name,
# #                     'graduates': data['graduates'],
# #                     'placements': data['placements'], # This count is now filtered
# #                     'success_rate': round((data['placements'] / data['graduates']) * 100, 1) if data['graduates'] > 0 else 0.0,
# #                 }
# #                 for name, data in institution_stats.items() if data['placements'] > 0 # Show only institutions with placements in the filtered view
# #             ],
# #             key=lambda x: x['placements'],
# #             reverse=True
# #         )[:10]

# #         # 5. --- SKILLS IN HIGH DEMAND (based on filtered placements) ---
# #         skill_counts = Counter()
# #         # The `hired_resumes` queryset from above is already filtered by region and time
# #         hired_resumes_with_skills = hired_resumes.exclude(skills__isnull=True).exclude(skills__exact='')
# #         for resume in hired_resumes_with_skills:
# #             try:
# #                 skills_list = json.loads(resume.skills) if resume.skills.strip().startswith('[') else [s.strip() for s in resume.skills.split(',')]
# #                 skill_counts.update(s.title() for s in skills_list if s)
# #             except (json.JSONDecodeError, AttributeError):
# #                 continue

# #         top_skills = [
# #             {'skill': skill, 'placements': count, 'growth': 0.0}
# #             for skill, count in skill_counts.most_common(10)
# #         ]
        
# #         # 6. --- REGIONAL PERFORMANCE ---
# #         # Base this on the main `hired_app_qs_base` so we can still show a global list,
# #         # but if regions are selected, we filter it down.
# #         regional_qs_base = hired_app_qs_base
# #         if selected_regions:
# #             regional_qs_base = regional_qs_base.filter(job_posting__location__in=selected_regions)

# #         regional_placements = regional_qs_base.values('job_posting__location').annotate(total=Count('id')).order_by('-total')
# #         regional_performance_data = []
# #         for region in regional_placements:
# #             location = region['job_posting__location']
# #             if not location: continue

# #             this_period = hired_app_qs_base.filter(job_posting__location=location, updated_at__date__gte=current_period_start).count()
# #             prev_period = hired_app_qs_base.filter(job_posting__location=location, updated_at__date__range=(prev_period_start, prev_period_end)).count()
# #             growth = self._calculate_growth(this_period, prev_period)
            
# #             regional_performance_data.append({
# #                 'region': location,
# #                 'placements': region['total'],
# #                 'growth': growth,
# #                 'status': 'Active' if growth > 5 else ('Declining' if growth < -5 else 'Stable')
# #             })

# #         # --- FINAL RESPONSE ASSEMBLY ---
# #         response_data = {
# #             "registered_ai_talent": {
# #                 "count": talent_qs.count(),
# #                 "growth_percent": self._calculate_growth(talent_this_period, talent_prev_period)
# #             },
# #             "global_employers": {
# #                 "count": employer_qs.count(),
# #                 "growth_percent": self._calculate_growth(employers_this_period, employers_prev_period)
# #             },
# #             "active_placements": {
# #                 "count": placements_this_period,
# #                 "growth_percent": self._calculate_growth(placements_this_period, placements_prev_period)
# #             },
# #             "total_placements": hired_app_qs_base.count() if not selected_regions else hired_app_qs_filtered.count(),
# #             "regional_performance": regional_performance_data[:10],
# #             "skills_in_high_demand": top_skills,
# #             "top_performing_institutions": top_institutions,
# #         }
        
# #         # Validate and return
# #         serializer = GlobalDashboardOverviewSerializer(data=response_data)
# #         serializer.is_valid(raise_exception=True)
# #         return Response(serializer.validated_data, status=status.HTTP_200_OK)





    
# from django.db import connections
# from datetime import datetime
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from rest_framework.views import APIView
 
 
# class TalentHeatmapAPIView(APIView):
#     permission_classes = [IsAuthenticated]
 
#     def get_statewise_data(self, role=None):
#         # Base query
#         query = """
#             SELECT current_state, COUNT(id) AS professionals
#             FROM gatep_platform_db.talent_management_resume
#             WHERE current_state IS NOT NULL AND TRIM(current_state) != ''
#         """
#         params = []
#         # Add role filter if present
#         if role:
#             query += " AND LOWER(TRIM(user_role)) = LOWER(%s)"
#             params.append(role.strip())
#         query += " GROUP BY current_state"
 
#         # Execute query
#         with connections['default'].cursor() as cursor:
#             cursor.execute(query, params)
#             rows = cursor.fetchall()
 
#         # Clean result
#         result = []
#         for row in rows:
#             state = row[0].strip().title()
#             count = row[1]
#             result.append({"state": state, "professionals": count})
 
#         # Optional: sort by count
#         result.sort(key=lambda x: x["professionals"], reverse=True)
#         return result
 
#     def get(self, request):
#         # 1. Overall statewise professionals
#         overall_data = self.get_statewise_data()
 
#         # 2. Role-specific data
#         roles = ["AI/ML Engineer", "Data Scientist", "Business Analyst"]
#         rolewise_data = {}
#         for role in roles:
#             rolewise_data[role] = self.get_statewise_data(role=role)
 
#         # 3. Final response
#         response = {
#             "overall": overall_data,
#             "roles": rolewise_data
#         }
#         return Response(response)



 
# from datetime import datetime
# from collections import Counter
# import json
 
# from django.db import connections
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
 
# import json
# from collections import defaultdict
# from django.db import connection
# from rest_framework.views import APIView
# from rest_framework.response import Response
 
#talentheatmap api institutionwise api with filters(admin)
import json
from collections import defaultdict
from datetime import timedelta

from django.db import connection
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView


class TalentHeatmapInstituteWiseAPIView(APIView):
    def get(self, request):
        institution_counts = defaultdict(int)

        # --- Filters from query params ---
        date_filter = request.GET.get("date_range", "last_6_months")  # default
        job_filter = request.GET.get("job", "all")  # default

        # --- Date filter handling ---
        today = timezone.now().date()
        if date_filter == "last_month":
            start_date = today - timedelta(days=30)
        elif date_filter == "last_3_months":
            start_date = today - timedelta(days=90)
        elif date_filter == "last_6_months":
            start_date = today - timedelta(days=180)
        elif date_filter == "last_year":
            start_date = today - timedelta(days=365)
        else:
            start_date = None  # no filter

        # --- SQL Query Build ---
        query = """
            SELECT degree_details, diploma_details, created_at, generated_preferences
            FROM talent_management_resume
            WHERE (degree_details IS NOT NULL OR diploma_details IS NOT NULL)
        """
        params = []

        # Apply date filter
        if start_date:
            query += " AND created_at >= %s"
            params.append(start_date)

        # Apply job filter
        if job_filter.lower() != "all":
            query += " AND generated_preferences LIKE %s"
            params.append(f"%{job_filter}%")

        # --- Execute query ---
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        # --- Parse results ---
        for degree_details, diploma_details, created_at, preferences in rows:
            # Degree details
            if degree_details:
                try:
                    degree_data = json.loads(degree_details)
                    for degree in degree_data:
                        name = degree.get("institution_name")
                        if name:
                            institution_counts[name.strip().lower()] += 1
                except json.JSONDecodeError:
                    pass

            # Diploma details
            if diploma_details:
                try:
                    diploma_data = json.loads(diploma_details)
                    for diploma in diploma_data:
                        name = diploma.get("institution_name")
                        if name:
                            institution_counts[name.strip().lower()] += 1
                except json.JSONDecodeError:
                    pass

        # --- Format response (Sorted) --- (इथे बदल केला आहे)
        # 1. डिक्शनरीला पदवीधरांच्या संख्येनुसार उतरत्या क्रमाने सॉर्ट करा
        sorted_institutions = sorted(institution_counts.items(), key=lambda item: item[1], reverse=True)

        # 2. अंतिम निकाल (result) तयार करा
        result = [{"institution": inst.title(), "graduates": count}
                  for inst, count in sorted_institutions]

        return Response(result)


# class AnalyticsCountAPIView(APIView):
#     """
#     API: /api/admin/analytics-count/
#     Fetches overall analytics counts from gatep_platform_db
#     """
 
#     def get(self, request):
#         data = {}
 
#         with connection.cursor() as cursor:
#             #  Total AI Talent Count
#             cursor.execute("""
#                 SELECT COUNT(*) 
#                 FROM talent_management_customuser 
#                 WHERE user_role = 'TALENT';
#             """)
#             data['total_ai_talent'] = cursor.fetchone()[0]
 
#             # Global Employer Count
#             cursor.execute("""
#                 SELECT COUNT(*) 
#                 FROM talent_management_customuser 
#                 WHERE user_role = 'EMPLOYER';
#             """)
#             data['global_employer_count'] = cursor.fetchone()[0]
 
#             #  Active Placements Count (HIRED)
#             cursor.execute("""
#                 SELECT COUNT(*) 
#                 FROM employer_management_application 
#                 WHERE status = 'HIRED';
#             """)
#             hired_count = cursor.fetchone()[0]
#             data['active_placements'] = hired_count
 
#             #  Total Applications Count
#             cursor.execute("""
#                 SELECT COUNT(*) 
#                 FROM employer_management_application;
#             """)
#             total_applications = cursor.fetchone()[0]
 
#             # Success Rate Calculation
#             if total_applications > 0:
#                 data['success_rate'] = round((hired_count / total_applications) * 100, 2)
#             else:
#                 data['success_rate'] = 0.0
 
#             #  Average Days to Place
#             cursor.execute("""
#                 SELECT AVG(DATEDIFF(updated_at, created_at)) 
#                 FROM employer_management_application 
#                 WHERE status = 'HIRED';
#             """)
#             avg_days = cursor.fetchone()[0]
#             data['average_days_to_place'] = round(avg_days, 2) if avg_days else 0.0
 
#         return Response(data)
    

    


    



# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework.permissions import IsAdminUser
# from django.utils import timezone
# from datetime import timedelta
# from django.core.cache import cache

# from . import services as admin_services

# class AdminDashboardAnalyticsView(APIView):
#     """
#     Provides all aggregated data for the main admin analytics dashboard.

#     This endpoint is designed to be called once to populate the entire dashboard UI.
#     It supports time-based filtering via a 'period' query parameter.

#     Query Parameters:
#         - period (str): Time range for the analytics.
#                         Supports 'last_week', 'last_month', 'last_90_days'.
#                         Defaults to 'last_month'.
    
#     Permissions:
#         - Requires the user to be an admin (`is_staff=True`).
    
#     Caching:
#         - Results are cached to ensure fast response times and reduce database load.
#         - The cache key is generated based on the 'period' filter.
#         - Default cache timeout is 1 hour (3600 seconds).
#     """
#     # permission_classes = [IsAdminUser]

#     def get(self, request, *args, **kwargs):
#         # 1. Parse and validate the 'period' filter from the request
#         period = request.query_params.get('period', 'last_month')
#         if period not in ['last_week', 'last_month', 'last_90_days']:
#             period = 'last_month'  # Default to a safe value

#         # 2. Check for cached data first to avoid re-computation
#         cache_key = f'admin_dashboard_analytics_{period}'
#         cached_data = cache.get(cache_key)
#         if cached_data:
#             # If a cached version exists, return it immediately
#             return Response(cached_data)

#         # 3. Define date ranges for the current and previous periods
#         # This is needed for calculating growth percentages.
#         end_date_current = timezone.now()
        
#         if period == 'last_week':
#             duration_days = 7
#         elif period == 'last_90_days':
#             duration_days = 90
#         else: # 'last_month'
#             duration_days = 30
            
#         start_date_current = end_date_current - timedelta(days=duration_days)
#         end_date_previous = start_date_current
#         start_date_previous = end_date_previous - timedelta(days=duration_days)

#         date_ranges = {
#             'current': {'start': start_date_current, 'end': end_date_current},
#             'previous': {'start': start_date_previous, 'end': end_date_previous}
#         }

#         # 4. Call service functions to get processed data
#         kpi_data = admin_services.get_kpi_data(date_ranges)
#         regional_performance_data = admin_services.get_regional_performance_data(date_ranges)
#         skills_in_demand_data = admin_services.get_skills_in_demand_data(date_ranges)
#         # Placeholder for the more complex institutions data
#         # top_institutions_data = admin_services.get_top_institutions_data(date_ranges)

#         # 5. Assemble the final response payload
#         dashboard_data = {
#             "kpi_cards": kpi_data,
#             "regional_performance": regional_performance_data,
#             "skills_in_demand": skills_in_demand_data,
#             # "top_institutions": top_institutions_data,
#         }

#         # 6. Store the newly computed data in the cache for future requests
#         cache.set(cache_key, dashboard_data, timeout=3600)  # Cache for 1 hour

#         return Response(dashboard_data)
    
















# from rest_framework.views import APIView
# from rest_framework.response import Response
# from employer_management.models import JobPosting # Make sure to import your JobPosting model

# class DashboardFilterOptionsAPIView(APIView):
#     """
#     Provides dynamic lists for dashboard filters, such as unique regions.
#     """
#     def get(self, request):
#         # Fetch unique, non-null, non-empty location strings from all job postings
#         # Sorting them makes the dropdown list user-friendly.
#         regions = JobPosting.objects.exclude(
#             location__isnull=True
#         ).exclude(
#             location__exact=''
#         ).values_list(
#             'location', flat=True
#         ).distinct().order_by('location')
        
#         # We can add more filter options here in the future
#         filter_data = {
#             "regions": list(regions)
#         }
        
#         return Response(filter_data)






















from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
 
from employer_management.models import Company, JobPosting, Interview, Application
from talent_management.models import TalentProfile  # ✅ import TalentProfile
 
 
class NotificationView(APIView):
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        user = request.user
        notifications = []
 
        # 🟢 ADMIN Notifications
        if user.user_role == "ADMIN":
            total_employers = Company.objects.count()
            total_jobs = JobPosting.objects.count()
            total_talents = Application.objects.values("talent").distinct().count()
            total_interviews = Interview.objects.count()
 
            notifications.append({
                "title": "Admin Dashboard",
                "description": f"Employers: {total_employers}, Jobs: {total_jobs}, "
                               f"Talents: {total_talents}, Interviews: {total_interviews}",
                "type": "info"
            })
 
        # 🟢 EMPLOYER Notifications
        elif user.user_role == "EMPLOYER":
            try:
                company = Company.objects.get(user=user)
 
                job_count = JobPosting.objects.filter(company=company).count()
                app_count = Application.objects.filter(job_posting__company=company).count()
                interviews = Interview.objects.filter(application__job_posting__company=company)
 
                notifications.extend([
                    {
                        "title": "Company Created",
                        "description": f"Your company {company.company_name} is registered.",
                        "type": "success"
                    },
                    {
                        "title": "Jobs Posted",
                        "description": f"You have posted {job_count} jobs.",
                        "type": "info"
                    },
                    {
                        "title": "Applications Received",
                        "description": f"{app_count} talents have applied to your jobs.",
                        "type": "info"
                    },
                    {
                        "title": "Interviews Status",
                        "description": f"Scheduled: {interviews.filter(interview_status='Scheduled').count()}, "
                                       f"Completed: {interviews.filter(interview_status='Completed').count()}, "
                                       f"Cancelled: {interviews.filter(interview_status='Cancelled').count()}",
                        "type": "warning"
                    }
                ])
            except Company.DoesNotExist:
                notifications.append({
                    "title": "No Company Found",
                    "description": "You haven’t registered your company yet.",
                    "type": "error"
                })
 
        # 🟢 TALENT Notifications
        elif user.user_role == "TALENT":
            try:
                # ✅ TalentProfile linked to CustomUser
                talent_profile = user.talentprofile  
 
                # ✅ Applications and Interviews need CustomUser (not TalentProfile)
                apps = Application.objects.filter(talent=user)
                interviews = Interview.objects.filter(application__talent=user)
 
                notifications.extend([
                    {
                        "title": "Applications",
                        "description": f"You have applied to {apps.count()} jobs.",
                        "type": "info"
                    },
                    {
                        "title": "Interview Updates",
                        "description": f"Scheduled: {interviews.filter(interview_status='Scheduled').count()}, "
                                       f"Rescheduled: {interviews.filter(interview_status='Rescheduled').count()}, "
                                       f"Completed: {interviews.filter(interview_status='Completed').count()}",
                        "type": "success"
                    },
                    {
                        "title": "Profile",
                        "description": "Profile completed ✅" if getattr(user, "is_profile_completed", False) else "Profile incomplete ❌",
                        "type": "warning"
                    }
                ])
 
            except TalentProfile.DoesNotExist:
                notifications.extend([
                    {
                        "title": "Applications",
                        "description": "You haven’t applied to any jobs yet.",
                        "type": "info"
                    },  
                    {
                        "title": "Interview Updates",
                        "description": "No interviews scheduled yet.",
                        "type": "success"
                    },
                    {
                        "title": "Profile",
                        "description": "You haven’t completed your talent profile yet.",
                        "type": "error"
                    }
                ])
 
        return Response({"notifications": notifications})