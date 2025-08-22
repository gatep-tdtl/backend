# # --- START OF FILE interview_cam.py ---

# import cv2
# import torch
# from deepface import DeepFace
# import mediapipe as mp
# import numpy as np
# import os

# # ===================== Models ===================== #
# # YOLOv5 model for object detection (phones, etc.)
# print("Loading YOLOv5 model for object detection...")
# model = torch.hub.load('ultralytics/yolov5', 'yolov5s', trust_repo=True)
# print("YOLOv5 model loaded.")
 
# # MediaPipe setup
# mp_face_mesh = mp.solutions.face_mesh
# mp_face_det = mp.solutions.face_detection
 
 
# # ===================== STEP 0: Face Visibility ===================== #
# def is_face_visible(image_path):
#     """
#     Returns (visible: bool, message: str|None)
#     """
#     image = cv2.imread(image_path)
#     if image is None:
#         return False, "Image not found ❌"
 
#     with mp_face_det.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
#         results = face_detection.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
#         if results.detections and len(results.detections) > 0:
#             return True, None
#         else:
#             return False, "Face not visible (blurry/obstructed) ❌"
 
 
# # ===================== STEP 1: Face Match (DeepFace) ===================== #
# def verify_face_match(resume_photo_path, interview_photo_path):
#     """
#     Returns dict with keys: verified(bool), model(str), or {'error': ...}
#     """
#     try:
#         result = DeepFace.verify(
#             img1_path=resume_photo_path,
#             img2_path=interview_photo_path,
#             model_name='ArcFace',
#             detector_backend='retinaface',
#             distance_metric='cosine',
#             enforce_detection=True
#         )
#         return {
#             "verified": result.get("verified", False),
#             "model": result.get("model")
#         }
#     except Exception as e:
#         return {"error": str(e)}
 
 
# # ===================== STEP 2: Orientation Rules ===================== #
# def check_face_orientation(image_path,
#                            yaw_thresh=0.06,
#                            down_thresh=0.15):
#     """
#     Returns (allowed: bool, msg: str)
#     """
#     image = cv2.imread(image_path)
#     if image is None:
#         return False, "Image not found ❌"
 
#     with mp_face_mesh.FaceMesh(static_image_mode=True,
#                                max_num_faces=1,
#                                refine_landmarks=True,
#                                min_detection_confidence=0.5) as face_mesh:
#         results = face_mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
#         if not results.multi_face_landmarks:
#             return False, "No face detected ❌"
 
#         lm = results.multi_face_landmarks[0].landmark
 
#         # Key landmarks
#         nose_tip = lm[1]
#         left_eye = lm[33]
#         right_eye = lm[263]
#         chin = lm[152]
 
#         # Pitch (up/down)
#         vert_ratio = (chin.y - nose_tip.y)
 
#         # Yaw (left/right)
#         eye_dist = abs(right_eye.x - left_eye.x) + 1e-6
#         center_x = (left_eye.x + right_eye.x) / 2.0
#         nose_offset = (nose_tip.x - center_x) / eye_dist  # signed
 
#         debug_msg = f"(yaw={nose_offset:.3f}, pitch={vert_ratio:.3f})"
 
#         # ---- PRIORITY: yaw first ----
#         if nose_offset > yaw_thresh:
#             return False, f"Face looking right ❌ {debug_msg}"
#         if nose_offset < -yaw_thresh:
#             return False, f"Face looking left ❌ {debug_msg}"
 
#         # ---- Then pitch ----
#         if vert_ratio > down_thresh:
#             return True, f"Looking down allowed ✅ {debug_msg}"
 
#         # Otherwise frontal
#         return True, f"Frontal face detected ✅ {debug_msg}"
 
 
# # ===================== STEP 3 & 4: Malpractice and People Detection ===================== #
# def detect_yolo_objects(image_path):
#     """
#     Detects specific objects (person, cell phone) using YOLOv5.
#     Returns (multiple_people: bool, malpractice: bool, detected_objects: list)
#     """
#     results = model(image_path)
#     labels = results.pandas().xyxy[0]['name'].tolist()
   
#     # Count specific objects
#     num_people = labels.count('person')
#     num_cell_phones = labels.count('cell phone')
   
#     multiple_people = num_people > 1
#     malpractice = num_cell_phones > 0
   
#     return multiple_people, malpractice, labels
 
 
# # ===================== PIPELINE ===================== #
# def run_full_interview_photo_check(resume_photo_path, interview_photo_path):
#     if not os.path.isfile(resume_photo_path) or not os.path.isfile(interview_photo_path):
#         return {'success': False, 'message': 'One or both image files not found ❌'}
 
#     # Step 0: Face visibility
#     visible, vis_msg = is_face_visible(interview_photo_path)
#     if not visible:
#         return {'success': False, 'message': vis_msg}
 
