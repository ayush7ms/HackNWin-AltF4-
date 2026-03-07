"""
UPSMS detector.py - FINAL HACKATHON VERSION (Fixed Circular Import)
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any
import cv2
import numpy as np

# Import config constants
import config
from config import (
    ACCIDENT_OVERLAP_FRAMES,
    ACCIDENT_VELOCITY_DROP_RATIO,
    ACCIDENT_VELOCITY_HISTORY_FRAMES,
    CONFLICT_STRUGGLE_VARIANCE_THRESHOLD,
    CONFLICT_STRUGGLE_WINDOW_SEC,
    EVENT_ACCIDENT,
    EVENT_CONFLICT,
    EVENT_MEDICAL,
    FALL_ANGLE_DEG_THRESHOLD,
    FALL_ANGLE_STATIC_TOLERANCE_DEG,
    FALL_POSITION_STATIC_PX,
    KEYPOINT_LEFT_HIP,
    KEYPOINT_LEFT_WRIST,
    KEYPOINT_NOSE,
    KEYPOINT_RIGHT_HIP,
    KEYPOINT_RIGHT_WRIST,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    VEHICLE_CLASS_IDS,
)

# --- DEMO SENSITIVITY OVERRIDES ---
CONFIDENCE_THRESHOLD = 0.4 
FALL_STATIC_DURATION_SEC = 2 
CONFLICT_PROXIMITY_DURATION_SEC = 3
CONFLICT_PROXIMITY_PX = 200 

logger = logging.getLogger("UPSMS.detector")

@dataclass
class Incident:
    """One detected incident to be saved and reported."""
    event_type: str
    severity: str
    metadata: dict = field(default_factory=dict)

# --- Helper Functions ---
def _iou_box(box1, box2):
    x1, y1 = max(box1[0], box2[0]), max(box1[1], box2[1])
    x2, y2 = min(box1[2], box2[2]), min(box1[3], box2[3])
    if x2 <= x1 or y2 <= y1: return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0

def _boxes_overlap(box1, box2, min_iou=0.01):
    return _iou_box(box1, box2) >= min_iou

def _match_tracks(prev_centers, curr_centers, max_dist=150):
    if not prev_centers: return [-1] * len(curr_centers)
    used, out = set(), []
    for (cx, cy) in curr_centers:
        best, best_d = -1, max_dist
        for i, (px, py) in enumerate(prev_centers):
            if i in used: continue
            d = np.hypot(cx - px, cy - py)
            if d < best_d: best_d, best = d, i
        if best >= 0: used.add(best)
        out.append(best)
    return out

# --- Detector Classes ---
class AccidentDetector:
    def __init__(self, fps=30):
        self.fps = max(fps, 1)
        self._history = {}
        self._next_id, self._frame_idx = 0, 0
        self._overlap_count, self._last_centers, self._last_track_ids = {}, [], []

    def update(self, detections, class_ids, confidences):
        self._frame_idx += 1
        vehicle_boxes, vehicle_centers = [], []
        for box, cid, conf in zip(detections, class_ids, confidences):
            if cid not in VEHICLE_CLASS_IDS or conf < CONFIDENCE_THRESHOLD: continue
            xyxy = np.array([box[0], box[1], box[2], box[3]], dtype=float)
            vehicle_boxes.append(xyxy)
            vehicle_centers.append(((xyxy[0]+xyxy[2])/2, (xyxy[1]+xyxy[3])/2))
        n = len(vehicle_boxes)
        if n < 2:
            self._overlap_count.clear()
            self._last_centers, self._last_track_ids = vehicle_centers, list(range(n))
            return None
        matches = _match_tracks(self._last_centers, vehicle_centers)
        track_ids = []
        for idx, m in enumerate(matches):
            tid = self._last_track_ids[m] if (m >= 0 and m < len(self._last_track_ids)) else self._next_id
            if m < 0: self._next_id += 1
            track_ids.append(tid)
        self._last_centers, self._last_track_ids = vehicle_centers, track_ids
        for idx in range(n):
            tid = track_ids[idx]
            if tid not in self._history: self._history[tid] = deque(maxlen=ACCIDENT_VELOCITY_HISTORY_FRAMES)
            self._history[tid].append((vehicle_boxes[idx], vehicle_centers[idx], self._frame_idx))
        for i in range(n):
            for j in range(i + 1, n):
                if _boxes_overlap(vehicle_boxes[i], vehicle_boxes[j]):
                    pair = (min(track_ids[i], track_ids[j]), max(track_ids[i], track_ids[j]))
                    self._overlap_count[pair] = self._overlap_count.get(pair, 0) + 1
                    if self._overlap_count[pair] >= ACCIDENT_OVERLAP_FRAMES:
                        self._overlap_count[pair] = 0
                        logger.info("Accident detected!")
                        return Incident(event_type=EVENT_ACCIDENT, severity=SEVERITY_HIGH)
        return None

class FallDetector:
    def __init__(self, fps=30):
        self.fps, self._person_states = max(fps, 1), []

    def update(self, pose_keypoints, frame_time):
        if pose_keypoints is None or len(pose_keypoints) == 0: return None
        while len(self._person_states) < len(pose_keypoints):
            self._person_states.append({"start_time": None, "last_angle": None, "last_mid_hip": None})
        for idx, kpts in enumerate(pose_keypoints):
            nose, lh, rh = kpts[KEYPOINT_NOSE], kpts[KEYPOINT_LEFT_HIP], kpts[KEYPOINT_RIGHT_HIP]
            if nose[2] < CONFIDENCE_THRESHOLD or (lh[2] < CONFIDENCE_THRESHOLD and rh[2] < CONFIDENCE_THRESHOLD): continue
            mid_hip = (lh[:2] + rh[:2]) / 2
            dx, dy = nose[0] - mid_hip[0], nose[1] - mid_hip[1]
            angle = 90.0 - abs(np.degrees(np.arctan2(dx, -dy)))
            state = self._person_states[idx]
            if angle >= FALL_ANGLE_DEG_THRESHOLD:
                state["start_time"] = None
                continue
            if state["start_time"] is None:
                state.update({"start_time": frame_time, "last_angle": angle, "last_mid_hip": mid_hip.copy()})
                continue
            if abs(angle - state["last_angle"]) > FALL_ANGLE_STATIC_TOLERANCE_DEG or np.linalg.norm(mid_hip - state["last_mid_hip"]) > FALL_POSITION_STATIC_PX:
                state["start_time"] = frame_time
            state["last_angle"], state["last_mid_hip"] = angle, mid_hip.copy()
            if frame_time - state["start_time"] >= FALL_STATIC_DURATION_SEC:
                state["start_time"] = None
                logger.info("Medical (fall) detected!")
                return Incident(event_type=EVENT_MEDICAL, severity=SEVERITY_HIGH)
        return None

class HarassmentDetector:
    def __init__(self, fps=30):
        self.fps, self._proximity_start = max(fps, 1), {}
        self._proximity_duration_frames = int(CONFLICT_PROXIMITY_DURATION_SEC * fps)

    def update(self, person_centers, frame_idx):
        n = len(person_centers)
        if n < 2:
            self._proximity_start.clear()
            return None
        for i in range(n):
            for j in range(i + 1, n):
                if np.hypot(person_centers[i][0]-person_centers[j][0], person_centers[i][1]-person_centers[j][1]) < CONFLICT_PROXIMITY_PX:
                    key = (min(i, j), max(i, j))
                    if key not in self._proximity_start: self._proximity_start[key] = frame_idx
                    if (frame_idx - self._proximity_start[key]) >= self._proximity_duration_frames:
                        self._proximity_start.pop(key, None)
                        logger.info("Conflict (harassment) detected!")
                        return Incident(event_type=EVENT_CONFLICT, severity=SEVERITY_MEDIUM)
        return None

# --- Main Detector Interface ---
class UPSMSDetector:
    def __init__(self, fps=30):
        self.fps = fps
        self._det_model, self._pose_model = None, None
        self._accident, self._fall, self._harassment = AccidentDetector(fps), FallDetector(fps), HarassmentDetector(fps)
        self._frame_idx, self._frame_time = 0, 0.0

    def _ensure_models(self):
        from ultralytics import YOLO
        if self._det_model is None:
            self._det_model = YOLO("yolov8n.pt")
            logger.info("Loaded yolov8n.pt")
        if self._pose_model is None:
            self._pose_model = YOLO("yolov8n-pose.pt")
            logger.info("Loaded yolov8n-pose.pt")

    def run(self, frame):
        self._ensure_models()
        self._frame_idx += 1
        self._frame_time += 1.0 / self.fps
        incidents = []

        # Detection & Pose prediction
        det_res = self._det_model.predict(frame, conf=CONFIDENCE_THRESHOLD, verbose=False, classes=list(VEHICLE_CLASS_IDS)+[0])[0]
        annotated_frame = det_res.plot()
        
        if det_res.boxes:
            xyxy, cls, conf = det_res.boxes.xyxy.cpu().numpy(), det_res.boxes.cls.cpu().numpy().astype(int), det_res.boxes.conf.cpu().numpy()
            acc = self._accident.update(xyxy, cls, conf)
            if acc: incidents.append(acc)

        pose_res = self._pose_model.predict(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)[0]
        annotated_frame = pose_res.plot(img=annotated_frame)
        
        if pose_res.keypoints is not None and pose_res.keypoints.data is not None:
            kpts = pose_res.keypoints.data.cpu().numpy()
            fall = self._fall.update(kpts, self._frame_time)
            if fall: incidents.append(fall)
            centers = [(float((k[11,0]+k[12,0])/2), float((k[11,1]+k[12,1])/2)) for k in kpts if k.shape[0] >= 13]
            conflict = self._harassment.update(centers, self._frame_idx)
            if conflict: incidents.append(conflict)
        
        return incidents, annotated_frame