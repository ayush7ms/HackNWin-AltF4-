"""
UPSMS detector.py - FINAL VERSION (with fps parameter)
Uses all thresholds and constants from config.py.
Includes:
- Fall detection (pose‑based)
- Harassment/conflict detection (proximity + wrist movement variance)
- Women safety detection (stalking, isolation, gang)
- Optimized inference (resize + reuse)
"""
import logging
from collections import deque, defaultdict
from dataclasses import dataclass, field
import cv2
import numpy as np

from ultralytics import YOLO

import config
from config import (
    CONFIDENCE_THRESHOLD,
    VEHICLE_CLASS_IDS,
    KEYPOINT_NOSE, KEYPOINT_LEFT_HIP, KEYPOINT_RIGHT_HIP,
    KEYPOINT_LEFT_WRIST, KEYPOINT_RIGHT_WRIST,
    FALL_ANGLE_DEG_THRESHOLD,
    FALL_STATIC_DURATION_SEC,
    CONFLICT_PROXIMITY_PX,
    CONFLICT_PROXIMITY_DURATION_SEC,
    CONFLICT_STRUGGLE_WINDOW_SEC,
    CONFLICT_STRUGGLE_VARIANCE_THRESHOLD,
    EVENT_ACCIDENT, EVENT_CONFLICT, EVENT_MEDICAL,
    SEVERITY_HIGH, SEVERITY_MEDIUM
)

logger = logging.getLogger("UPSMS.detector")

@dataclass
class Incident:
    event_type: str
    severity: str
    metadata: dict = field(default_factory=dict)


class FallDetector:
    """
    Detects a fall when a person's torso is nearly horizontal for a minimum duration.
    Uses keypoints: nose, left hip, right hip.
    """
    def __init__(self):
        self.angle_threshold = FALL_ANGLE_DEG_THRESHOLD
        self.min_duration = FALL_STATIC_DURATION_SEC
        self._person_states = []          # state per detected person (list of dicts)

    def update(self, pose_keypoints, frame_time):
        """
        Args:
            pose_keypoints: list of arrays, each shape (17, 3)
            frame_time: current timestamp in seconds
        Returns:
            Incident or None
        """
        if pose_keypoints is None or len(pose_keypoints) == 0:
            return None

        while len(self._person_states) < len(pose_keypoints):
            self._person_states.append({"fall_start": None})

        for idx, kpts in enumerate(pose_keypoints):
            nose = kpts[KEYPOINT_NOSE]
            lh = kpts[KEYPOINT_LEFT_HIP]
            rh = kpts[KEYPOINT_RIGHT_HIP]

            # Skip if keypoints are too uncertain
            if nose[2] < CONFIDENCE_THRESHOLD or (lh[2] < CONFIDENCE_THRESHOLD and rh[2] < CONFIDENCE_THRESHOLD):
                continue

            mid_hip = (lh[:2] + rh[:2]) / 2.0
            dx = nose[0] - mid_hip[0]
            dy = nose[1] - mid_hip[1]
            # Angle from vertical (0° = upright, 90° = horizontal)
            angle = abs(np.degrees(np.arctan2(dx, -dy)))

            state = self._person_states[idx]
            if angle > self.angle_threshold:
                if state["fall_start"] is None:
                    state["fall_start"] = frame_time
                elif frame_time - state["fall_start"] >= self.min_duration:
                    # Reset to avoid repeated triggers
                    state["fall_start"] = None
                    logger.info("Medical (fall) detected!")
                    return Incident(event_type=EVENT_MEDICAL, severity=SEVERITY_HIGH)
            else:
                state["fall_start"] = None

        return None


