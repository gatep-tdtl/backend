import re
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

model_id = "distilbert/distilgpt2"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id)
generator = pipeline("text-generation", model=model, tokenizer=tokenizer)

def get_ai_match_score(user_skills, job_skills):
    if not user_skills or not job_skills:
        return 0.0
    user_skills_set = set([s.lower() for s in user_skills])
    job_skills_set = set([s.lower() for s in job_skills])
    matched = user_skills_set.intersection(job_skills_set)
    return round(100 * len(matched) / len(job_skills_set), 2) if job_skills_set else 0.0




# def get_ai_match_score(user_skills, job_skills):
#     prompt = f"""
#     You are an expert AI assistant. Based on the following:
#     User Skills: {', '.join(user_skills)}
#     Job Skills: {', '.join(job_skills)}
#     How well do they match? Give only a percentage score between 0 and 100.
#     """

#     result = generator(prompt, max_length=50, do_sample=False, num_return_sequences=1)
#     text = result[0]['generated_text']
#     match = re.search(r'\d+\.?\d*', text)

#     try:
#         score = float(match.group(0)) if match else 0.0
#         return round(min(score, 100), 2)
#     except:
#         return 0.0