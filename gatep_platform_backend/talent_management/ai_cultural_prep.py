# from groq import Groq
# import os
# import json
# import re
# from django.core.exceptions import ImproperlyConfigured

# # Use the GROQ_API_KEY from your .env file
# GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
# if not GROQ_API_KEY:
#     raise ImproperlyConfigured("The GROQ_API_KEY environment variable is not set!")

# client = Groq(api_key=GROQ_API_KEY)
# MODEL_NAME = "llama3-70b-8192"

# def generate_cultural_preparation(countries: list[str]) -> dict | None:
#     """
#     Generates cultural preparation insights for a list of countries using Groq's Llama3.
#     """
#     prompt = f"""
# You are an international career advisor. Create structured JSON content to help users prepare culturally when relocating or working in {countries}.

# Wrap the output in a top-level key called "cultural_preparation".

# For each country in {countries}, provide:
# - "country": Name of the country
# - "cultural_insights": 2–3 unique observations about working culture, social behaviors, and local expectations.
# - "communication_tips": 2–3 practical tips for professional communication in that country.
# - "work_etiquette": 2–3 essential dos and don'ts in professional settings.
# - "language_support": Mention:
#     - "official_language"
#     - "business_language" (if different)
#     - "is_english_sufficient" (true/false)
#     - "translation_tools" (list 2 recommended apps/tools)

# Constraints:
# - Do NOT repeat generic info.
# - Ensure information is specific to each country.
# - Format output strictly as valid JSON only.
# - Be concise but informative.

# Countries: {', '.join(countries)}
# """
#     try:
#         res = client.chat.completions.create(
#             model=MODEL_NAME,
#             messages=[{"role": "user", "content": prompt}]
#         )
#         response_text = res.choices[0].message.content
#     except Exception as e:
#         print(f"Error calling Groq API: {e}")
#         return None # Return None on API call failure

#     # Extract JSON from the response
#     json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
#     if json_match:
#         try:
#             return json.loads(json_match.group(0))
#         except json.JSONDecodeError as e:
#             print(f"JSON Decode Error: {e}")
#             print(f"Raw JSON from model: {json_match.group(0)}")
#             return None
#     else:
#         print("No JSON found in model response.")
#         print(f"Raw response: {response_text}")
#         return None



# ai_cultural_prep.py

import os
import json
import re
from groq import Groq
from django.core.exceptions import ImproperlyConfigured

# --- Configuration ---
# Keep loading the key securely from environment variables
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ImproperlyConfigured("The GROQ_API_KEY environment variable is not set!")

client = Groq(api_key=GROQ_API_KEY)
MODEL_NAME = "llama3-70b-8192"


# --- Helper Function (from your new code) ---
def extract_unique_locations(locations_list: list[str]) -> list[str]:
    """Deduplicates and cleans a list of location strings."""
    # Using a set for efficient deduplication
    unique_locations = {loc.strip() for loc in locations_list if loc and loc.strip()}
    return sorted(list(unique_locations)) # Sorting ensures consistent cache keys


# --- Main AI Generation Function (Combined & Improved) ---
def generate_cultural_preparation(locations: list[str]) -> dict | None:
    """
    Generates cultural preparation insights for a list of locations using Groq's Llama3.
    """
    if not locations:
        return None

    prompt = f"""
You are an international career advisor. Create structured JSON content to help users prepare culturally when relocating or working in the following locations.

Wrap the output in a top-level key called "cultural_preparation".

For each location in {locations}, provide:
- "location_name": Name of the location (country or city)
- "country": The country this location belongs to.
- "cultural_insights": 2–3 unique observations about working culture, social behaviors, and local expectations.
- "communication_tips": 2–3 practical tips for professional communication.
- "work_etiquette": 2–3 essential dos and don'ts in professional settings.
- "language_support": Mention:
    - "official_language"
    - "business_language" (if different)
    - "is_english_sufficient" (true/false)
    - "translation_tools" (list 2 recommended apps/tools)

Constraints:
- Do NOT repeat generic info.
- Ensure information is specific and relevant to each location. For cities, provide city-specific details where possible.
- Format output strictly as valid JSON only.
- Be concise but informative.

Locations: {', '.join(locations)}
"""
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} # Use JSON mode for reliability
        )
        response_text = res.choices[0].message.content
    except Exception as e:
        # Keep this robust error handling for API failures
        print(f"Error calling Groq API: {e}")
        return None

    # Parsing the JSON response
    try:
        # Llama3 with json_object mode usually returns clean JSON
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        # Fallback to regex if the model doesn't respect JSON mode perfectly
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError as e2:
                print(f"JSON Decode Error on regex fallback: {e2}")
                print(f"Raw JSON from model: {json_match.group(0)}")
                return None
    
    print("No valid JSON found in model response.")
    print(f"Raw response: {response_text}")
    return None