class HarassmentDetector:
    """
    Detects potential harassment/conflict when two persons are very close
    and at least one shows erratic wrist movement (struggle).
    Uses keypoints: left wrist, right wrist, and mid‑hip for position.
    """
    def __init__(self, fps=30):
        self.fps = fps
        self.proximity_threshold = CONFLICT_PROXIMITY_PX
        self.proximity_duration = CONFLICT_PROXIMITY_DURATION_SEC
        self.struggle_window = CONFLICT_STRUGGLE_WINDOW_SEC
        self.variance_threshold = CONFLICT_STRUGGLE_VARIANCE_THRESHOLD

        # Calculate deque max length based on fps and struggle window
        self.history_len = int(self.struggle_window * self.fps) + 1

        # Person tracks: id -> {
        #   'last_seen': time,
        #   'position_history': deque of (x,y,time) for mid‑hip,
        #   'wrist_history': deque of (x_left, y_left, x_right, y_right, time)
        # }
        self.tracks = {}
        self.next_id = 0

        # Pair states: (id1,id2) -> {
        #   'close_start': time when they first became close,
        #   'struggle_detected': bool (whether struggle occurred during this close interval)
        # }
        self.pair_states = {}

    def _compute_wrist_variance(self, wrist_history):
        """Compute variance of wrist positions over the stored window."""
        if len(wrist_history) < 2:
            return 0.0
        # Flatten all wrist coordinates into a single array of vectors (x_left, y_left, x_right, y_right)
        points = np.array([[h[0], h[1], h[2], h[3]] for h in wrist_history])
        # Compute variance across time (axis=0) and take mean as a single scalar
        var = np.var(points, axis=0).mean()
        return var

    def update(self, pose_keypoints, frame_time):
        """
        Args:
            pose_keypoints: list of arrays, each shape (17, 3)
            frame_time: current timestamp in seconds
        Returns:
            Incident or None
        """
        if pose_keypoints is None or len(pose_keypoints) < 2:
            # Not enough people to form a pair
            return None

        # First, match current detections to existing tracks (simple nearest neighbor)
        current_centers = []
        current_wrists = []
        valid_indices = []
        for idx, kpts in enumerate(pose_keypoints):
            lh = kpts[KEYPOINT_LEFT_HIP]
            rh = kpts[KEYPOINT_RIGHT_HIP]
            lw = kpts[KEYPOINT_LEFT_WRIST]
            rw = kpts[KEYPOINT_RIGHT_WRIST]

            # Require at least one hip and both wrists with reasonable confidence
            if (lh[2] < CONFIDENCE_THRESHOLD and rh[2] < CONFIDENCE_THRESHOLD) or \
               lw[2] < CONFIDENCE_THRESHOLD or rw[2] < CONFIDENCE_THRESHOLD:
                continue

            mid_hip = (lh[:2] + rh[:2]) / 2.0
            current_centers.append(mid_hip)
            current_wrists.append((lw[0], lw[1], rw[0], rw[1]))
            valid_indices.append(idx)

        if len(current_centers) < 2:
            return None

        # Match each detection to an existing track (simple distance‑based)
        used_tracks = set()
        matched = {}      # track_id -> (center, wrists, original_idx)
        for center, wrists, orig_idx in zip(current_centers, current_wrists, valid_indices):
            best_tid = None
            best_dist = float('inf')
            for tid, tdata in self.tracks.items():
                if tid in used_tracks:
                    continue
                # Use last known position from position_history
                if tdata['position_history']:
                    last_center = tdata['position_history'][-1][:2]
                    # FIX: Convert tuple to array before subtraction
                    dist = np.linalg.norm(center - np.array(last_center))
                    if dist < best_dist and dist < 100:  # 100px association threshold
                        best_dist = dist
                        best_tid = tid
            if best_tid is not None:
                matched[best_tid] = (center, wrists, orig_idx)
                used_tracks.add(best_tid)
            else:
                # New track
                new_id = self.next_id
                self.next_id += 1
                matched[new_id] = (center, wrists, orig_idx)

        # Update tracks with new observations
        current_ids = []
        for tid, (center, wrists, orig_idx) in matched.items():
            if tid not in self.tracks:
                # Initialize new track with deques sized for the struggle window
                self.tracks[tid] = {
                    'position_history': deque(maxlen=self.history_len),
                    'wrist_history': deque(maxlen=self.history_len)
                }
            # Append new data
            self.tracks[tid]['position_history'].append((center[0], center[1], frame_time))
            self.tracks[tid]['wrist_history'].append((wrists[0], wrists[1], wrists[2], wrists[3], frame_time))
            current_ids.append(tid)

        # Remove tracks not seen for a while (e.g., > 2 seconds)
        to_delete = []
        for tid, tdata in self.tracks.items():
            if tdata['position_history'] and (frame_time - tdata['position_history'][-1][2]) > 2.0:
                to_delete.append(tid)
        for tid in to_delete:
            del self.tracks[tid]

        # Update pair states
        # First, mark all existing pairs as not seen in this frame
        for pair_key in list(self.pair_states.keys()):
            self.pair_states[pair_key]['seen_this_frame'] = False

        # Check all pairs of current tracks
        incident = None
        for i in range(len(current_ids)):
            for j in range(i+1, len(current_ids)):
                id1, id2 = current_ids[i], current_ids[j]
                # Ensure both have recent position history
                if (len(self.tracks[id1]['position_history']) == 0 or
                    len(self.tracks[id2]['position_history']) == 0):
                    continue

                # Compute current distance between mid‑hips
                pos1 = self.tracks[id1]['position_history'][-1][:2]
                pos2 = self.tracks[id2]['position_history'][-1][:2]
                distance = np.linalg.norm(np.array(pos1) - np.array(pos2))

                pair_key = tuple(sorted((id1, id2)))
                if distance < self.proximity_threshold:
                    # They are close
                    if pair_key not in self.pair_states:
                        self.pair_states[pair_key] = {
                            'close_start': frame_time,
                            'struggle_detected': False,
                            'seen_this_frame': True
                        }
                    else:
                        state = self.pair_states[pair_key]
                        state['seen_this_frame'] = True
                        # Check if struggle has been detected during this close interval
                        if not state['struggle_detected']:
                            # Compute wrist variance for both persons over the stored window
                            var1 = self._compute_wrist_variance(self.tracks[id1]['wrist_history'])
                            var2 = self._compute_wrist_variance(self.tracks[id2]['wrist_history'])
                            if var1 > self.variance_threshold or var2 > self.variance_threshold:
                                state['struggle_detected'] = True

                        # Now check if the pair has been close long enough and struggle occurred
                        if (state['struggle_detected'] and
                            frame_time - state['close_start'] >= self.proximity_duration):
                            logger.info(f"Conflict detected between IDs {id1} and {id2}")
                            incident = Incident(event_type=EVENT_CONFLICT, severity=SEVERITY_MEDIUM)
                            # Reset pair to avoid repeated triggers
                            del self.pair_states[pair_key]
                            break
                else:
                    # Not close anymore – remove pair state
                    if pair_key in self.pair_states:
                        del self.pair_states[pair_key]

            if incident:
                break

        # Clean up pair states that weren't seen in this frame
        for pair_key in list(self.pair_states.keys()):
            if not self.pair_states[pair_key].get('seen_this_frame', False):
                del self.pair_states[pair_key]

        return incident

