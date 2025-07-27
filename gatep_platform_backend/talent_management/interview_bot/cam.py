import cv2
# import tkinter as tk # Removed as file dialog is no longer needed
# from tkinter import filedialog # Removed as file dialog is no longer needed
from deepface import DeepFace
import time
import os
from datetime import datetime
import sys
import numpy as np
from speech_utils import speak_text

# Constants
SNAPSHOT_DIR = "malpractice_snapshots"
TEMP_IMAGE_PATH = "temp.jpg"
LIVE_FRAME_PATH = "live_frame.jpg"
MAX_TOTAL_WARNINGS = 3 # Maximum total warnings allowed throughout the interview
FRAME_SKIP = 3
RESIZE_SCALE = 0.5  # Reduce size for faster processing
WARNING_INTERVAL = 5  # seconds between warnings
MALPRACTICE_STATUS_FILE = "malpractice_status.txt"
IDENTITY_VERIFIED_FILE = "identity_verified.txt"
CV2_WINDOW_NAME = "Interview Monitor"

# --- NEW CONSTANTS FOR SIMPLIFIED GAZE TRACKING ---
# Threshold for horizontal deviation of eye midpoint from face center (in pixels, scaled)
# This value might need fine-tuning based on your webcam and face size.
GAZE_HORIZONTAL_DEVIATION_THRESHOLD = 20 # pixels
GAZE_WARNING_STREAK_LIMIT = 5 # How many consecutive frames before a 'gaze away' warning is issued


# Globals (will be managed within the function for multiprocessing safety)
# reference_img_path = "" # No longer needed as it's directly set in verify_identity
current_malpractice_status = "INITIAL"
total_malpractice_warnings = 0

# --- NEW GLOBALS FOR GAZE TRACKING ---
gaze_away_warnings_current_streak = 0
last_gaze_away_warning_time = time.time()


# Setup
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

def write_malpractice_status(status):
    """Writes the current malpractice status to a file."""
    global current_malpractice_status
    if current_malpractice_status != status: # Only write if status has changed
        try:
            with open(MALPRACTICE_STATUS_FILE, "w") as f:
                f.write(status)
            current_malpractice_status = status
            print(f"[Proctor Status Updated]: {status}")
        except IOError as e:
            print(f"[cam.py Error]: Could not write malpractice status file: {e}")

def cleanup_camera_and_windows(cap):
    """Releases camera and destroys all OpenCV windows."""
    if cap:
        cap.release()
    cv2.destroyAllWindows()

def cleanup_proctor_files():
    """Removes temporary status files and image files, but keeps malpractice snapshots."""
    files_to_remove = [MALPRACTICE_STATUS_FILE, IDENTITY_VERIFIED_FILE, TEMP_IMAGE_PATH, LIVE_FRAME_PATH]
    for f in files_to_remove:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"Cleaned up {f}")
            except OSError as e:
                print(f"Error cleaning up {f}: {e}")

