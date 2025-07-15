# main.py
import sys
import os
import multiprocessing # Still needed if you intend to run other processes in the future, but not for proctoring now
import time

# Add the current directory to sys.path to allow direct imports of local modules
# This helps Python find modules like 'interviewer_logic', 'config', etc. when main.py is run directly.
sys.path.append(os.path.dirname(__file__))

from interviewer_logic import AIInterviewer
import config # Import config to access OPENAI_MODEL_NAME for the print statement
from speech_utils import speak_text # Import speak_text directly

# --- Removed: Constants for file communication related to camera/proctoring ---
# MALPRACTICE_STATUS_FILE = "malpractice_status.txt"
# IDENTITY_VERIFIED_FILE = "identity_verified.txt"

# --- Removed: Function to read malpractice status (no longer needed) ---
# def read_malpractice_status():
#     try:
#         if os.path.exists(MALPRACTICE_STATUS_FILE):
#             with open(MALPRACTICE_STATUS_FILE, "r") as f:
#                 return f.read().strip()
#         return "NOT_STARTED" # Default if file doesn't exist yet
#     except IOError as e:
#         print(f"Error reading malpractice status file: {e}")
#         return "ERROR_READING_STATUS"

# --- Removed: Cleanup function from cam.py, as cam.py is removed ---
# def cleanup_proctor_files():
#     # This function was from cam.py, which is now removed.
#     # You might want to keep a generic cleanup for 'pre_generated_questions.json'
#     # and 'interview_results.json' if you want them cleaned on each run.
#     # For now, assuming you'll manage those files.
#     pass # Placeholder for now

if __name__ == "__main__":
    # Removed: Clean up any residual files from previous camera runs
    # cleanup_proctor_files() # This call is removed because the function is gone.

    # Pre-defined job_desc, user_skills, position for testing
    job_desc = """
We are looking for an AI Engineer to design and deploy NLP models, fine-tune transformers, and implement model monitoring in production environments.
The role requires experience with Python, Hugging Face, Docker, AWS, and REST API development.
    """
    user_skills = ["Python", "Machine Learning", "Deep Learning", "NLP", "PyTorch", "TensorFlow"]
    position = "AI Engineer"

    # Initialize the AI Interviewer
    interviewer = AIInterviewer(job_desc, user_skills, position)
    print(f"\n--- Starting AI Interview for {position} ---")
    speak_text(f"Welcome to the AI Interview for the {position} role.")
    speak_text("Let's begin!")

    # Removed: Proctoring process initialization and checks
    # proctor_process = None # This variable is no longer needed
    interview_terminated_reason = None # Initialize as None, will be set only on AI interview termination

    try:
        # No camera or proctoring process to start here.
        # Identity verification and malpractice status will be handled by the frontend
        # and communicated to the backend via API calls (not directly in this script).

        # Main interview loop
        interviewer.start_interview() # This method contains the conversational logic

        # After interview completes successfully or naturally terminates
        if interviewer.interview_finished:
            print("\nInterview process completed by AI.")
            speak_text("The interview has concluded. Thank you for your time.")
        else:
            # This branch might be less likely if start_interview() fully runs,
            # but good for explicit termination from within interviewer_logic
            interview_terminated_reason = "Interview terminated by AI logic (e.g., all questions asked or time limit reached)."
            print(f"\nInterview ended. Reason: {interview_terminated_reason}")

        # Removed: Malpractice detection from main.py's perspective
        # if interviewer.malpractice_detected:
        #     interview_terminated_reason = f"Interview terminated due to proctoring violation: {interviewer.malpractice_reason.replace('TERMINATED_', '').replace('_', ' ').title()}"
        #     print(f"\n{interview_terminated_reason}")
        #     speak_text(f"The interview has been terminated due to: {interviewer.malpractice_reason.replace('TERMINATED_', '').replace('_', ' ').title()}")
        #     sys.exit(1) # Explicitly exit the main process

    except Exception as e:
        print(f"An unexpected error occurred in the main interview process: {e}")
        speak_text(f"An unexpected error occurred in the interview: {e}. The interview is ending.")
        interview_terminated_reason = f"Main interview process error: {e}"
    finally:
        # Removed: Ensure the proctor process is terminated when the main script finishes
        # if proctor_process and proctor_process.is_alive():
        #     print("Terminating webcam proctoring process...")
        #     proctor_process.terminate()
        #     proctor_process.join() # Wait for the process to finish
        #     print("Webcam proctoring process terminated.")

        # Removed: Call to cleanup_proctor_files()
        # cleanup_proctor_files()

        if interview_terminated_reason:
            print(f"\nInterview ended prematurely. Reason: {interview_terminated_reason}")
        else:
            print("\nInterview concluded successfully.")