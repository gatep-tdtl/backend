# main.py
from interviewer_logic import AIInterviewer
import config
import multiprocessing
import os
import time
import sys
from cam import cleanup_proctor_files, start_proctor_camera_system # Import the function and cleanup from cam.py
from speech_utils import speak_text # Import speak_text directly

# Constants for file communication
MALPRACTICE_STATUS_FILE = "malpractice_status.txt"
IDENTITY_VERIFIED_FILE = "identity_verified.txt"

# --- Dummy cleanup_proctor_files (if cam.py is completely removed or simplified) ---
def cleanup_proctor_files():
    """Removes temporary status files."""
    files_to_remove = [MALPRACTICE_STATUS_FILE, IDENTITY_VERIFIED_FILE]
    for f in files_to_remove:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"Cleaned up {f}")
            except OSError as e:
                print(f"Error cleaning up {f}: {e}")
# --- End Dummy cleanup_proctor_files ---

def read_malpractice_status():
    """Reads the current malpractice status from the file."""
    try:
        if os.path.exists(MALPRACTICE_STATUS_FILE):
            with open(MALPRACTICE_STATUS_FILE, "r") as f:
                status = f.read().strip()
                # If camera is removed, all "TERMINATED_*" statuses other than NORMAL_EXIT indicate an issue
                # and "NO_FACE", "MULTIPLE_FACES", "GAZE_AWAY" are no longer relevant.
                if status.startswith("TERMINATED") and status != "TERMINATED_NORMAL_EXIT":
                    return status # Still report other termination reasons
                elif status == "TERMINATED_NORMAL_EXIT":
                    return status
                else: # Any other status, including camera-specific warnings, are ignored
                    return "NOT_STARTED" # Treat as ongoing or not started if not a final termination
        return "NOT_STARTED" # Default if file doesn't exist yet
    except IOError as e:
        print(f"Error reading malpractice status file: {e}")
        return "ERROR_READING_STATUS"

if __name__ == "__main__":
    # Clean up any residual files from previous runs
    cleanup_proctor_files()

    # Pre-defined inputs: position, experience, and AIML specialization
    position = "AI Engineer"
    experience = "5 years in Python, Machine Learning, NLP, Deep Learning, AWS, and Docker."
    aiml_specialization = "Computer Vision" # New hardcoded input for AIML specialization

    interview_terminated_reason = None
    proctor_process = None

    try:
        # No camera process to start, directly simulate identity verification.
        print("Camera functionality is removed. Skipping proctoring process start.")
        
        # We need to explicitly write the identity verified file as the proctor process won't.
        try:
            with open(IDENTITY_VERIFIED_FILE, "w") as f:
                f.write("verified")
            print("Identity verification simulated successfully.")
            speak_text("Identity verified. We can now proceed with the interview.")
        except IOError as e:
            print(f"Error: Could not write identity verified file: {e}")
            speak_text("Error: Could not mark identity as verified. The interview cannot proceed.")
            sys.exit(1)

        print("Identity verified. Proceeding with the interview.")
        speak_text("Identity verified. We can now proceed with the interview.")

        # Initialize the AI Interviewer with new inputs
        interviewer = AIInterviewer(position, experience, aiml_specialization) # Updated call

        # Run the interview, passing the status check function
        interviewer.run_interview(read_malpractice_status)

    except Exception as e:
        print(f"An unexpected error occurred in the main interview process: {e}")
        speak_text(f"An unexpected error occurred in the interview: {e}. The interview is ending.")
        interview_terminated_reason = f"Main interview process error: {e}"
    finally:
        # Ensure the proctor process is terminated when the main script finishes
        if proctor_process and proctor_process.is_alive():
            print("Terminating webcam proctoring process...")
            proctor_process.terminate()
            proctor_process.join() # Wait for the process to finish
            print("Webcam proctoring process terminated.")
        
        # Clean up files regardless of how the interview ended
        cleanup_proctor_files()

        if interview_terminated_reason:
            print(f"\nInterview ended prematurely. Reason: {interview_terminated_reason}")
        else:
            print("\nInterview concluded successfully.")
