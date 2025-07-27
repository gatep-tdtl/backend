# talent_management/interview_bot/speech_utils.py

# import speech_recognition as sr # Speech-to-Text library (not needed for backend API)
# import pyttsx3 # Text-to-Speech library (not needed for backend API voice output)

# --- Speech Engine Initialization ---
# This block initializes the Text-to-Speech engine for the bot's voice.
# We will explicitly disable pyttsx3's active voice output on the backend
# because it conflicts with Django's event loop.
# The frontend will handle actual voice output.
engine = None # Explicitly set engine to None for backend
# recognizer = sr.Recognizer() # Keep recognizer for potential STT if needed for internal analysis (though frontend provides text)

def speak_text(text):
    """
    Converts text to speech using pyttsx3.
    On the backend, this will only print to console to avoid event loop conflicts.
    """
    print(f"Bot says (Backend): {text}") # Always print on backend

# REMOVED: listen_for_answer and listen_and_confirm_answer are no longer needed
# as the answer text is received directly via the API from the frontend.
