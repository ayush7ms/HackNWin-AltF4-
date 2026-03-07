"""
YOLOv8 detection and pose estimation; accident, fall, and harassment (conflict) logic.
Modular design with confidence threshold 0.6 to reduce false positives.
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from config import (
    ACCIDENT_OVERLAP_FRAMES,
    ACCIDENT_VELOCITY_DROP_RATIO,
    ACCIDENT_VELOCITY_HISTORY_FRAMES,
    CONFIDENCE_THRESHOLD,
    CONFLICT_PROXIMITY_DURATION_SEC,
    CONFLICT_PROXIMITY_PX,
    CONFLICT_STRUGGLE_VARIANCE_THRESHOLD,
    CONFLICT_STRUGGLE_WINDOW_SEC,
    EVENT_ACCIDENT,
    EVENT_CONFLICT,
    EVENT_MEDICAL,
    FALL_ANGLE_DEG_THRESHOLD,
    FALL_ANGLE_STATIC_TOLERANCE_DEG,
    FALL_POSITION_STATIC_PX,
    FALL_STATIC_DURATION_SEC,
    KEYPOINT_LEFT_HIP,
    KEYPOINT_LEFT_WRIST,
    KEYPOINT_NOSE,
    KEYPOINT_RIGHT_HIP,
    KEYPOINT_RIGHT_WRIST,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    VEHICLE_CLASS_IDS,
)

logger = logging.getLogger("UPSMS.detector")


@dataclass
class Incident:
    """One detected incident to be saved and reported."""
    event_type: str
    severity: str
    metadata: dict = field(default_factory=dict)


def _iou_box(box1: np.ndarray, box2: np.ndarray) -> float:
    """Compute IoU of two boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _boxes_overlap(box1: np.ndarray, box2: np.ndarray, min_iou: float = 0.01) -> bool:
    """True if two boxes overlap (IoU or intersection exists)."""
    return _iou_box(box1, box2) >= min_iou


def _match_tracks(prev_centers: list[tuple[float, float]], curr_centers: list[tuple[float, float]], max_dist: float = 150) -> list[int]:
    """Match current centers to previous by nearest distance. Returns list of track_id per curr index (-1 = new)."""
    if not prev_centers:
        return [-1] * len(curr_centers)
    used = set()
    out = []
    for (cx, cy) in curr_centers:
        best = -1
        best_d = max_dist
        for i, (px, py) in enumerate(prev_centers):
            if i in used:
                continue
            d = np.hypot(cx - px, cy - py)
            if d < best_d:
                best_d = d
                best = i
        if best >= 0:
            used.add(best)
        out.append(best)
    return out


