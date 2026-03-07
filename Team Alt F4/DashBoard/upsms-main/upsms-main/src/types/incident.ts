export interface Incident {
  id: string;
  event_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  location: string;
  coordinates: { lat: number; lng: number };
  timestamp: string;
  clip_url: string | null;
  created_at: string;
}
