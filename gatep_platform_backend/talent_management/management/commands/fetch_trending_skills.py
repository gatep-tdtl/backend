import json
import logging
import os
from django.core.management.base import BaseCommand
# from gatep_platform_config.settings import GROQ_API_KEY
from groq import Groq
from talent_management.models import TrendingSkill

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetches trending AI/ML skills from the Groq API and updates the database.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to fetch trending skills from Groq API...'))

        if not GROQ_API_KEY:
            self.stdout.write(self.style.ERROR('GROQ_API_KEY is not set. Aborting.'))
            return

        try:
            client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                "Give me the top 10 trending AI/ML deployment & engineering skills "
                "with demand percentage, increase over last year (as a string like '+45%'), and priority (High/Medium/Low). "
                "Return ONLY the raw JSON array, without any explanations or markdown. The format must be exactly: "
                "[{\"skill\": \"Skill Name\", \"demand\": \"95%\", \"increase\": \"+45%\", \"priority\": \"High\"}, ...]"
            )
            
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_output = response.choices[0].message.content.strip()
            data = json.loads(raw_output)

            skills_list = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])

            if not skills_list:
                self.stdout.write(self.style.ERROR('Could not find a list of skills in the JSON response.'))
                logger.error(f"Could not find list in Groq response: {raw_output}")
                return

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred communicating with Groq API: {e}'))
            return

        TrendingSkill.objects.all().delete()
        self.stdout.write('Cleared old trending skills from the database.')

        created_count = 0
        for skill_data in skills_list:
            if skill_data.get('skill'):
                TrendingSkill.objects.create(
                    skill=skill_data['skill'],
                    demand=skill_data.get('demand', ''),
                    increase=skill_data.get('increase', ''),
                    priority=skill_data.get('priority', '')
                )
                created_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully created {created_count} new trending skill entries.'))