#     # Step 1: Face match (performed before orientation check)
#     match_result = verify_face_match(resume_photo_path, interview_photo_path)
#     if 'error' in match_result:
#         return {'success': False, 'match': False, 'message': f"Face verification error: {match_result['error']}"}
 
#     # Step 2: Orientation
#     allowed, orient_msg = check_face_orientation(interview_photo_path)
 
#     # Step 3 & 4: Multiple people and malpractice detection using YOLO
#     multiple_people, malpractice, detected_objects = detect_yolo_objects(interview_photo_path)
 
#     # Determine final success status based on all checks
#     final_success = match_result.get('verified') and allowed and not multiple_people and not malpractice
 
#     # Build response
#     response = {
#         'success': final_success,
#         'match': match_result.get('verified', False),
#         'orientation_ok': allowed,
#         'multiple_faces': multiple_people,
#         'malpractice': malpractice,
#         'detected_objects': detected_objects,
#         'model_used': match_result.get('model'),
#         'face_orientation_msg': orient_msg
#     }
 
#     # Summary message
#     parts = []
#     if match_result.get('verified', False):
#         parts.append("Face matched ✅")
#     else:
#         parts.append("Face mismatch ❌ – person not same")
 
#     # The orientation message from check_face_orientation already includes an icon
#     parts.append(orient_msg)
 
#     parts.append('multiple faces detected ❌' if multiple_people else 'no extra face detected ✅')
#     parts.append('cell phone detected ❌ – possible malpractice' if malpractice else 'no malpractice detected ✅')
   
#     response['message'] = ', '.join(parts)
 
#     return response

# # --- END OF FILE interview_cam.py ---




















"""
Interview Proctoring Module (interview_cam.py)

This module provides a suite of functions to perform automated checks on a
still image captured during a remote interview. It is designed to be integrated
into a larger system (like a Django application) to ensure interview integrity.

Checks Performed:
1.  Face Match: Verifies if the person in the interview photo matches a reference photo (e.g., from a resume).
2.  Frontal Face Orientation: Ensures the candidate is looking straight at the camera.
3.  Multiple Face Detection: Detects if more than one person is present in the frame.
4.  Malpractice Detection: Specifically checks for the presence of a cell phone.
"""

import cv2
import torch
from deepface import DeepFace
import mediapipe as mp
import numpy as np
import os

# --- MODEL AND LIBRARY INITIALIZATION ---

# Load YOLOv5 model once for object detection.
# trust_repo=True is required for the current version of the ultralytics hub.
print("Loading YOLOv5 model for object detection...")
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', trust_repo=True)
print("YOLOv5 model loaded.")

# Initialize MediaPipe Face Mesh for detailed landmark detection (used for orientation).
mp_face_mesh = mp.solutions.face_mesh

# Initialize MediaPipe Face Detection for finding the number of faces.
mp_face_detection = mp.solutions.face_detection


# ----------- STEP 1: Face Match Check ----------- #
def verify_face_match(resume_builder_photo_path, interview_talent_photo_path):
    """
    Verifies if two faces from different images belong to the same person using DeepFace.
    Args:
        resume_builder_photo_path (str): Path to the reference image.
        interview_talent_photo_path (str): Path to the image captured during the interview.
    Returns:
        dict: A dictionary containing the match status, distance, model, or an error.
    """
    try:
        # Using ArcFace model as it's highly accurate for verification tasks.
        result = DeepFace.verify(resume_builder_photo_path, interview_talent_photo_path, model_name='ArcFace')
        return {
            'match': result['verified'],
            'distance': result['distance'],
            'model_used': result['model']
        }
    except Exception as e:
        # Handle cases where a face isn't found in one of the images.
        return {'match': False, 'error': str(e)}


# ----------- STEP 2: Frontal Face / Orientation Check ----------- #
def is_frontal_face(image_path, threshold_ratio=0.1):
    """
    Checks if a face in an image is looking straight ahead.
    Compares the horizontal distance between the nose tip and the center of the eyes.
    Args:
        image_path (str): Path to the interview image.
        threshold_ratio (float): Sensitivity for detecting non-frontal poses. Lower is stricter.
    Returns:
        tuple: (bool: True if frontal, str: Descriptive message)
    """
    image = cv2.imread(image_path)
    if image is None:
        return False, "Image not found for orientation check"

    # Use a 'with' statement for resource management. static_image_mode=True is for single images.
    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, min_detection_confidence=0.5) as face_mesh:
        results = face_mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        if not results.multi_face_landmarks:
            return False, "No face detected for orientation check"

        face_landmarks = results.multi_face_landmarks[0]
        # Key landmarks for orientation check
        nose_tip = face_landmarks.landmark[1]
        left_eye = face_landmarks.landmark[33]
        right_eye = face_landmarks.landmark[263]

        # Calculate the ratio of nose offset to eye distance
        eye_distance = abs(left_eye.x - right_eye.x)
        nose_center_offset = abs((left_eye.x + right_eye.x) / 2 - nose_tip.x)
        
        # Avoid division by zero if eyes are not detected properly
        if eye_distance == 0:
            return False, "Could not determine eye distance"

        ratio = nose_center_offset / eye_distance

        if ratio < threshold_ratio:
            return True, "Frontal face detected"
        else:
            return False, "Face is turned – please look straight"


