import cv2
import torch
from deepface import DeepFace
import mediapipe as mp
import numpy as np
import os
 
# YOLOv5 model for object detection (phones, etc.)
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', trust_repo=True)
 
# MediaPipe setup
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True)
 
# ----------- STEP 1: Face Match Check ----------- #
def verify_face_match(resume_builder_photo_path, interview_talent_photo_path):
    try:
        result = DeepFace.verify(resume_builder_photo_path, interview_talent_photo_path, model_name='ArcFace')
        return {
            'match': result['verified'],
            'distance': result['distance'],
            'model_used': result['model']
        }
    except Exception as e:
        return {'match': False, 'error': str(e)}
 
# ----------- STEP 2: Orientation & Eye Direction ----------- #
def check_orientation_and_eyes(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return {'orientation_ok': False, 'eye_message': 'Image not found'}
 
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_image)
 
    if not results.multi_face_landmarks:
        return {'orientation_ok': False, 'eye_message': 'No face detected'}
 
    face_landmarks = results.multi_face_landmarks[0].landmark
    left_eye_x = face_landmarks[33].x
    right_eye_x = face_landmarks[263].x
    nose_x = face_landmarks[1].x
 
    eye_direction = 'forward'
    if nose_x < left_eye_x and nose_x < right_eye_x:
        eye_direction = 'right'
    elif nose_x > left_eye_x and nose_x > right_eye_x:
        eye_direction = 'left'
 
    orientation_ok = eye_direction == 'forward'
    return {
        'orientation_ok': orientation_ok,
        'eye_message': f"Eyes are looking {eye_direction} {'✅' if orientation_ok else '❌'}"
    }
 
# ----------- STEP 3: Multiple Face Detection ----------- #
def detect_multiple_faces(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return False
 
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_image)
 
    return len(results.multi_face_landmarks) > 1 if results.multi_face_landmarks else False
 
# ----------- STEP 4: Malpractice Detection (Phone, TV, etc.) ----------- #
def detect_phone_or_malpractice(image_path):
    results = model(image_path)
    labels = results.pandas().xyxy[0]['name'].tolist()
    print("Detected objects:", labels)
 
    # Malpractice check
    malpractice = any(label in ['cell phone', 'refrigerator', 'remote', 'tv', 'monitor'] for label in labels)
 
    return malpractice, labels
 
# ----------- Final Pipeline Function ----------- #
def run_full_interview_photo_check(resume_photo_path, interview_photo_path):
    if not os.path.isfile(resume_photo_path) or not os.path.isfile(interview_photo_path):
        return {'success': False, 'message': 'One or both image files not found'}
 
    # Step 1: Face match
    match_result = verify_face_match(resume_photo_path, interview_photo_path)
    if not match_result['match']:
        return {
            'success': False,
            'match': False,
            'message': 'Face mismatch ❌ – person not same'
        }
 
    # Step 2: Orientation and Eyes
    orientation_result = check_orientation_and_eyes(interview_photo_path)
 
    # Step 3: Multiple faces
    multiple_faces = detect_multiple_faces(interview_photo_path)
 
    # Step 4: Malpractice detection
    malpractice, labels = detect_phone_or_malpractice(interview_photo_path)
 
    return {
        'success': True,
        'match': True,
        'orientation_ok': orientation_result['orientation_ok'],
        'multiple_faces': multiple_faces,
        'malpractice': malpractice,
        'detected_objects': labels,
        'message': (
            f"Face matched ✅, "
            f"{'photo orientation good 👍' if orientation_result['orientation_ok'] else orientation_result['eye_message']}, "
            f"{'multiple faces detected ❌' if multiple_faces else 'and no extra face detected ✅'}, "
            f"{'suspicious object(s) detected ❌ – possible malpractice' if malpractice else 'and no malpractice detected ✅'}"
        ),
        'distance': match_result.get('distance'),
        'model_used': match_result.get('model_used')
    }