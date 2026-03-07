"""
UPSMS app.py - FINAL HACKATHON VERSION
"""
import collections
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import cv2
import requests
from dotenv import load_dotenv

from config import BUFFER_DURATION_SEC, CLIPS_OUTPUT_DIR, DEFAULT_FPS, DEFAULT_LOCATION, INCIDENT_COOLDOWN_SEC
from database_manager import insert_incident, upload_incident_clip
from detector import UPSMSDetector, Incident

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("UPSMS")

def _trigger_n8n_webhook(payload: dict):
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url: return False
    try:
        r = requests.post(url, json=payload, timeout=10)
        logger.info("n8n alert sent!")
        return True
    except: return False

def _save_buffer_to_clip(buffer, width, height, fps, out_path):
    if not buffer: return False
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for frame in buffer: writer.write(frame)
    writer.release()
    return True

def run(video_source):
    logger.info("Starting UPSMS Live Feed...")
    cap = cv2.VideoCapture(video_source)
    fps = cap.get(cv2.CAP_PROP_FPS) or DEFAULT_FPS
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    buffer = collections.deque(maxlen=max(1, int(BUFFER_DURATION_SEC * fps)))
    detector = UPSMSDetector(fps=fps)
    cooldown_until, frame_count = {}, 0
    CLIPS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            frame_count += 1
            buffer.append(frame.copy())
            
            # --- GET ANNOTATED FRAME FROM AI ---
            incidents, annotated_frame = detector.run(frame)

            # --- LIVE DEMO DISPLAY ---
            cv2.imshow("UPSMS Live - Team Alt F4", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

            now_ts = datetime.now(timezone.utc)
            now_sec = frame_count / fps

            for inc in incidents:
                if inc.event_type in cooldown_until and now_sec < cooldown_until[inc.event_type]: continue
                
                clip_name = f"incident_{now_ts.strftime('%Y%m%d_%H%M%S')}.mp4"
                out_path = CLIPS_OUTPUT_DIR / clip_name
                
                if _save_buffer_to_clip(buffer, width, height, fps, out_path):
                    try:
                        url = upload_incident_clip(out_path, object_name=clip_name)
                        insert_incident(inc.event_type, inc.severity, DEFAULT_LOCATION, url, now_ts)
                        _trigger_n8n_webhook({"event": inc.event_type, "severity": inc.severity, "url": url})
                        cooldown_until[inc.event_type] = now_sec + INCIDENT_COOLDOWN_SEC
                        logger.info(f"ALERT: {inc.event_type} handled and uploaded!")
                    except Exception as e: logger.error(f"Incident handling failed: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    from main import main
    main()