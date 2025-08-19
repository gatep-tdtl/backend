
from django.db.models import Count, Avg
from collections import Counter
from decimal import Decimal

# Import all necessary models
from talent_management.models import CustomUser
from employer_management.models import Application, JobPosting, Company, UserRole, JobStatus

def _calculate_growth(current_value, previous_value):
    """Helper function to calculate percentage growth, handling division by zero."""
    if previous_value == 0:
        return 0  # Can't calculate growth if the previous value was zero
    return round(((current_value - previous_value) / previous_value) * 100, 2)

def get_kpi_data(date_ranges):
    """Calculates the primary KPI metrics for the dashboard header."""
    
    # --- Data for Current Period ---
    current_apps = Application.objects.filter(application_date__range=(date_ranges['current']['start'], date_ranges['current']['end']))
    current_hires = current_apps.filter(status__in=['HIRED', 'OFFER_ACCEPTED']).count()
    
    # --- Data for Previous Period ---
    previous_apps = Application.objects.filter(application_date__range=(date_ranges['previous']['start'], date_ranges['previous']['end']))
    previous_hires = previous_apps.filter(status__in=['HIRED', 'OFFER_ACCEPTED']).count()

    # --- Calculations ---
    total_talent = CustomUser.objects.filter(user_role=UserRole.TALENT).count()
    total_employers = Company.objects.count()

    success_rate = (current_hires / current_apps.count() * 100) if current_apps.count() > 0 else 0
    
    return {
        "total_talent": {
            "value": total_talent,
            "growth": 0 # Growth is not applicable for a total count
        },
        "active_placements": {
            "value": current_hires,
            "growth": _calculate_growth(current_hires, previous_hires)
        },
        "global_employers": {
            "value": total_employers,
            "growth": 0 # Growth is not applicable for a total count
        },
        "success_rate": {
            "value": round(success_rate, 2),
            "growth": 0 # Growth for a rate is more complex, keeping it simple for now
        },
        "avg_days_to_place": { # This remains a placeholder as it's complex
            "value": 15,
            "growth": -2 # Mocking "2 days improved"
        }
    }

def get_regional_performance_data(date_ranges):
    """Analyzes performance by geographic region based on JobPosting.location."""
    
    hired_apps = Application.objects.filter(
        status__in=['HIRED', 'OFFER_ACCEPTED'],
        updated_at__range=(date_ranges['current']['start'], date_ranges['current']['end'])
    ).select_related('job_posting')

    performance_by_region = {}
    for app in hired_apps:
        # Normalize the location string to ensure consistent grouping
        location = app.job_posting.location.strip().lower()
        if not location:
            continue

        if location not in performance_by_region:
            performance_by_region[location] = {'placements': 0, 'salaries': [], 'roles': []}
        
        performance_by_region[location]['placements'] += 1
        if app.job_posting.salary_max is not None:
            performance_by_region[location]['salaries'].append(app.job_posting.salary_max)
        performance_by_region[location]['roles'].append(app.job_posting.title)

    results = []
    for location, data in performance_by_region.items():
        avg_salary = sum(data['salaries']) / len(data['salaries']) if data['salaries'] else Decimal('0.0')
        top_roles = [item[0] for item in Counter(data['roles']).most_common(2)]

        results.append({
            "region": location.title(),
            "placements": data['placements'],
            "avg_salary": round(avg_salary),
            "top_roles": top_roles,
            # Placeholders for now, would require another query on the previous period
            "growth": 15,
            "demand_score": 95,
        })
    
    results.sort(key=lambda x: x['placements'], reverse=True)
    return results

def get_skills_in_demand_data(date_ranges):
    """Finds the most frequently requested skills from job postings."""
    
    # --- Skills in Current Period ---
    current_postings = JobPosting.objects.filter(created_at__range=(date_ranges['current']['start'], date_ranges['current']['end']), status=JobStatus.PUBLISHED)
    current_skills_flat_list = []
    for skills in current_postings.values_list('required_skills', flat=True):
        if isinstance(skills, list):
            current_skills_flat_list.extend(skills)
    current_skill_counts = Counter(current_skills_flat_list)

    # --- Skills in Previous Period ---
    previous_postings = JobPosting.objects.filter(created_at__range=(date_ranges['previous']['start'], date_ranges['previous']['end']), status=JobStatus.PUBLISHED)
    previous_skills_flat_list = []
    for skills in previous_postings.values_list('required_skills', flat=True):
        if isinstance(skills, list):
            previous_skills_flat_list.extend(skills)
    previous_skill_counts = Counter(previous_skills_flat_list)

    results = []
    # Use the top 5 skills from the current period as the baseline
    for skill, current_count in current_skill_counts.most_common(5):
        previous_count = previous_skill_counts.get(skill, 0)
        results.append({
            "skill": skill,
            "mentions": current_count, # Renamed from 'placements' for clarity
            "growth": _calculate_growth(current_count, previous_count)
        })
    
    return results






