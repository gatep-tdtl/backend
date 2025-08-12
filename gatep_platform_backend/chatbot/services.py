# chatbot/services.py

import json
from groq import Groq
from django.conf import settings
from django.db import connection # We might need this for schema, but prefer ORM
from talent_management.models import CustomUser, Resume
from employer_management.models import JobPosting, Company

# Initialize the Groq client using the key from Django settings
groq_client = Groq(api_key=settings.GROQ_API_KEY)

class ChatbotService:
    def __init__(self, user: CustomUser):
        """
        Initializes the service with the current user context.
        :param user: A Django CustomUser object.
        """
        self.user = user
        self.chat_history = [] # For now, history is per-instance. Can be moved to user session.

    def _get_db_schema_info(self):
        """
        Generates a simplified schema description from Django models.
        This is much safer and more abstract than raw table inspection.
        """
        schema_info = """
        Available Models and Key Fields:
        - JobPosting: title, description, requirements, responsibilities, location, job_type, experience_level, company (ForeignKey to Company), required_skills (JSON), status.
        - Company: company_name, description, industry, website, headquarters.
        - Application: job_posting (ForeignKey to JobPosting), talent (ForeignKey to CustomUser), status, application_date.
        - Resume (for the current user): name, email, phone, skills, experience, projects, preferred_tech_stack, current_location.
        """
        return schema_info

    def _get_user_profile_summary(self):
        """
        Gets a summary of the current user's profile using the Django ORM.
        """
        try:
            resume = Resume.objects.get(talent_id=self.user)
            # Create a simple string summary of the resume
            profile_parts = []
            if resume.skills: profile_parts.append(f"Skills: {resume.skills}")
            if resume.experience: profile_parts.append(f"Experience: {resume.experience}")
            if resume.preferred_tech_stack: profile_parts.append(f"Preferred Stack: {resume.preferred_tech_stack}")
            if resume.current_city: profile_parts.append(f"Location: {resume.current_city}")

            if not profile_parts:
                return "The user's resume exists but is mostly empty."
            return "User Profile Summary: " + "; ".join(profile_parts)
        except Resume.DoesNotExist:
            return "No resume found for this user."

    def _execute_query_with_orm(self, user_query: str):
        """
        This is the REPLACEMENT for your raw SQL execution.
        Instead of generating SQL, we will ask the LLM to identify the INTENT
        and then we can map that intent to an ORM query here.
        
        For this example, we'll keep it simple and just show job recommendations.
        A more advanced version would have the LLM return a structured JSON
        indicating the intent (e.g., {"intent": "find_jobs", "filters": {"tech": "Python"}}).
        """
        # This is a simplified example. In a real scenario, you'd parse the LLM's intent.
        # Let's assume any query with "job" or "hiring" is a job search.
        if "job" in user_query.lower() or "hiring" in user_query.lower() or "recommend" in user_query.lower():
            try:
                # Use the ORM to find relevant jobs.
                jobs = JobPosting.objects.filter(status='PUBLISHED', is_active=True).select_related('company').order_by('-posted_date')[:5]
                
                if not jobs.exists():
                    return {"message": "No published jobs found at the moment."}

                results = []
                for job in jobs:
                    results.append({
                        "title": job.title,
                        "company": job.company.company_name,
                        "location": job.location,
                        "description_preview": job.description[:150] + "..."
                    })
                return {"query_result": results, "message": "Here are some recent job postings."}
            except Exception as e:
                return {"error": f"An error occurred while querying jobs with the ORM: {str(e)}"}
        
        return {"message": "I can primarily help with job-related queries right now. How can I assist with that?"}


    def handle_conversation(self, user_query: str, language: str):
        """
        Main method to handle a user's query.
        """
        self.chat_history.append({"role": "user", "content": user_query})

        # Get context about the database and user
        schema_info = self._get_db_schema_info()
        user_profile_summary = self._get_user_profile_summary() if self.user.is_talent_role else "User is not a talent."

        # The system prompt is now about understanding user intent against our models, not generating SQL.
        system_prompt = f"""
        You are a helpful AI assistant for a talent platform. You respond in '{language}'.
        Your goal is to understand the user's request and provide information based on the available data.
        You should not generate SQL queries. Instead, formulate a helpful, conversational response.
        If the user asks for jobs, recommendations, or companies hiring, provide a response indicating you are searching.
        
        DATABASE CONTEXT:
        {schema_info}
        
        USER CONTEXT:
        - User's Role: {self.user.user_role}
        - {user_profile_summary}
        """
        
        # Here, we decide if we need to query the database or just chat.
        # This logic determines if we call our internal ORM-based function.
        if "job" in user_query.lower() or "recommend" in user_query.lower():
            # The user is asking for data. Use our ORM function.
            db_result = self._execute_query_with_orm(user_query)
            
            if "error" in db_result:
                return {"response": f"Sorry, I encountered an error: {db_result['error']}"}

            # Now, use the LLM to format the ORM result into a nice, conversational response.
            formatting_prompt = f"""
            Based on the user's query "{user_query}", I found the following data from the database:
            {json.dumps(db_result.get('query_result'), indent=2)}
            
            Please present this information to the user in a friendly, conversational way, in '{language}'.
            Summarize the findings. For example: "I found a few jobs that might interest you! Here they are:"
            """
            
            final_response = groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatting_prompt}
                ]
            )
            response_content = final_response.choices[0].message.content
        else:
            # For general chat, just talk to the LLM.
            chat_response = groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ]
            )
            response_content = chat_response.choices[0].message.content

        self.chat_history.append({"role": "assistant", "content": response_content})
        return {"response": response_content}