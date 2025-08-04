import json
import logging
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from groq import Groq
from talent_management.models import TrendingSkill

# Securely load API key from environment variables
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = (
        'Fetches trending skills for specified job roles from the Groq API '
        'and updates the database. Usage: python manage.py update_trending_skills "Role 1" "Role 2"'
    )

    def add_arguments(self, parser):
        # Allow the command to accept one or more role strings as arguments
        parser.add_argument(
            'roles',
            nargs='+',  # '+' means one or more arguments
            type=str,
            help='A list of job roles to fetch skills for (e.g., "AI/ML Engineer").'
        )

    def handle(self, *args, **options):
        selected_roles = options['roles']
        self.stdout.write(self.style.SUCCESS(f"Starting skill fetch for roles: {', '.join(selected_roles)}"))

        if not GROQ_API_KEY:
            self.stdout.write(self.style.ERROR('GROQ_API_KEY is not set in environment variables. Aborting.'))
            return

        # --- Dynamic Prompt Generation ---
        if len(selected_roles) == 1:
            # Prompt for a single role (expects a JSON array)
            role_str = selected_roles[0]
            prompt = (
                f"List the top 10 trending skills for a '{role_str}'. For each skill, provide "
                "demand percentage, increase over the last year (as a string like '+45%'), and priority (High/Medium/Low). "
                "Format the output as a single, raw JSON array of objects. Example: "
                '[{"skill": "Skill Name", "demand": "90%", "increase": "+30%", "priority": "High"}]'
            )
        else:
            # Prompt for multiple roles (expects a JSON object with roles as keys)
            roles_str = ", ".join(f"'{role}'" for role in selected_roles)
            prompt = (
                f"For each of the following roles: {roles_str}, list the top 10 trending skills. "
                "For each skill, include the demand percentage, increase over last year (as '+%'), and priority (High/Medium/Low). "
                "Return the response as a single, raw JSON object where keys are the role names and values are arrays of skill objects. Example: "
                '{"AI/ML Engineer": [{"skill": "MLOps", ...}], "Data Scientist": [{"skill": "Pandas", ...}]}'
            )

        # --- Call Groq API ---
        try:
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model="llama3-70b-8192",  # Using a more capable model for structured data
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"} # Use JSON mode for reliability
            )
            raw_output = response.choices[0].message.content.strip()
            skills_data = json.loads(raw_output)

        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'Failed to parse JSON from API response: {e}'))
            logger.error(f"Invalid JSON received from Groq: {raw_output}")
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred communicating with Groq API: {e}'))
            return

        # --- Process Data and Update Database ---
        skills_to_create = []
        
        # Handle the two different response formats (list for 1 role, dict for many)
        if isinstance(skills_data, list):
            # The API returned a list, meaning it was a single-role request
            role_name = selected_roles[0]
            for skill_item in skills_data:
                if skill_item.get('skill'):
                    skills_to_create.append(TrendingSkill(
                        role=role_name,
                        skill=skill_item['skill'],
                        demand=skill_item.get('demand', ''),
                        increase=skill_item.get('increase', ''),
                        priority=skill_item.get('priority', '')
                    ))
        elif isinstance(skills_data, dict):
            # The API returned a dict, likely with role names as keys
            # The key might be "trending_skills" or the direct role names. We check for both.
            if len(skills_data.keys()) == 1 and isinstance(list(skills_data.values())[0], dict):
                 # Handles responses like {"results": {"Role 1": [...], "Role 2": [...]}}
                 data_dict = list(skills_data.values())[0]
            else:
                 # Handles responses like {"Role 1": [...], "Role 2": [...]}
                 data_dict = skills_data

            for role_name, skills_list in data_dict.items():
                if role_name in selected_roles and isinstance(skills_list, list):
                    for skill_item in skills_list:
                        if skill_item.get('skill'):
                             skills_to_create.append(TrendingSkill(
                                role=role_name,
                                skill=skill_item['skill'],
                                demand=skill_item.get('demand', ''),
                                increase=skill_item.get('increase', ''),
                                priority=skill_item.get('priority', '')
                            ))
        else:
            self.stdout.write(self.style.ERROR(f"Unexpected JSON format received: {type(skills_data)}"))
            logger.error(f"Unexpected JSON format: {skills_data}")
            return

        if not skills_to_create:
            self.stdout.write(self.style.WARNING('No valid skills were found in the API response to process.'))
            return

        # Use a transaction to ensure atomicity: either all changes are saved, or none are.
        with transaction.atomic():
            # Delete ONLY the old skills for the roles we are updating
            old_skill_count = TrendingSkill.objects.filter(role__in=selected_roles).count()
            TrendingSkill.objects.filter(role__in=selected_roles).delete()
            self.stdout.write(f'Cleared {old_skill_count} old skill(s) for the specified roles.')

            # Use bulk_create for high efficiency
            TrendingSkill.objects.bulk_create(skills_to_create)
        
        self.stdout.write(self.style.SUCCESS(f'Successfully created {len(skills_to_create)} new trending skill entries.'))