"""
UPSMS main execution loop: video capture, rolling buffer, detector, incident handling.
"""
import collections
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import cv2
import requests
from dotenv import load_dotenv

from config import (
    BUFFER_DURATION_SEC,
    CLIPS_OUTPUT_DIR,
    DEFAULT_FPS,
    DEFAULT_LOCATION,
    INCIDENT_COOLDOWN_SEC,
)
from database_manager import insert_incident, upload_incident_clip
from detector import UPSMSDetector, Incident

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("UPSMS")


def _trigger_n8n_webhook(payload: dict) -> bool:
    """POST JSON to n8n webhook URL. Returns True on success."""
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url:
        logger.warning("N8N_WEBHOOK_URL not set; skipping webhook")
        return False
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("n8n webhook triggered successfully")
        return True
    except Exception as e:
        logger.exception("n8n webhook failed: %s", e)
        return False


def _save_buffer_to_clip(
    buffer: collections.deque,
    width: int,
    height: int,
    fps: float,
    out_path: Path,
) -> bool:
    """Write all frames in buffer to out_path as MP4. Returns True on success."""
    if len(buffer) == 0:
        logger.warning("Buffer empty; cannot save clip")
        return False
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        logger.error("Failed to open VideoWriter for %s", out_path)
        return False
    for frame in buffer:
        writer.write(frame)
    writer.release()
    logger.info("Saved incident clip: %s (%d frames)", out_path, len(buffer))
    return True


def run(video_source):
    """
    Open video source (file path or device index), maintain rolling buffer,
    run detector, on incident: save clip, upload to Supabase, insert row, trigger n8n.
    """
    logger.info("Starting UPSMS pipeline; video_source=%s", video_source)
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        logger.error("Could not open video source: %s", video_source)
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or DEFAULT_FPS
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    buffer_maxlen = max(1, int(BUFFER_DURATION_SEC * fps))
    buffer = collections.deque(maxlen=buffer_maxlen)
    detector = UPSMSDetector(fps=fps)
    cooldown_until: dict[str, float] = {}
    CLIPS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.info("End of stream or read error; exiting")
                break
            frame_count += 1
            buffer.append(frame.copy())
            incidents = detector.run(frame)
            now_ts = datetime.now(timezone.utc)
            now_sec = frame_count / fps

            for inc in incidents:
                event_type = inc.event_type
                if event_type in cooldown_until and now_sec < cooldown_until[event_type]:
                    logger.debug("Incident %s in cooldown; skipping", event_type)
                    continue
                timestamp_str = now_ts.strftime("%Y%m%d_%H%M%S")
                clip_name = f"incident_{timestamp_str}.mp4"
                out_path = CLIPS_OUTPUT_DIR / clip_name
                if not _save_buffer_to_clip(buffer, width, height, fps, out_path):
                    continue
                clip_url = out_path.name
                try:
                    clip_url = upload_incident_clip(out_path, object_name=clip_name)
                except Exception as e:
                    logger.exception("Upload failed; clip saved locally: %s", e)
                try:
                    insert_incident(
                        event_type=event_type,
                        severity=inc.severity,
                        location=DEFAULT_LOCATION,
                        clip_url=clip_url,
                        timestamp=now_ts,
                    )
                except Exception as e:
                    logger.exception("Insert incident failed: %s", e)
                    continue
                payload = {
                    "event": event_type,
                    "severity": inc.severity,
                    "location": DEFAULT_LOCATION,
                    "timestamp": now_ts.isoformat() + "Z",
                    "clip_url": clip_url,
                }
                _trigger_n8n_webhook(payload)
                cooldown_until[event_type] = now_sec + INCIDENT_COOLDOWN_SEC
                logger.info("Incident handled: type=%s clip=%s", event_type, clip_name)
    finally:
        cap.release()
    logger.info("UPSMS pipeline finished; processed %d frames", frame_count)


if __name__ == "__main__":
    from main import main
    main()
