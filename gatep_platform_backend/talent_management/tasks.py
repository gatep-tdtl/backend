# talent_management/tasks.py

from celery import shared_task
import requests
import os
import time
from django.db import transaction
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
import json # For handling JSON string conversions (e.g., for logging)

from employer_management.models import JobType, ExperienceLevel, Company # Assuming Company also imported for job processing

# Import your JobListing and CustomUser models from their respective apps
from .models import JobListing # From talent_management app
from django.contrib.auth import get_user_model # To get CustomUser from auth_management app
CustomUser = get_user_model()


def map_employment_type(api_type):
    if api_type:
        api_type = str(api_type).upper().replace(' ', '_').replace('-', '_')
        # Access choices from the imported JobType enum
        if api_type in [choice[0] for choice in JobType.choices]:
            return api_type
    return None

def map_experience_level(api_level): # Assuming you'd have a similar function for experience
    if api_level:
        api_level = str(api_level).upper().replace(' ', '_').replace('-', '_')
        if api_level in [choice[0] for choice in ExperienceLevel.choices]:
            return api_level
    return None
# --- Helper functions (from previous turn, include these in this file) ---


def map_work_location_type(api_type):
    if api_type:
        api_type = str(api_type).upper().replace(' ', '_').replace('-', '_') # Ensure string and convert
        if api_type in [choice[0] for choice in JobListing.WORK_LOCATION_TYPE_CHOICES]:
            return api_type
    return None

def convert_to_decimal(value):
    try:
        # Handle cases where value might be float or string, ensure Decimal conversion
        return Decimal(str(value)) if value is not None else None
    except (ValueError, TypeError): # Add InvalidOperation for Decimal errors
        return None

