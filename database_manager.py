"""
Supabase CRUD: client init, upload to incident-clips bucket, insert into incidents table.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("UPSMS.database")

_SUPABASE_CLIENT = None


def _get_client():
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        from supabase import create_client
        _SUPABASE_CLIENT = create_client(url, key)
        logger.info("Supabase client initialized")
    return _SUPABASE_CLIENT


def upload_incident_clip(file_path: str | Path, object_name: str | None = None) -> str:
    """
    Upload a video file to Supabase Storage bucket 'incident-clips'.
    Returns the public URL or path for the stored object.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Clip file not found: {file_path}")
    name = object_name or path.name
    client = _get_client()
    with open(path, "rb") as f:
        data = f.read()
    try:
        client.storage.from_("incident-clips").upload(
            name,
            data,
            {"content-type": "video/mp4", "upsert": "true"},
        )
        logger.info("Uploaded incident clip: %s", name)
    except Exception as e:
        logger.exception("Failed to upload incident clip %s: %s", name, e)
        raise
    # Build public URL (bucket must be public or use get_public_url if available)
    try:
        public = client.storage.from_("incident-clips").get_public_url(name)
        return public
    except Exception:
        return name


def insert_incident(
    event_type: str,
    severity: str,
    location: str,
    clip_url: str,
    timestamp: datetime | None = None,
) -> dict | None:
    """
    Insert a row into the incidents table.
    Returns the inserted row or None on failure.
    """
    from config import INCIDENTS_TABLE
    ts = timestamp or datetime.now(timezone.utc)
    row = {
        "type": event_type,
        "severity": severity,
        "location": location,
        "clip_url": clip_url,
        "created_at": ts.isoformat() + "Z",
    }
    client = _get_client()
    try:
        resp = client.table(INCIDENTS_TABLE).insert(row).execute()
        logger.info("Inserted incident: type=%s severity=%s", event_type, severity)
        if resp.data and len(resp.data) > 0:
            return resp.data[0]
        return row
    except Exception as e:
        logger.exception("Failed to insert incident: %s", e)
        raise
