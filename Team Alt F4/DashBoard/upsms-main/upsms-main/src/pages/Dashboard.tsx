import { useState } from "react";
import { useIncidents } from "@/hooks/useIncidents";
import { IncidentCard } from "@/components/dashboard/IncidentCard";
import { VideoModal } from "@/components/dashboard/VideoModal";
import { IncidentMap } from "@/components/dashboard/IncidentMap";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { SeverityBadge } from "@/components/dashboard/SeverityBadge";
import type { Incident } from "@/types/incident";
import { Radio, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Dashboard() {
  const { incidents, loading, refetch } = useIncidents();
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [videoOpen, setVideoOpen] = useState(false);

  const handleViewEvidence = (incident: Incident) => {
    setSelectedIncident(incident);
    setVideoOpen(true);
  };

  return (
    <div className="flex-1 flex flex-col gap-4 p-4 lg:p-6 overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            Incident Command Center
            <Radio className="h-4 w-4 text-primary animate-pulse" />
          </h1>
          <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider mt-0.5">
            Real-time monitoring • {incidents.length} incidents tracked
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refetch} className="border-border text-muted-foreground hover:text-foreground">
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          Refresh
        </Button>
      </div>

      {/* Stats */}
      <StatsBar incidents={incidents} />

      {/* Main Content */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 flex-1 min-h-0">
        {/* Live Feed */}
        <div className="flex flex-col rounded-lg border bg-card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b bg-secondary/30">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-severity-critical animate-pulse" />
              Live Feed
            </h2>
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              {incidents.length} events
            </span>
          </div>
          <div className="flex-1 overflow-auto p-3 space-y-2">
            {loading ? (
              <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
                Loading incidents...
              </div>
            ) : incidents.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
                No incidents reported. System clear.
              </div>
            ) : (
              incidents.map((incident) => (
                <IncidentCard
                  key={incident.id}
                  incident={incident}
                  onViewEvidence={handleViewEvidence}
                />
              ))
            )}
          </div>
        </div>

        {/* Map */}
        <div className="flex flex-col rounded-lg border bg-card overflow-hidden min-h-[400px]">
          <div className="flex items-center justify-between px-4 py-3 border-b bg-secondary/30">
            <h2 className="text-sm font-semibold">Incident Map</h2>
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              Global View
            </span>
          </div>
          <div className="flex-1">
            <IncidentMap incidents={incidents} onSelectIncident={handleViewEvidence} />
          </div>
        </div>
      </div>

      <VideoModal incident={selectedIncident} open={videoOpen} onOpenChange={setVideoOpen} />
    </div>
  );
}
