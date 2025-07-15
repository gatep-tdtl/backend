# config.py

# --- Configuration ---
# Your OpenAI API Key. Set this as an environment variable or replace the placeholder.
# You can get your API key from https://platform.openai.com/account/api-keys
import os
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL_NAME = "gpt-4-turbo" # Using GPT-3.5 Turbo. You can change to "gpt-4" or other suitable models

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
# Define how many questions should be generated for each round/stage at the beginning of that round.
COMMUNICATION_QUESTIONS_COUNT = 2
PSYCHOMETRIC_QUESTIONS_COUNT = 2
TECHNICAL_QUESTIONS_PER_SPECIALIZATION_COUNT = 2 # Number of questions per identified technical specialization
CODING_PREDICT_OUTPUT_QUESTIONS_COUNT = 1
CODING_FIX_ERROR_QUESTIONS_COUNT = 1
CODING_WRITE_PROGRAM_QUESTIONS_COUNT = 1

# --- AI Conversation History Limit ---
# Define how many past conversation turns (Q&A pairs) the AI should remember for context.
# This helps manage token usage and focus the conversation.
MAX_CHAT_HISTORY_TURNS = 10 # Keep the last 10 turns (5 Q&A pairs) for context. Adjust as needed.