def capture_snapshot(frame, reason):
    """Saves a frame as a JPG image with a timestamp and reason."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(SNAPSHOT_DIR, f"malpractice_{reason}_{timestamp}.jpg")
    try:
        cv2.imwrite(filename, frame)
        print(f"Snapshot captured: {filename} (Reason: {reason})")
    except Exception as e:
        print(f"Error capturing snapshot {filename}: {e}")

def verify_identity(cap): # reference_img_path_local removed from params
    """
    Handles identity verification at the start of the interview.
    Uses a predefined local image for verification.
    """
    global total_malpractice_warnings

    # --- MODIFIED: Use a local reference image instead of file dialog ---
    reference_img_path_local = "test.jpg" # <--- Set your reference image filename here!

    if not os.path.exists(reference_img_path_local):
        print(f"Error: Reference image '{reference_img_path_local}' not found in the current directory. Please place your reference image here.")
        speak_text(f"Error: Reference image not found. Please place the image named reference_image.jpg in the same folder as this script. Exiting interview.")
        write_malpractice_status("TERMINATED_REFERENCE_IMAGE_NOT_FOUND")
        cleanup_camera_and_windows(cap)
        sys.exit(1)
    # --- END MODIFIED ---

    try:
        # Verify the reference image itself has a face
        DeepFace.extract_faces(img_path=reference_img_path_local, enforce_detection=True)
        print(f"Reference image loaded from: {reference_img_path_local}")
    except Exception as e:
        print(f"Error: No face detected in the selected reference image '{reference_img_path_local}'. Please ensure it clearly shows a single face.")
        speak_text(f"Error: No face detected in the reference image. Please ensure it clearly shows a single face. Exiting interview.")
        write_malpractice_status("TERMINATED_INVALID_REFERENCE_IMAGE")
        cleanup_camera_and_windows(cap)
        sys.exit(1)

    face_verified = False
    verification_attempts = 0
    max_verification_attempts = 5 # Give a few attempts for verification
    last_verification_warning_time = time.time()
    verification_warning_interval = 10 # seconds

    print("Please look at the camera for identity verification...")
    speak_text("Please look at the camera for identity verification.")

    while not face_verified and verification_attempts < max_verification_attempts:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame during verification.")
            speak_text("Failed to access camera during verification. Exiting.")
            write_malpractice_status("TERMINATED_CAMERA_ERROR_VERIFICATION")
            cleanup_camera_and_windows(cap)
            sys.exit(1)

        small_frame = cv2.resize(frame, (0, 0), fx=RESIZE_SCALE, fy=RESIZE_SCALE)
        # Flip frame horizontally for selfie-view
        small_frame = cv2.flip(small_frame, 1)
        display_frame = frame.copy() # Use original size for display

        try:
            # Perform identity verification
            result = DeepFace.verify(
                img1_path=reference_img_path_local,
                img2_path=small_frame,
                model_name="VGG-Face",
                distance_metric="cosine",
                enforce_detection=False # Set to False to handle no face scenario gracefully
            )
            face_verified = result['verified']

            if not face_verified:
                if time.time() - last_verification_warning_time > verification_warning_interval:
                    print(f"Identity mismatch. Please ensure your face is clearly visible. Attempt {verification_attempts+1}/{max_verification_attempts}")
                    speak_text(f"Identity mismatch. Please ensure your face is clearly visible. Attempt {verification_attempts+1} of {max_verification_attempts}.")
                    capture_snapshot(display_frame, "IDENTITY_MISMATCH")
                    total_malpractice_warnings += 1
                    last_verification_warning_time = time.time()
                verification_attempts += 1
            else:
                print("Identity verified successfully!")
                break

        except Exception as e:
            if "Face could not be detected" in str(e):
                if time.time() - last_verification_warning_time > verification_warning_interval:
                    print(f"No face detected for verification. Please look at the camera. Attempt {verification_attempts+1}/{max_verification_attempts}")
                    speak_text(f"No face detected for verification. Please look at the camera. Attempt {verification_attempts+1} of {max_verification_attempts}.")
                    capture_snapshot(display_frame, "NO_FACE_VERIFICATION")
                    total_malpractice_warnings += 1
                    last_verification_warning_time = time.time()
            else:
                print(f"Error during identity verification: {e}")
                if time.time() - last_verification_warning_time > verification_warning_interval:
                    speak_text(f"Error during verification: {e}. Attempt {verification_attempts+1} of {max_verification_attempts}.")
                    total_malpractice_warnings += 1
                    last_verification_warning_time = time.time()
            verification_attempts += 1

        if total_malpractice_warnings >= MAX_TOTAL_WARNINGS:
            print("Too many warnings during verification. Terminating interview.")
            speak_text("Too many warnings during verification. Terminating interview.")
            write_malpractice_status("TERMINATED_TOO_MANY_WARNINGS_VERIFICATION")
            cleanup_camera_and_windows(cap)
            sys.exit(1)

        cv2.putText(display_frame, "Identity Verification - Look at Camera", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2, cv2.LINE_AA)
        status_text = "Status: Verified" if face_verified else f"Status: Not Verified ({verification_attempts}/{max_verification_attempts})"
        cv2.putText(display_frame, status_text, (50, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow(CV2_WINDOW_NAME, display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            write_malpractice_status("TERMINATED_MANUAL_QUIT_KEY_VERIFICATION")
            print("Verification manually terminated by 'q' key.")
            cleanup_camera_and_windows(cap)
            sys.exit(0)

    if not face_verified:
        print("Failed to verify identity after multiple attempts. Terminating interview.")
        speak_text("Failed to verify identity. Terminating interview.")
        write_malpractice_status("TERMINATED_IDENTITY_FAILURE")
        cleanup_camera_and_windows(cap)
        sys.exit(1)

def monitor_user(cap):
    """Continuously monitors the user for malpractice during the interview."""
    global total_malpractice_warnings, last_gaze_away_warning_time, gaze_away_warnings_current_streak
    frame_count = 0
    no_face_warnings_current_streak = 0
    multiple_faces_warnings_current_streak = 0
    last_no_face_warning_time = time.time()
    last_multiple_faces_warning_time = time.time()

    print("Proctoring: Monitoring user during interview...")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame during monitoring.")
            write_malpractice_status("TERMINATED_CAMERA_ERROR_MONITORING")
            break

        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            continue

        small_frame = cv2.resize(frame, (0, 0), fx=RESIZE_SCALE, fy=RESIZE_SCALE)
        small_frame = cv2.flip(small_frame, 1) # Flip horizontally for selfie-view
        display_frame = frame.copy() # Use original size for display

        faces = []
        try:
            detected_faces_info = DeepFace.extract_faces(img_path=small_frame, enforce_detection=False, detector_backend='mediapipe')
            
            if detected_faces_info:
                # Filter out non-face detections if any, and extract facial_area for drawing
                faces = [f['facial_area'] for f in detected_faces_info if f is not None]

                # --- SIMPLIFIED GAZE TRACKING LOGIC ---
                if len(detected_faces_info) == 1:
                    face_area = detected_faces_info[0]['facial_area']
                    
                    # Ensure eye landmarks are present
                    if 'left_eye' in face_area and 'right_eye' in face_area:
                        left_eye_x, _ = face_area['left_eye']
                        right_eye_x, _ = face_area['right_eye']
                        
                        face_center_x = face_area['x'] + face_area['w'] / 2
                        eye_midpoint_x = (left_eye_x + right_eye_x) / 2
                        
                        # Calculate horizontal deviation from face center
                        deviation = abs(eye_midpoint_x - face_center_x)
                        
                        if deviation > GAZE_HORIZONTAL_DEVIATION_THRESHOLD:
                            gaze_away_warnings_current_streak += 1
                            if gaze_away_warnings_current_streak >= GAZE_WARNING_STREAK_LIMIT and \
                               time.time() - last_gaze_away_warning_time > WARNING_INTERVAL:
                                print(f"Warning: User looking away from screen (Horizontal Deviation: {deviation:.2f} pixels).")
                                speak_text("Please look at the screen. You appear to be looking away.")
                                capture_snapshot(display_frame, "GAZE_AWAY")
                                total_malpractice_warnings += 1
                                last_gaze_away_warning_time = time.time()
                                gaze_away_warnings_current_streak = 0 # Reset streak after warning
                        else:
                            gaze_away_warnings_current_streak = 0 # Reset streak if looking straight
                    else:
                        gaze_away_warnings_current_streak = 0 # No eye landmarks for gaze tracking
                else:
                    gaze_away_warnings_current_streak = 0 # Not exactly one face for gaze tracking

        except Exception as e:
            faces = [] # Ensure faces is empty if an error occurs

        num_faces = len(faces)

        current_status = "OK"
        if num_faces == 0:
            no_face_warnings_current_streak += 1
            if no_face_warnings_current_streak >= GAZE_WARNING_STREAK_LIMIT and \
               time.time() - last_no_face_warning_time > WARNING_INTERVAL:
                current_status = "NO_FACE"
                print("Warning: No face detected.")
                speak_text("Warning: No face detected. Please ensure your face is visible.")
                capture_snapshot(display_frame, "NO_FACE")
                total_malpractice_warnings += 1
                last_no_face_warning_time = time.time()
                no_face_warnings_current_streak = 0 # Reset streak after warning
        else:
            no_face_warnings_current_streak = 0

        if num_faces > 1:
            multiple_faces_warnings_current_streak += 1
            if multiple_faces_warnings_current_streak >= GAZE_WARNING_STREAK_LIMIT and \
               time.time() - last_multiple_faces_warning_time > WARNING_INTERVAL:
                current_status = "MULTIPLE_FACES"
                print(f"Warning: {num_faces} faces detected. Only one person should be present.")
                speak_text("Warning: Multiple faces detected. Only one person should be present during the interview.")
                capture_snapshot(display_frame, "MULTIPLE_FACES")
                total_malpractice_warnings += 1
                last_multiple_faces_warning_time = time.time()
                multiple_faces_warnings_current_streak = 0 # Reset streak after warning
        else:
            multiple_faces_warnings_current_streak = 0

        # Update status file if there's a critical warning or if it returns to OK
        if current_status != "OK":
            write_malpractice_status(current_status)
        elif total_malpractice_warnings >= MAX_TOTAL_WARNINGS:
             write_malpractice_status("TERMINATED_TOO_MANY_WARNINGS")
        elif gaze_away_warnings_current_streak >= GAZE_WARNING_STREAK_LIMIT and \
             time.time() - last_gaze_away_warning_time > WARNING_INTERVAL:
             write_malpractice_status("GAZE_AWAY") # This will trigger the write if gaze is away
        else:
            write_malpractice_status("OK") # Ensure status goes back to OK if issues resolve

        # Display current status on the frame
        cv2.putText(display_frame, f"Faces: {num_faces}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(display_frame, f"Total Warnings: {total_malpractice_warnings}/{MAX_TOTAL_WARNINGS}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(display_frame, f"Status: {current_status}", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)

        cv2.imshow(CV2_WINDOW_NAME, display_frame)

        # Check for termination conditions
        if total_malpractice_warnings >= MAX_TOTAL_WARNINGS:
            print("Total malpractice warnings exceeded. Terminating interview.")
            speak_text("Total malpractice warnings exceeded. Terminating interview.")
            write_malpractice_status("TERMINATED_TOO_MANY_WARNINGS")
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            write_malpractice_status("TERMINATED_MANUAL_QUIT_KEY_MONITORING")
            print("Monitoring manually terminated by 'q' key.")
            break

    cleanup_camera_and_windows(cap)
    sys.exit(1)

def start_proctor_camera_system():
    """Main function to start the proctoring camera system."""
    # reference_img_path global is no longer used for verification, directly set in verify_identity
    cap = None
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise IOError("Cannot open webcam")

        verify_identity(cap) # Call without reference_img_path_local param

    except Exception as e:
        print(f"[cam.py Error]: An unexpected error occurred: {e}")
        write_malpractice_status("TERMINATED_UNEXPECTED_ERROR_PROCTOR")
        cleanup_camera_and_windows(cap)
        sys.exit(1)
    
    print("Identity verified! Starting interview and monitoring...")
    try:
        with open(IDENTITY_VERIFIED_FILE, "w") as f:
            f.write("verified")
    except IOError as e:
        print(f"[cam.py Error]: Could not write identity verified file: {e}")
        write_malpractice_status("TERMINATED_FILE_WRITE_ERROR")
        cleanup_camera_and_windows(cap)
        sys.exit(1)

    monitor_user(cap)

if __name__ == '__main__':
    start_proctor_camera_system()