import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Incident } from "@/types/incident";

// Fix default marker icons
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

const severityColors: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

interface IncidentMapProps {
  incidents: Incident[];
  onSelectIncident?: (incident: Incident) => void;
}

export function IncidentMap({ incidents, onSelectIncident }: IncidentMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    mapInstance.current = L.map(mapRef.current, {
      zoomControl: false,
    }).setView([20, 0], 2);

    L.control.zoom({ position: "bottomright" }).addTo(mapInstance.current);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
      maxZoom: 19,
    }).addTo(mapInstance.current);

    return () => {
      mapInstance.current?.remove();
      mapInstance.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapInstance.current) return;

    // Clear existing markers
    mapInstance.current.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        mapInstance.current!.removeLayer(layer);
      }
    });

    incidents.forEach((incident) => {
      const coords = incident.coordinates as { lat: number; lng: number };
      if (!coords?.lat || !coords?.lng) return;

      const color = severityColors[incident.severity] || severityColors.low;
      const radius = incident.severity === "critical" ? 10 : incident.severity === "high" ? 8 : 6;

      const marker = L.circleMarker([coords.lat, coords.lng], {
        radius,
        fillColor: color,
        color: color,
        weight: 2,
        opacity: 0.8,
        fillOpacity: 0.4,
      }).addTo(mapInstance.current!);

      marker.bindPopup(`
        <div style="font-family: Inter, sans-serif; color: #e2e8f0;">
          <strong>${incident.event_type}</strong><br/>
          <span style="color: ${color}; text-transform: uppercase; font-size: 11px; font-weight: 700;">${incident.severity}</span><br/>
          <span style="font-size: 12px;">${incident.location}</span>
        </div>
      `, {
        className: "dark-popup",
      });

      if (onSelectIncident) {
        marker.on("click", () => onSelectIncident(incident));
      }
    });

    // Fit bounds if incidents exist
    const validCoords = incidents
      .map((i) => i.coordinates as { lat: number; lng: number })
      .filter((c) => c?.lat && c?.lng);

    if (validCoords.length > 0) {
      const bounds = L.latLngBounds(validCoords.map((c) => [c.lat, c.lng]));
      mapInstance.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
    }
  }, [incidents, onSelectIncident]);

  return (
    <div className="relative w-full h-full min-h-[300px] rounded-lg overflow-hidden border border-border">
      <div ref={mapRef} className="w-full h-full" />
      <style>{`
        .dark-popup .leaflet-popup-content-wrapper {
          background: hsl(220 18% 10%);
          border: 1px solid hsl(220 16% 18%);
          border-radius: 8px;
          box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        }
        .dark-popup .leaflet-popup-tip {
          background: hsl(220 18% 10%);
        }
        .dark-popup .leaflet-popup-content {
          margin: 8px 12px;
          color: #e2e8f0;
        }
        .leaflet-control-zoom a {
          background: hsl(220 18% 10%) !important;
          color: hsl(210 20% 80%) !important;
          border-color: hsl(220 16% 18%) !important;
        }
      `}</style>
    </div>
  );
}
