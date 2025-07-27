# config.py

# --- Configuration ---
# Your Groq API Key. Set this as an environment variable or replace the placeholder.
# You can get your API key from https://console.groq.com/keys


import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions" # Groq's OpenAI-compatible endpoint
GROQ_MODEL_NAME = "llama3-8b-8192" # Using Llama 3 8B. You can change to "mixtral-8x7b-32768" or other suitable Groq models

# Define the default mock interview position
MOCK_INTERVIEW_POSITION = "AI Engineer" # Added this line

# --- Round Time Limits (in seconds) ---
# Define the maximum duration for each interview round.
# The timer for a round starts at the beginning of the round and checks before each question.
# If the time is exceeded, the round ends prematurely.
ROUND_TIME_LIMITS = {
    "communication": 300,  # 5 minutes
    "psychometric": 300,   # 5 minutes
    "coding": 300,         # 5 minutes (for all coding stages combined)
    "technical": 300       # 5 minutes (for all technical specializations combined)
}

# --- Number of Questions per Round/Stage ---
# Define how many questions should be generated for each round/stage.
# These values are used during the pre-generation phase.
NUM_COMMUNICATION_QUESTIONS = 2
NUM_PSYCHOMETRIC_QUESTIONS = 2
NUM_TECHNICAL_QUESTIONS_PER_SPECIALIZATION = 2 # Per identified specialization (e.g., 2 for ML, 2 for NLP)
NUM_CODING_PREDICT_OUTPUT_QUESTIONS = 1
NUM_CODING_FIX_ERROR_QUESTIONS = 1
NUM_CODING_WRITE_PROGRAM_QUESTIONS = 1

# --- Malpractice Detection Thresholds ---
# Define thresholds for flagging potential malpractice.
# These are example values and may need tuning based on your proctoring system's output.
MALPRACTICE_CONFIDENCE_THRESHOLD = 0.7 # Confidence score above which a detection is considered malpractice
MALPRACTICE_STRIKES_LIMIT = 3 # Number of malpractice incidents before termination

# --- AI Scoring Configuration ---
# You can define specific prompts or parameters for scoring here if needed
# For now, scoring prompts are embedded in interviewer_logic.py