class AccidentDetector:
    """Flag ACCIDENT when two vehicle bboxes overlap and both velocities drop >80%."""

    def __init__(self, fps: float = 30):
        self.fps = max(fps, 1)
        # track_id -> deque of (bbox_xyxy, center, frame_idx)
        self._history: dict[int, deque] = {}
        self._next_id = 0
        self._frame_idx = 0
        self._overlap_count: dict[tuple[int, int], int] = {}
        self._last_centers: list[tuple[float, float]] = []
        self._last_track_ids: list[int] = []

    def update(self, detections: np.ndarray, class_ids: np.ndarray, confidences: np.ndarray) -> Incident | None:
        """
        detections: (N, 4) xyxy boxes; class_ids and confidences (N,).
        Only vehicles (car, truck, motorcycle) with conf >= CONFIDENCE_THRESHOLD.
        """
        self._frame_idx += 1
        vehicle_boxes = []
        vehicle_centers = []
        for box, cid, conf in zip(detections, class_ids, confidences):
            if cid not in VEHICLE_CLASS_IDS or conf < CONFIDENCE_THRESHOLD:
                continue
            xyxy = np.array([box[0], box[1], box[2], box[3]], dtype=float)
            cx = (xyxy[0] + xyxy[2]) / 2
            cy = (xyxy[1] + xyxy[3]) / 2
            vehicle_boxes.append(xyxy)
            vehicle_centers.append((cx, cy))

        n = len(vehicle_boxes)
        if n < 2:
            self._overlap_count.clear()
            self._last_centers = vehicle_centers
            self._last_track_ids = list(range(n))
            self._prune_history([])
            return None

        # Match current vehicles to previous tracks by nearest center
        matches = _match_tracks(self._last_centers, vehicle_centers)
        track_ids = []
        for idx, m in enumerate(matches):
            if m >= 0 and m < len(self._last_track_ids):
                tid = self._last_track_ids[m]
            else:
                tid = self._next_id
                self._next_id += 1
            track_ids.append(tid)
        self._last_centers = vehicle_centers
        self._last_track_ids = track_ids

        # Update velocity history per track
        for idx in range(n):
            tid = track_ids[idx]
            if tid not in self._history:
                self._history[tid] = deque(maxlen=ACCIDENT_VELOCITY_HISTORY_FRAMES)
            center = vehicle_centers[idx]
            box = vehicle_boxes[idx]
            self._history[tid].append((box.copy(), center, self._frame_idx))

        # Check overlapping pairs (by box index); track pair by (tid_i, tid_j)
        overlap_pairs: list[tuple[int, int]] = []
        overlap_track_pairs: list[tuple[int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                if _boxes_overlap(vehicle_boxes[i], vehicle_boxes[j]):
                    overlap_pairs.append((i, j))
                    overlap_track_pairs.append((min(track_ids[i], track_ids[j]), max(track_ids[i], track_ids[j])))

        for (i, j), tpair in zip(overlap_pairs, overlap_track_pairs):
            self._overlap_count[tpair] = self._overlap_count.get(tpair, 0) + 1
        for pair in list(self._overlap_count):
            if pair not in overlap_track_pairs:
                self._overlap_count[pair] = 0

        # Require overlap for ACCIDENT_OVERLAP_FRAMES
        for tpair, count in self._overlap_count.items():
            if count < ACCIDENT_OVERLAP_FRAMES:
                continue
            vel_ok = True
            for tid in tpair:
                if tid not in self._history or len(self._history[tid]) < 2:
                    vel_ok = False
                    break
                hist = self._history[tid]
                (_, c_curr, _), (_, c_prev, _) = hist[-1], hist[-2]
                v_curr = np.hypot(c_curr[0] - c_prev[0], c_curr[1] - c_prev[1])
                if len(hist) >= 3:
                    (_, c_old, _) = hist[-3]
                    v_prev = np.hypot(c_prev[0] - c_old[0], c_prev[1] - c_old[1])
                else:
                    v_prev = v_curr
                if v_prev <= 1e-6:
                    drop = 1.0
                else:
                    drop = 1.0 - (v_curr / v_prev)
                if drop < ACCIDENT_VELOCITY_DROP_RATIO:
                    vel_ok = False
                    break
            if vel_ok:
                self._overlap_count[tpair] = 0
                logger.info("Accident detected: overlapping vehicles with velocity drop >80%%")
                return Incident(event_type=EVENT_ACCIDENT, severity=SEVERITY_HIGH, metadata={})

        self._prune_history(track_ids)
        return None

    def _prune_history(self, current_track_ids: list[int]):
        keep = set(current_track_ids)
        for k in list(self._history):
            if k not in keep:
                del self._history[k]


def _torso_angle_deg(keypoints: np.ndarray) -> float | None:
    """
    keypoints: (17, 3) with x, y, conf. Nose=0, left_hip=11, right_hip=12.
    Angle of torso (nose to mid-hip) to ground (horizontal). Horizontal = 90°.
    """
    if keypoints.shape[0] < 13:
        return None
    nose = keypoints[KEYPOINT_NOSE]
    lh = keypoints[KEYPOINT_LEFT_HIP]
    rh = keypoints[KEYPOINT_RIGHT_HIP]
    if nose[2] < CONFIDENCE_THRESHOLD or (lh[2] < CONFIDENCE_THRESHOLD and rh[2] < CONFIDENCE_THRESHOLD):
        return None
    mid_hip = (lh[:2] + rh[:2]) / 2 if (lh[2] >= CONFIDENCE_THRESHOLD and rh[2] >= CONFIDENCE_THRESHOLD) else (lh[:2] if lh[2] >= CONFIDENCE_THRESHOLD else rh[:2])
    dx = nose[0] - mid_hip[0]
    dy = nose[1] - mid_hip[1]
    # Angle from vertical: vertical = (0, -1) upward. Torso vector = (dx, dy).
    # Angle to ground: ground is horizontal; angle to ground = 90 - angle_to_vertical.
    angle_to_vertical = np.degrees(np.arctan2(dx, -dy))
    angle_to_ground = 90.0 - abs(angle_to_vertical)
    return angle_to_ground


class FallDetector:
    """Flag MEDICAL when torso is horizontal (<30° to ground) and static for 5 seconds."""

    def __init__(self, fps: float = 30):
        self.fps = max(fps, 1)
        self._person_states: list[dict] = []  # per-person: start_time, last_angle, last_mid_hip

    def update(self, pose_keypoints: np.ndarray, frame_time: float) -> Incident | None:
        """
        pose_keypoints: (N_persons, 17, 3) x, y, conf for each person.
        frame_time: current time in seconds.
        """
        if pose_keypoints is None or len(pose_keypoints) == 0:
            return None
        # Ensure we have one state per person (by index)
        while len(self._person_states) < len(pose_keypoints):
            self._person_states.append({"start_time": None, "last_angle": None, "last_mid_hip": None})

        for idx, kpts in enumerate(pose_keypoints):
            if kpts.shape[0] < 13:
                continue
            angle = _torso_angle_deg(kpts)
            if angle is None:
                self._person_states[idx]["start_time"] = None
                continue
            mid_hip = (kpts[KEYPOINT_LEFT_HIP, :2] + kpts[KEYPOINT_RIGHT_HIP, :2]) / 2
            state = self._person_states[idx]
            if angle >= FALL_ANGLE_DEG_THRESHOLD:
                state["start_time"] = None
                continue
            # Torso horizontal
            if state["start_time"] is None:
                state["start_time"] = frame_time
                state["last_angle"] = angle
                state["last_mid_hip"] = mid_hip.copy()
                continue
            # Check static: angle and position change below threshold
            angle_change = abs(angle - state["last_angle"]) if state["last_angle"] is not None else 0
            pos_change = np.linalg.norm(mid_hip - state["last_mid_hip"]) if state["last_mid_hip"] is not None else 0
            state["last_angle"] = angle
            state["last_mid_hip"] = mid_hip.copy()
            if angle_change > FALL_ANGLE_STATIC_TOLERANCE_DEG or pos_change > FALL_POSITION_STATIC_PX:
                state["start_time"] = frame_time
                continue
            if frame_time - state["start_time"] >= FALL_STATIC_DURATION_SEC:
                state["start_time"] = None
                logger.info("Medical (fall) detected: torso horizontal and static for 5s")
                return Incident(event_type=EVENT_MEDICAL, severity=SEVERITY_HIGH, metadata={"person_index": idx})
        return None


def _wrist_variance(history: list[np.ndarray]) -> float:
    """history: list of (17,3) keypoints. Return variance of wrist positions (left+right)."""
    if len(history) < 2:
        return 0.0
    pts = []
    for kpts in history:
        if kpts.shape[0] < 11:
            continue
        for ki in (KEYPOINT_LEFT_WRIST, KEYPOINT_RIGHT_WRIST):
            if kpts[ki, 2] >= CONFIDENCE_THRESHOLD:
                pts.append(kpts[ki, :2])
    if len(pts) < 2:
        return 0.0
    pts = np.array(pts)
    return float(np.var(pts[:, 0]) + np.var(pts[:, 1]))


class HarassmentDetector:
    """Flag CONFLICT when two persons < 1m for 10s and at least one has wrist high-freq movement."""

    def __init__(self, fps: float = 30):
        self.fps = max(fps, 1)
        self._proximity_start: dict[tuple[int, int], float] = {}
        self._wrist_history: dict[int, deque] = {}
        self._struggle_window_frames = max(1, int(CONFLICT_STRUGGLE_WINDOW_SEC * fps))
        self._proximity_duration_frames = int(CONFLICT_PROXIMITY_DURATION_SEC * fps)

    def update(
        self,
        person_centers: list[tuple[float, float]],
        pose_keypoints: np.ndarray | None,
        frame_time: float,
        frame_idx: int,
    ) -> Incident | None:
        """
        person_centers: list of (cx, cy) for each person.
        pose_keypoints: (N, 17, 3) if available for wrist struggle.
        """
        n = len(person_centers)
        if n < 2:
            self._proximity_start.clear()
            return None

        # Pairwise distances (pixel proxy for 1m)
        close_pairs: list[tuple[int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                d = np.hypot(
                    person_centers[i][0] - person_centers[j][0],
                    person_centers[i][1] - person_centers[j][1],
                )
                if d < CONFLICT_PROXIMITY_PX:
                    close_pairs.append((i, j))

        # Update wrist history for struggle
        if pose_keypoints is not None and pose_keypoints.shape[0] >= n:
            for idx in range(n):
                if idx not in self._wrist_history:
                    self._wrist_history[idx] = deque(maxlen=self._struggle_window_frames)
                self._wrist_history[idx].append(pose_keypoints[idx].copy())

        for pair in close_pairs:
            key = (min(pair), max(pair))
            if key not in self._proximity_start:
                self._proximity_start[key] = frame_idx
            duration_frames = frame_idx - self._proximity_start[key]
            if duration_frames < self._proximity_duration_frames:
                continue
            # Check struggle for either person in the pair
            struggle = False
            for idx in key:
                if idx in self._wrist_history and len(self._wrist_history[idx]) >= 2:
                    var = _wrist_variance(list(self._wrist_history[idx]))
                    if var >= CONFLICT_STRUGGLE_VARIANCE_THRESHOLD:
                        struggle = True
                        break
            if struggle:
                self._proximity_start.pop(key, None)
                logger.info("Conflict (harassment) detected: proximity <1m for 10s with wrist struggle")
                return Incident(event_type=EVENT_CONFLICT, severity=SEVERITY_MEDIUM, metadata={"pair": list(key)})
        # Reset pairs that are no longer close
        for key in list(self._proximity_start):
            if key not in [(min(a, b), max(a, b)) for a, b in close_pairs]:
                del self._proximity_start[key]
        return None


class UPSMSDetector:
    """
    Single entry: run detection + pose, then accident, fall, harassment logic.
    Returns list of Incident for the current frame.
    """

    def __init__(self, fps: float = 30):
        self.fps = fps
        self._det_model = None
        self._pose_model = None
        self._accident = AccidentDetector(fps)
        self._fall = FallDetector(fps)
        self._harassment = HarassmentDetector(fps)
        self._frame_idx = 0
        self._frame_time = 0.0

    def _ensure_models(self):
        if self._det_model is None:
            from ultralytics import YOLO
            self._det_model = YOLO("yolov8s.pt")
            logger.info("Loaded yolov8s.pt")
        if self._pose_model is None:
            from ultralytics import YOLO
            self._pose_model = YOLO("yolov8s-pose.pt")
            logger.info("Loaded yolov8s-pose.pt")

    def run(self, frame: np.ndarray) -> list[Incident]:
        """
        Run object detection and pose on frame; run all three detection logics.
        Returns list of Incident (usually 0 or 1 per frame after cooldown in app).
        """
        self._ensure_models()
        self._frame_idx += 1
        self._frame_time += 1.0 / self.fps
        incidents: list[Incident] = []

        # Object detection (vehicles + person for consistency)
        det_results = self._det_model.predict(
            frame,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,
            classes=list(VEHICLE_CLASS_IDS) + [0],
        )[0]
        boxes = det_results.boxes
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            cls = boxes.cls.cpu().numpy().astype(int)
            conf = boxes.conf.cpu().numpy()
            vehicle_mask = np.isin(cls, VEHICLE_CLASS_IDS)
            v_xyxy = xyxy[vehicle_mask] if vehicle_mask.any() else np.empty((0, 4))
            v_cls = cls[vehicle_mask] if vehicle_mask.any() else np.empty(0)
            v_conf = conf[vehicle_mask] if vehicle_mask.any() else np.empty(0)
            acc = self._accident.update(v_xyxy, v_cls, v_conf)
            if acc:
                incidents.append(acc)
        else:
            self._accident.update(np.empty((0, 4)), np.empty(0), np.empty(0))

        # Pose (full frame for persons)
        pose_results = self._pose_model.predict(
            frame,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,
        )[0]
        keypoints = pose_results.keypoints
        if keypoints is not None and keypoints.data is not None:
            kpts = keypoints.data.cpu().numpy()
            # Fall
            fall = self._fall.update(kpts, self._frame_time)
            if fall:
                incidents.append(fall)
            # Harassment: person centers from pose bboxes or keypoint centroids
            person_centers = []
            for i in range(len(kpts)):
                k = kpts[i]
                if k.shape[0] < 13:
                    continue
                mid_hip = (k[KEYPOINT_LEFT_HIP, :2] + k[KEYPOINT_RIGHT_HIP, :2]) / 2
                person_centers.append((float(mid_hip[0]), float(mid_hip[1])))
            if len(person_centers) < 2:
                person_centers = []
            conflict = self._harassment.update(
                person_centers, kpts if len(person_centers) >= 2 else None,
                self._frame_time, self._frame_idx,
            )
            if conflict:
                incidents.append(conflict)
        else:
            self._fall.update(np.empty((0, 17, 3)), self._frame_time)
            self._harassment.update([], None, self._frame_time, self._frame_idx)

        return incidents
