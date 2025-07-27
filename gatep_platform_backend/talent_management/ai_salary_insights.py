# talent_management/ai_salary_insights.py
import json
import re
import logging
from django.conf import settings
from groq import Groq

# Configure logging
logger = logging.getLogger(__name__)

# Constants
MODEL_NAME = "llama3-70b-8192"
CURRENCY_TO_INR = {
    "AED": 22.6,
    "USD": 83.5,
    "EUR": 91.3,
    "SGD": 62.3
}

def _convert_to_inr_lpa(amount, currency):
    """Helper function to convert local currency to INR Lakhs Per Annum."""
    rate = CURRENCY_TO_INR.get(currency.upper(), 0)
    if rate == 0:
        logger.warning(f"No conversion rate found for currency '{currency}'.")
        return "N/A"
    try:
        clean_amount = str(amount).replace(',', '').strip()
        multiplier = 1
        if re.search(r'[Kk]', clean_amount):
            multiplier = 1000
            clean_amount = re.sub(r'[^\d.]', '', clean_amount)
        else:
            clean_amount = re.sub(r'[^\d.]', '', clean_amount)

        amount_numeric = float(clean_amount) * multiplier
        inr = amount_numeric * rate
        return f"{round(inr / 100000, 2)} LPA"
    except (ValueError, TypeError):
        logger.error(f"Could not convert amount '{amount}' to INR for currency '{currency}'.")
        return "N/A"

def generate_salary_insights(cities, roles):
    """
    Calls the Groq API to generate salary insights and processes the response.
    """
    groq_api_key = getattr(settings, 'GROQ_API_KEY', None)
    if not groq_api_key:
        logger.error("GROQ_API_KEY not found in Django settings.")
        return None

    try:
        client = Groq(api_key=groq_api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        return None

    prompt = f"""
You are a salary insights expert. Based on market research and analysis, generate a structured JSON report wrapped in a top-level key called "salary_insights".

The JSON must contain:

1. "location_based": a list of cities (from {cities}) with salary figures:
   - city
   - min_salary in local currency (e.g., min_salary_AED/year)
   - median_salary
   - max_salary

2. "salary_insights_summary": for each role in {roles}:
   - role
   - demand_in_salary_percent (range 10–100%)

3. "negotiation_tips": 4 realistic, actionable bullet points for salary negotiation in tech.

4. "market_trends": 3–4 trends with:
   - trend (title)
   - insight (short explanation and impact)

Use currencies:
- UAE → AED/year
- USA → USD/year
- EU → EUR/year
- Singapore → SGD/year

Only provide valid JSON. No explanations. Format numbers like: $120K, AED 250K, €85K, S$100K.
Cities: {', '.join(cities)}
Roles: {', '.join(roles)}
"""
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = res.choices[0].message.content

        # Extract valid JSON from the model's response
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            logger.warning("No JSON object found in the AI model's response.")
            logger.debug(f"Raw response: {response_text}")
            return None

        insights = json.loads(json_match.group(0))

        # Post-process: Convert salaries to INR
        for loc in insights.get("salary_insights", {}).get("location_based", []):
            currency = None
            keys = list(loc.keys())

            # Dynamically find the currency from keys like 'min_salary_AED/year'
            for key in keys:
                if "min_salary_" in key:
                    currency_match = re.search(r'min_salary_([A-Z]{3})', key)
                    if currency_match:
                        currency = currency_match.group(1)
                        break
            
            if not currency:
                continue

            # Add INR conversions
            if f'min_salary_{currency}/year' in loc:
                loc['in_INR_min'] = _convert_to_inr_lpa(loc[f'min_salary_{currency}/year'], currency)
            if 'median_salary' in loc:
                loc['in_INR_median'] = _convert_to_inr_lpa(loc['median_salary'], currency)
            if f'max_salary_{currency}/year' in loc:
                loc['in_INR_max'] = _convert_to_inr_lpa(loc[f'max_salary_{currency}/year'], currency)
        
        return insights

    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error from AI response: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during AI call: {e}")
        return None