class WomenSafetyDetector:
    """
    Detects scenarios that are especially relevant for women's safety:
    - Stalking: a person persistently following another at a distance.
    - Isolation: a person being alone in an area for a prolonged time.
    - Ganging up: multiple persons surrounding a single person.
    """
    def __init__(self, fps=30):
        self.fps = fps
        # Thresholds from config (or hardcoded defaults)
        self.stalking_distance = config.STALKING_DISTANCE_PX if hasattr(config, 'STALKING_DISTANCE_PX') else 150
        self.stalking_duration = config.STALKING_DURATION_SEC if hasattr(config, 'STALKING_DURATION_SEC') else 10
        self.stalking_angle_tol = config.STALKING_ANGLE_TOLERANCE_DEG if hasattr(config, 'STALKING_ANGLE_TOLERANCE_DEG') else 30
        self.isolation_radius = config.ISOLATION_RADIUS_PX if hasattr(config, 'ISOLATION_RADIUS_PX') else 200
        self.isolation_duration = config.ISOLATION_DURATION_SEC if hasattr(config, 'ISOLATION_DURATION_SEC') else 15
        self.gang_min_members = config.GANG_MIN_MEMBERS if hasattr(config, 'GANG_MIN_MEMBERS') else 3
        self.gang_proximity = config.GANG_PROXIMITY_PX if hasattr(config, 'GANG_PROXIMITY_PX') else 150
        self.gang_duration = config.GANG_DURATION_SEC if hasattr(config, 'GANG_DURATION_SEC') else 5

        # Tracking each person's position history (id -> deque of (x,y,time))
        self.tracks = {}
        self.next_id = 0

        # State for stalking: (stalker_id, target_id) -> {'start': frame_time, 'seen': bool}
        self.stalking_pairs = {}

        # State for isolation: person_id -> {'start': frame_time}
        self.isolation_state = {}

        # State for gang: group_key (sorted tuple of ids) -> {'start': frame_time, 'target': target_id}
        self.gang_state = {}

    def _match_detections(self, pose_keypoints, frame_time):
        """Existing matching method – unchanged."""
        # Extract mid‑hip for each detected person with sufficient confidence
        current_centers = []
        valid_indices = []
        for idx, kpts in enumerate(pose_keypoints):
            lh = kpts[config.KEYPOINT_LEFT_HIP]
            rh = kpts[config.KEYPOINT_RIGHT_HIP]
            if lh[2] < config.CONFIDENCE_THRESHOLD and rh[2] < config.CONFIDENCE_THRESHOLD:
                continue
            mid_hip = (lh[:2] + rh[:2]) / 2.0
            current_centers.append(mid_hip)
            valid_indices.append(idx)

        # Match to existing tracks (simple nearest neighbor)
        matched_ids = []
        used_tracks = set()
        for center in current_centers:
            best_tid = None
            best_dist = float('inf')
            for tid, tdata in self.tracks.items():
                if tid in used_tracks or not tdata['history']:
                    continue
                last_pos = tdata['history'][-1][:2]
                dist = np.linalg.norm(center - np.array(last_pos))
                if dist < best_dist and dist < 100:  # association threshold
                    best_dist = dist
                    best_tid = tid
            if best_tid is not None:
                matched_ids.append(best_tid)
                used_tracks.add(best_tid)
                self.tracks[best_tid]['history'].append((center[0], center[1], frame_time))
            else:
                # New track
                new_id = self.next_id
                self.next_id += 1
                self.tracks[new_id] = {
                    'history': deque(maxlen=int(10 * self.fps))  # store up to 10 seconds
                }
                self.tracks[new_id]['history'].append((center[0], center[1], frame_time))
                matched_ids.append(new_id)

        # Remove tracks not seen in this frame (older than 2 sec)
        to_delete = []
        for tid, tdata in self.tracks.items():
            if tdata['history'] and (frame_time - tdata['history'][-1][2]) > 2.0:
                to_delete.append(tid)
        for tid in to_delete:
            del self.tracks[tid]
            # Also clean up states
            self.isolation_state.pop(tid, None)

        return matched_ids

    def _is_behind(self, follower_pos, target_pos, target_heading, angle_tol=45):
        """Check if follower is behind the target (within angle_tol degrees behind)."""
        to_follower = follower_pos - target_pos
        norm = np.linalg.norm(to_follower)
        if norm == 0:
            return False
        to_follower = to_follower / norm
        heading_norm = np.linalg.norm(target_heading)
        if heading_norm == 0:
            return False
        target_heading = target_heading / heading_norm
        cos_angle = np.dot(target_heading, to_follower)
        # Behind means the direction to follower is opposite to heading (cos <= -cos(angle_tol))
        return cos_angle <= -np.cos(np.radians(angle_tol))

    def _check_stalking(self, current_ids, frame_time):
        """Detect stalking: one person consistently behind another at close distance."""
        incident = None
        for i in range(len(current_ids)):
            for j in range(i+1, len(current_ids)):
                id_a, id_b = current_ids[i], current_ids[j]
                hist_a = list(self.tracks[id_a]['history'])
                hist_b = list(self.tracks[id_b]['history'])
                if len(hist_a) < 5 or len(hist_b) < 5:
                    continue

                # Helper to get heading from history
                def get_heading(hist):
                    if len(hist) < 3:
                        return None
                    p_prev = np.array(hist[-3][:2])
                    p_curr = np.array(hist[-1][:2])
                    heading = p_curr - p_prev
                    norm = np.linalg.norm(heading)
                    if norm < 1e-3:
                        return np.zeros(2)
                    return heading / norm

                heading_a = get_heading(hist_a)
                heading_b = get_heading(hist_b)
                pos_a = np.array(hist_a[-1][:2])
                pos_b = np.array(hist_b[-1][:2])

                # Check if A is behind B
                if heading_b is not None and np.linalg.norm(pos_a - pos_b) < self.stalking_distance:
                    if self._is_behind(pos_a, pos_b, heading_b, self.stalking_angle_tol):
                        stalker, target = id_a, id_b
                    elif heading_a is not None and self._is_behind(pos_b, pos_a, heading_a, self.stalking_angle_tol):
                        stalker, target = id_b, id_a
                    else:
                        continue
                else:
                    continue

                pair_key = (stalker, target)  # ordered
                if pair_key not in self.stalking_pairs:
                    self.stalking_pairs[pair_key] = {'start': frame_time, 'seen': True}
                else:
                    self.stalking_pairs[pair_key]['seen'] = True
                    if frame_time - self.stalking_pairs[pair_key]['start'] >= self.stalking_duration:
                        logger.info(f"Stalking detected: {stalker} following {target}")
                        incident = Incident(event_type=config.EVENT_STALKING, severity=config.SEVERITY_HIGH)
                        del self.stalking_pairs[pair_key]
                        break
            if incident:
                break

        # Clean up unseen pairs
        for key in list(self.stalking_pairs.keys()):
            if not self.stalking_pairs[key].get('seen', False):
                del self.stalking_pairs[key]
            else:
                self.stalking_pairs[key]['seen'] = False
        return incident

    def _check_isolation(self, current_ids, frame_time):
        """Existing isolation detection – unchanged."""
        incident = None
        for tid in current_ids:
            pos = np.array(self.tracks[tid]['history'][-1][:2])
            others_near = 0
            for other in current_ids:
                if other == tid:
                    continue
                other_pos = np.array(self.tracks[other]['history'][-1][:2])
                if np.linalg.norm(pos - other_pos) < self.isolation_radius:
                    others_near += 1

            if others_near == 0:
                if tid not in self.isolation_state:
                    self.isolation_state[tid] = {'start': frame_time}
                elif frame_time - self.isolation_state[tid]['start'] >= self.isolation_duration:
                    logger.info(f"Isolation detected for person {tid}")
                    incident = Incident(event_type=config.EVENT_ISOLATION, severity=config.SEVERITY_MEDIUM)
                    del self.isolation_state[tid]
                    break
            else:
                self.isolation_state.pop(tid, None)
        return incident

    def _check_gang(self, current_ids, frame_time):
        """Existing gang detection – unchanged."""
        incident = None
        for target in current_ids:
            target_pos = np.array(self.tracks[target]['history'][-1][:2])
            close_others = []
            for other in current_ids:
                if other == target:
                    continue
                other_pos = np.array(self.tracks[other]['history'][-1][:2])
                if np.linalg.norm(target_pos - other_pos) < self.gang_proximity:
                    close_others.append(other)

            if len(close_others) >= self.gang_min_members - 1:
                group = tuple(sorted([target] + close_others))
                if group not in self.gang_state:
                    self.gang_state[group] = {'start': frame_time, 'target': target}
                elif frame_time - self.gang_state[group]['start'] >= self.gang_duration:
                    logger.info(f"Gang detected around person {target}")
                    incident = Incident(event_type=config.EVENT_GANG, severity=config.SEVERITY_HIGH)
                    del self.gang_state[group]
                    break
            else:
                for key in list(self.gang_state.keys()):
                    if target in key:
                        del self.gang_state[key]
        return incident

    def update(self, pose_keypoints, frame_time):
        """Main update method – unchanged."""
        if pose_keypoints is None or len(pose_keypoints) < 2:
            return None

        current_ids = self._match_detections(pose_keypoints, frame_time)
        if len(current_ids) < 2:
            return None

        # Run each detector (order doesn't matter)
        incident = self._check_stalking(current_ids, frame_time)
        if incident:
            return incident

        incident = self._check_isolation(current_ids, frame_time)
        if incident:
            return incident

        incident = self._check_gang(current_ids, frame_time)
        if incident:
            return incident

        return None


