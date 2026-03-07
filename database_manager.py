"""
Supabase CRUD: client init, upload to incident-clips bucket, insert into incidents table.
Includes retry logic and fallback to local storage on network failure.
"""
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("UPSMS.database")

_SUPABASE_CLIENT = None
# Local fallback directory for clips when upload fails
FALLBACK_CLIP_DIR = Path("local_incident_clips")
FALLBACK_CLIP_DIR.mkdir(exist_ok=True)


def _get_client():
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is None:
        # HARDCODED FOR HACKATHON DEMO – replace with env vars later
        url = "https://begkeadhbkehmprzwovv.supabase.co"
        key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJlZ2tlYWRoYmtlaG1wcnp3b3Z2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI4NTU1NjEsImV4cCI6MjA4ODQzMTU2MX0.prCfC1FZYaafWS2LcxjN2KjtT3YRlK_x_CY596XhKbE"
        
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set!")
            
        from supabase import create_client
        _SUPABASE_CLIENT = create_client(url, key)
        logger.info("Supabase client initialized with hardcoded keys")
    return _SUPABASE_CLIENT


def upload_incident_clip(file_path: str | Path, object_name: str | None = None, max_retries=3) -> str:
    """
    Upload a video file to Supabase Storage bucket 'incident-clips'.
    Returns a public URL if successful, otherwise returns a local fallback path.
    Retries up to `max_retries` times on network errors.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Clip file not found: {file_path}")
    
    name = object_name or path.name
    client = _get_client()
    
    # Attempt upload with retries
    for attempt in range(1, max_retries + 1):
        try:
            with open(path, "rb") as f:
                data = f.read()
            client.storage.from_("incident-clips").upload(
                name,
                data,
                {"content-type": "video/mp4", "upsert": "true"},
            )
            logger.info("Uploaded incident clip: %s (attempt %d)", name, attempt)
            # Get public URL
            try:
                public_url = client.storage.from_("incident-clips").get_public_url(name)
                return public_url
            except Exception:
                # If we can't get public URL, return the path (maybe bucket is private)
                return name
        except Exception as e:
            logger.warning("Upload attempt %d failed for %s: %s", attempt, name, e)
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                # All retries exhausted – fallback to local storage
                logger.error("All upload attempts failed. Storing clip locally.")
                fallback_path = FALLBACK_CLIP_DIR / name
                # Copy the file to fallback directory (or just return original path)
                import shutil
                shutil.copy2(path, fallback_path)
                logger.info("Local fallback copy created at %s", fallback_path)
                return str(fallback_path)


def insert_incident(
    event_type: str,
    severity: str,
    location: str,
    clip_url: str,  # can be a local path or remote URL
    timestamp: datetime | None = None,
) -> dict | None:
    """
    Insert a row into the incidents table.
    Returns the inserted row (or a dict with fallback info) if successful,
    otherwise returns None (does not raise).
    """
    from config import INCIDENTS_TABLE
    ts = timestamp or datetime.now(timezone.utc)
    row = {
        "type": event_type,
        "severity": severity,
        "location": location,
        "clip_url": clip_url,
        "created_at": ts.isoformat(timespec='milliseconds')
    }
    client = _get_client()
    try:
        resp = client.table(INCIDENTS_TABLE).insert(row).execute()
        logger.info("Inserted incident: type=%s severity=%s", event_type, severity)
        if resp.data and len(resp.data) > 0:
            return resp.data[0]
        return row
    except Exception as e:
        logger.exception("Failed to insert incident into database: %s", e)
        # Return the local row as a fallback so caller knows it was logged locally
        return row