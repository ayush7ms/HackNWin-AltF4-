import { useState } from "react";
import { useIncidents } from "@/hooks/useIncidents";
import { IncidentMap } from "@/components/dashboard/IncidentMap";
import { VideoModal } from "@/components/dashboard/VideoModal";
import type { Incident } from "@/types/incident";

export default function MapView() {
  const { incidents } = useIncidents();
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [videoOpen, setVideoOpen] = useState(false);

  const handleSelect = (incident: Incident) => {
    setSelectedIncident(incident);
    setVideoOpen(true);
  };

  return (
    <div className="flex-1 flex flex-col p-4 lg:p-6">
      <div className="mb-4">
        <h1 className="text-xl font-bold tracking-tight">Map View</h1>
        <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider mt-0.5">
          Geographic incident distribution
        </p>
      </div>
      <div className="flex-1 min-h-[500px]">
        <IncidentMap incidents={incidents} onSelectIncident={handleSelect} />
      </div>
      <VideoModal incident={selectedIncident} open={videoOpen} onOpenChange={setVideoOpen} />
    </div>
  );
}