# ----------- STEP 3: Multiple Face Detection ----------- #
def detect_multiple_faces(image_path):
    """
    Detects if more than one face is present in the image.
    Args:
        image_path (str): Path to the interview image.
    Returns:
        bool: True if more than one face is detected, False otherwise.
    """
    image = cv2.imread(image_path)
    if image is None:
        return False

    # Use FaceDetection model which is optimized for finding faces.
    with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
        results = face_detection.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        # Check if detections exist and if the count is greater than 1
        return results.detections and len(results.detections) > 1


# ----------- STEP 4: Malpractice Detection (Only Cell Phone) ----------- #
def detect_phone_or_malpractice(image_path):
    """
    Runs YOLOv5 object detection on an image to find cell phones.
    Args:
        image_path (str): Path to the interview image.
    Returns:
        tuple: (bool: True if a cell phone is found, list: List of detected 'cell phone' labels)
    """
    results = model(image_path)
    labels = results.pandas().xyxy[0]['name'].tolist()

    # We are only interested in 'cell phone' for this check
    cell_phones_detected = [label for label in labels if label == 'cell phone']

    malpractice = len(cell_phones_detected) > 0
    return malpractice, cell_phones_detected


# ----------- Final Pipeline Function ----------- #
def run_full_interview_photo_check(resume_photo_path, interview_photo_path):
    """
    Executes the full pipeline of checks on the provided interview photo.
    Args:
        resume_photo_path (str): Path to the reference image.
        interview_photo_path (str): Path to the image captured during the interview.
    Returns:
        dict: A comprehensive dictionary with the results of all checks.
    """
    if not os.path.isfile(resume_photo_path) or not os.path.isfile(interview_photo_path):
        return {'success': False, 'message': 'One or both image files not found'}

    # 1. Face Match Verification
    match_result = verify_face_match(resume_photo_path, interview_photo_path)
    if not match_result.get('match'):
        return {
            'success': False,
            'match': False,
            'message': f"Face mismatch ❌ – person not same. Reason: {match_result.get('error', 'N/A')}"
        }

    # 2. Frontal Face Orientation Check
    is_frontal, frontal_msg = is_frontal_face(interview_photo_path)

    # 3. Multiple Faces Detection
    multiple_faces = detect_multiple_faces(interview_photo_path)

    # 4. Malpractice Detection (Cell Phone)
    malpractice, detected_labels = detect_phone_or_malpractice(interview_photo_path)

    # 5. Compile Final Result and Message
    # This structure is designed to be easily consumed by a Django API view.
    return {
        'success': True,
        'match': True,
        'orientation_ok': is_frontal,
        'face_orientation_msg': frontal_msg,
        'multiple_faces': multiple_faces,
        'malpractice': malpractice,
        'detected_objects': detected_labels,  # Will only contain 'cell phone' if detected
        'message': (
            f"Face matched ✅, "
            f"{frontal_msg} {'👍' if is_frontal else '❌'}, "
            f"{'multiple faces detected ❌' if multiple_faces else 'no extra face detected ✅'}, "
            f"{'cell phone detected ❌ – possible malpractice' if malpractice else 'no malpractice detected ✅'}"
        ),
        'distance': match_result.get('distance'),
        'model_used': match_result.get('model_used')
    }


# ----------- Example Usage (for testing the script directly) ----------- #
if __name__ == "__main__":
    # --- IMPORTANT ---
    # To test this, replace these paths with actual image file paths on your system.
    # For example:
    # resume_photo = "C:/Users/YourUser/Pictures/my_photo.jpg"
    # interview_photo = "C:/Users/YourUser/Pictures/test_photo_with_phone.jpg"

    resume_photo = "path/to/your/resume_photo.jpeg"
    interview_photo = "path/to/your/interview_photo.jpeg"

    # Check if placeholder paths have been changed
    if not os.path.exists(resume_photo) or not os.path.exists(interview_photo):
        print("\n--- EXAMPLE USAGE ---")
        print("Please update the 'resume_photo' and 'interview_photo' paths inside the")
        print("`if __name__ == '__main__':` block at the end of this script to test it.")
    else:
        print("\n--- RUNNING FULL CHECK ---")
        final_result = run_full_interview_photo_check(resume_photo, interview_photo)
        
        # Pretty print the final result dictionary
        import json
        print(json.dumps(final_result, indent=4))