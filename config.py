"""
UPSMS configuration: thresholds, timings, and resource names.
"""
import os
from pathlib import Path

# Detection confidence (reduce false positives)
CONFIDENCE_THRESHOLD = 0.5        

# Rolling buffer
BUFFER_DURATION_SEC = 10
DEFAULT_FPS = 30

# Accident detection
VEHICLE_CLASS_IDS = (2, 3, 7)  # COCO: car=2, motorcycle=3, truck=7
ACCIDENT_VELOCITY_DROP_RATIO = 0.80  # flag if velocity drops by >80%
ACCIDENT_OVERLAP_FRAMES = 2  # require overlap for N consecutive frames
ACCIDENT_VELOCITY_HISTORY_FRAMES = 10

# Fall (medical) detection - pose keypoints 0-based: 0=nose, 11=left_hip, 12=right_hip
KEYPOINT_NOSE = 0
KEYPOINT_LEFT_HIP = 11
KEYPOINT_RIGHT_HIP = 12
FALL_ANGLE_DEG_THRESHOLD = 30  # torso < 30° to ground = horizontal
FALL_STATIC_DURATION_SEC = 5
FALL_ANGLE_STATIC_TOLERANCE_DEG = 5  # angle change below this = static
FALL_POSITION_STATIC_PX = 10  # mid-hip movement below this = static

# Harassment (conflict) detection - keypoints: 9=left_wrist, 10=right_wrist
KEYPOINT_LEFT_WRIST = 9
KEYPOINT_RIGHT_WRIST = 10
CONFLICT_PROXIMITY_PX = 120  # ~1m equivalent; tune per camera (no calibration)
CONFLICT_PROXIMITY_DURATION_SEC = 5
CONFLICT_STRUGGLE_WINDOW_SEC = 2
CONFLICT_STRUGGLE_VARIANCE_THRESHOLD = 50.0  # wrist displacement variance

# Stalking detection
STALKING_DISTANCE_PX = 150           # how close the follower stays (pixels)
STALKING_DURATION_SEC = 3           # how long they must follow
STALKING_ANGLE_TOLERANCE_DEG = 30    # follower should be roughly behind the target

# Isolation detection
ISOLATION_RADIUS_PX = 200            # consider a person isolated if no others within this radius
ISOLATION_DURATION_SEC = 15          # how long they must be alone

# Gang detection
GANG_MIN_MEMBERS = 3                  # minimum persons surrounding one
GANG_PROXIMITY_PX = 150               # how close they must be to the target
GANG_DURATION_SEC = 2                # how long they must maintain formation

# Incident handling
INCIDENT_COOLDOWN_SEC = 45  # per event type
STORAGE_BUCKET = "incident-clips"
INCIDENTS_TABLE = "incidents"
CLIPS_OUTPUT_DIR = Path(os.getenv("CLIPS_OUTPUT_DIR", "incident_clips"))
DEFAULT_LOCATION = "unknown"

# Severity mapping
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
EVENT_ACCIDENT = "ACCIDENT"
EVENT_MEDICAL = "MEDICAL"
EVENT_CONFLICT = "CONFLICT"

EVENT_STALKING = "STALKING"
EVENT_ISOLATION = "ISOLATION"
EVENT_GANG = "GANG"