def parse_datetime_string(datetime_str):
    if not datetime_str:
        return None
    try:
        # datetime.fromisoformat handles 'Z' for UTC
        return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'): # Added .%f for microseconds
        try:
            return datetime.strptime(datetime_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None

# --- Main Job Processing Function ---
def process_and_save_job(job_data, source, system_user):
    """
    Processes raw job data from APIJobs and saves/updates it in the JobListing model.
    """
    external_id = job_data.get('id')
    if not external_id:
        print(f"Warning: Job from {source} has no unique 'id'. Skipping.")
        return

    # --- Data Mapping from APIJobs to JobListing Model ---
    mapped_data = {
        'title': job_data.get('title'),
        'description': job_data.get('description'),
        
        # Combine skills_requirements and responsibilities into general requirements
        'requirements': (
            "\nSkills: " + "\n- ".join(job_data.get('skills_requirements', [])) if job_data.get('skills_requirements') else ""
        ) + (
            "\n\nResponsibilities: " + "\n- ".join(job_data.get('responsibilities', [])) if job_data.get('responsibilities') else ""
        ) + (
            ("\n\nExperience: " + str(job_data.get('experience_requirements_months')) + " months") if job_data.get('experience_requirements_months') is not None else ""
        ) + (
            ("\n\nEducation: " + job_data.get('education_requirements')) if job_data.get('education_requirements') else ""
        ),
        
        # Company Info
        'company_name': job_data.get('hiring_organization_name'),
        'hiring_organization_url': job_data.get('hiring_organization_url'),
        'hiring_organization_logo': job_data.get('hiring_organization_logo'),

        # Location Info: Combine into a single string
        'location': ", ".join(filter(None, [job_data.get('city'), job_data.get('region'), job_data.get('country')])).strip(),
        
        # Salary Information
        'salary_min': convert_to_decimal(job_data.get('base_salary_min_value')),
        'salary_max': convert_to_decimal(job_data.get('base_salary_max_value')),
        'currency': job_data.get('base_salary_currency'),
        'base_salary_unit': job_data.get('base_salary_unit'),

        # Employment Type & Workplace Options
        'employment_type': map_employment_type(job_data.get('employment_type')),
        'work_location_type': map_work_location_type(job_data.get('workplace_type')),
        
        # External Application URL - APIJobs lists 'website' for organization, so verify this is the apply URL
        # If 'website' is the company's main site, not specific application, this needs adjustment.
        # Assuming 'website' in the 'hits' schema refers to the job's application URL.
        'external_application_url': job_data.get('website'),
        
        'published_at': parse_datetime_string(job_data.get('published_at')),

        # Industry
        'industry': job_data.get('industry'),

        # Link to external source for deduplication
        'external_source_id': f"{source}_{external_id}",
        'external_source_name': source,

        # Job Verification Logic (10.3)
        # For APIJobs data, assume 'VERIFIED' as it's a structured API
        'status': 'VERIFIED',
        'verified_by': system_user,
        'verified_at': timezone.now(),
    }

    # --- Deduplication & Update Logic ---
    try:
        with transaction.atomic():
            job_listing, created = JobListing.objects.update_or_create(
                external_source_id=mapped_data['external_source_id'],
                defaults=mapped_data
            )
            if created:
                print(f"  [DB] Created new job: {job_listing.title} from {source} (ID: {job_listing.id})")
            else:
                print(f"  [DB] Updated existing job: {job_listing.title} from {source} (ID: {job_listing.id})")

    except Exception as e:
        print(f"  [DB ERROR] Failed to save/update job from {source} (ID: {external_id}): {e}")
        import traceback
        print(traceback.format_exc())
        print(f"Problematic job_data (from API): {json.dumps(job_data, indent=2)}")

# --- Celery Task for APIJobs ---
@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def fetch_jobs_from_apijobs(self, query_configs=None):
    from django.conf import settings # Import settings here for Celery task

    api_key = settings.APIJOBS_API_KEY
    if not api_key or api_key == 'YOUR_API_JOBS_DEV_KEY':
        print("APIJOBS_API_KEY not properly set in settings. Skipping fetch.")
        return

    base_url = "https://api.apijobs.dev/v1/job/search"
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json"
    }

    # Define common search configurations to cover your target regions and job types
    if query_configs is None:
        query_configs = [
            {"q": "software engineer", "country": "US", "size": 50},
            {"q": "data scientist", "country": "GB", "size": 50},
            {"q": "AI ML", "country": "AE", "size": 50}, # UAE
            {"q": "full stack", "country": "SG", "size": 50}, # Singapore
            {"q": "cybersecurity", "country": "DE", "size": 50}, # Germany (EU)
            {"q": "product manager", "workplace_type": "remote", "size": 50},
            {"industry": "Finance", "country": "US", "size": 50},
            # Add more specific queries for your needs.
            # Example for filtering by salary range (add to JobListing model if you want to store these specific filter parameters)
            # {"q": "developer", "country": "US", "base_salary_min_value": 70000, "base_salary_currency": "USD", "base_salary_unit": "year", "size": 50},
        ]

    total_jobs_processed_overall = 0

    # Ensure system_user exists for verification logging
    try:
        system_user = CustomUser.objects.get(username='system_job_importer')
    except CustomUser.DoesNotExist:
        system_user = CustomUser.objects.create_user(
            username='system_job_importer',
            email='system@yourdomain.com',
            password=None,
            user_role='ADMIN',
            is_active=True
        )
        print("Created system_job_importer user for job verification.")


    for config_idx, query_config in enumerate(query_configs):
        current_offset = 0
        jobs_processed_for_query = 0
        search_size = query_config.get("size", 50)
        
        print(f"\n--- Starting fetch for Query {config_idx+1}/{len(query_configs)}: {query_config.get('q', 'N/A')} in {query_config.get('country', 'N/A')} ---")

        while True:
            request_body = {
                **query_config,
                "from": current_offset,
                "size": search_size
            }
            # Remove keys that are None or empty lists to avoid API errors
            request_body = {k: v for k, v in request_body.items() if v is not None and v != []}

            try:
                print(f"  Fetching from offset {current_offset} with size {search_size} for query: {request_body}")
                response = requests.post(base_url, headers=headers, json=request_body, timeout=60)
                response.raise_for_status()
                
                data = response.json()
                
                if not data.get('ok'):
                    print(f"  API response not 'ok': {data.get('message', 'Unknown error')}. Stopping for this query.")
                    break

                jobs = data.get('hits', [])
                total_hits_for_query = data.get('total', 0)

                if not jobs:
                    print(f"  No more jobs found for this query or offset {current_offset}.")
                    break

                for job_data in jobs:
                    process_and_save_job(job_data, source='APIJobs', system_user=system_user)
                    jobs_processed_for_query += 1
                    total_jobs_processed_overall += 1

                if (current_offset + len(jobs)) < total_hits_for_query:
                    current_offset += len(jobs)
                    time.sleep(0.5)
                else:
                    break

            except requests.exceptions.Timeout as e:
                print(f"  Timeout fetching jobs for query {request_body}. Retrying Celery task...")
                raise self.retry(exc=e)
            except requests.exceptions.RequestException as e:
                print(f"  Error fetching jobs for query {request_body}: {e}. Retrying Celery task...")
                raise self.retry(exc=e)
            except Exception as e:
                print(f"  [CRITICAL ERROR] Unexpected error during APIJobs fetch for query {request_body}: {e}")
                import traceback
                print(traceback.format_exc())
                break # Stop processing this query, move to next config

        print(f"--- Finished query. Total jobs processed for this query: {jobs_processed_for_query} ---")

    print(f"\n--- APIJobs fetch complete. Total jobs processed overall: {total_jobs_processed_overall} ---")