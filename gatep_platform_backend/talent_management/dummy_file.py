#pip install transformers accelerate
 
import json
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import re # Import regex library
 
# ---------------------- Load Model from Hugging Face ----------------------
# Using a publicly available model that doesn't require authentication
model_id = "distilbert/distilgpt2"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id)
 
generator = pipeline("text-generation", model=model, tokenizer=tokenizer)
 
# ---------------------- Sample User Skills (from Skills Passport) ----------------------
user_skills = ["Machine Learning", "Deep Learning", "NLP", "Computer Vision", "MLOps",
               "TensorFlow", "PyTorch", "Scikit-learn", "Keras"]
 
# ---------------------- Sample Jobs Posted by Employers (On-platform) ----------------------
jobs_data = [
    {
        "id": 1,
        "title": "Senior AI Engineer",
        "company": "Tech Innovations UAE",
        "location": "Dubai, UAE",
        "salary": "$80,000 - $120,000",
        "employment_type": "Full-time",
        "posted_date": '16/06/2025',
        "required_skills": ["Python", "TensorFlow", "PyTorch"],
        "apply_link": "https://yourplatform.com/jobs/1"
    },
    {
        "id": 2,
        "title": "Machine Learning Specialist",
        "company": "DataCorp USA",
        "location": "San Francisco, USA",
        "salary": "$100,000 - $150,000",
        "employment_type": "Full-time",
        "posted_date": '16/06/2025',
        "required_skills": ["Python", "Scikit-learn", "Pandas"],
        "apply_link": "https://yourplatform.com/jobs/2"
    },
    {
        "id": 3,
        "title": "NLP Research Scientist",
        "company": "AI Research Lab",
        "location": "London, UK",
        "salary": "£70,000 - £100,000",
        "employment_type": "Full-time",
        "posted_date": '16/06/2025',
        "required_skills": ["Python", "NLP", "Transformers"],
        "apply_link": "https://yourplatform.com/jobs/3"
    }
]
 
# ---------------------- AI Match Score via LLama Model ----------------------
def get_ai_match_score(user_skills, job_skills):
    prompt = f"""
    You are an expert AI assistant. Based on the following information:
    User Skills: {', '.join(user_skills)}
    Job Required Skills: {', '.join(job_skills)}
    Calculate how well the user's skills match this job.
    Provide only a percentage match score between 0 and 100.
    """
 
    result = generator(prompt, max_length=50, do_sample=False, num_return_sequences=1) # Added num_return_sequences
    score_text = result[0]['generated_text'].split('\n')[0].strip()
 
    # Extract number from output text using regex
    match = re.search(r'\d+\.?\d*', score_text) # Use regex to find number
 
    try:
        if match:
            score = float(match.group(0)) # Get the matched number
            if score > 100: score = 100  # Clamp to 100 max
        else:
            score = 0.0 # fallback in case parsing fails
    except:
        score = 0.0  # fallback in case parsing fails
 
 
    return round(score, 2)
 
# ---------------------- Display Matched Jobs ----------------------
def show_matched_jobs(user_skills, jobs_data):
    print("\n======= Matched Jobs Based on AI Model =======\n")
    for job in jobs_data:
        score = get_ai_match_score(user_skills, job['required_skills'])
        print(f"Job Title      : {job['title']}")
        print(f"Company        : {job['company']}")
        print(f"Location       : {job['location']}")
        print(f"Salary         : {job['salary']}")
        print(f"Employment     : {job['employment_type']}")
        print(f"Posted date    : {job['posted_date']} ")
        print(f"AI Match Score : {score}%")
        print(f"Required Skills: {', '.join(job['required_skills'])}")
        print(f"Apply Link     : {job['apply_link']}")
        print("-" * 60)
 
# Run the matcher
show_matched_jobs(user_skills, jobs_data)
 
print("\nAll jobs displayed with AI Match Scores and Apply Links!")