class UPSMSDetector:
    def __init__(self, fps=30, target_size=640):
        """
        Args:
            fps: frames per second of the input stream (used for timing)
            target_size: resize frames to this size (max dimension) for faster inference
        """
        self.fps = fps
        self.target_size = target_size
        self._det_model = None
        self._pose_model = None
        self._fall_detector = FallDetector()
        self._harassment_detector = HarassmentDetector(fps=fps)
        self._women_safety_detector = WomenSafetyDetector(fps=fps)
        self._frame_time = 0.0

    def _ensure_models(self):
        if self._det_model is None:
            self._det_model = YOLO("yolov8n.pt")
        if self._pose_model is None:
            self._pose_model = YOLO("yolov8n-pose.pt")

    def run(self, frame):
        """
        Process a single frame.
        Returns:
            incidents: list of Incident objects
            annotated_frame: image with detections/poses drawn
        """
        try:
            self._ensure_models()

            # Accurate timestamp
            current_time = cv2.getTickCount() / cv2.getTickFrequency()

            # Resize for speed
            h, w = frame.shape[:2]
            scale = self.target_size / max(h, w)
            if scale != 1.0:
                new_w = int(w * scale)
                new_h = int(h * scale)
                frame_resized = cv2.resize(frame, (new_w, new_h))
            else:
                frame_resized = frame

            # Detection (persons only, class 0)
            det_results = self._det_model.predict(
                frame_resized, conf=CONFIDENCE_THRESHOLD, verbose=False, classes=[0]
            )[0]

            # Pose estimation on the same resized frame
            pose_results = self._pose_model.predict(
                frame_resized, conf=CONFIDENCE_THRESHOLD, verbose=False
            )[0]

            # Extract keypoints for incident detectors
            pose_keypoints = None
            if pose_results.keypoints is not None and pose_results.keypoints.data is not None:
                pose_keypoints = pose_results.keypoints.data.cpu().numpy()

            # Annotate frame (detection boxes + skeletons)
            annotated_frame = det_results.plot()
            if pose_results.keypoints is not None:
                annotated_frame = pose_results.plot(img=annotated_frame)

            incidents = []

            # Fall detection
            fall_inc = self._fall_detector.update(pose_keypoints, current_time)
            if fall_inc:
                incidents.append(fall_inc)

            # Harassment detection (original conflict detection)
            harass_inc = self._harassment_detector.update(pose_keypoints, current_time)
            if harass_inc:
                incidents.append(harass_inc)

            # Women safety detection (stalking, isolation, gang)
            women_inc = self._women_safety_detector.update(pose_keypoints, current_time)
            if women_inc:
                incidents.append(women_inc)

            self._frame_time = current_time
            return incidents, annotated_frame

        except Exception as e:
            logger.exception("Unhandled error in detector.run – returning empty incidents")
            return [], frame