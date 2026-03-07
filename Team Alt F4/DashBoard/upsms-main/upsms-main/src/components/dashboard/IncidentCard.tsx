import { AlertTriangle, Car, HeartPulse, Swords, Play, Clock, MapPin } from "lucide-react";
import { cn } from "@/lib/utils";
import { SeverityBadge } from "./SeverityBadge";
import { Button } from "@/components/ui/button";
import type { Incident } from "@/types/incident";
import { format } from "date-fns";

const eventIcons: Record<string, React.ElementType> = {
  Accident: Car,
  Medical: HeartPulse,
  Conflict: Swords,
};

interface IncidentCardProps {
  incident: Incident;
  onViewEvidence: (incident: Incident) => void;
}

export function IncidentCard({ incident, onViewEvidence }: IncidentCardProps) {
  const Icon = eventIcons[incident.event_type] || AlertTriangle;
  const isHighSeverity = incident.severity === "critical" || incident.severity === "high";

  return (
    <div
      className={cn(
        "group relative rounded-lg border bg-card p-4 transition-all hover:border-primary/30",
        isHighSeverity && "border-severity-critical/30 pulse-danger"
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn(
          "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
          isHighSeverity ? "bg-severity-critical/10" : "bg-primary/10"
        )}>
          <Icon className={cn("h-5 w-5", isHighSeverity ? "text-severity-critical" : "text-primary")} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-semibold text-sm truncate">{incident.event_type}</span>
            <SeverityBadge severity={incident.severity} />
          </div>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {incident.location}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {format(new Date(incident.timestamp), "HH:mm:ss")}
            </span>
          </div>
        </div>

        {incident.clip_url && (
          <Button
            size="sm"
            variant="outline"
            className="shrink-0 border-primary/30 text-primary hover:bg-primary/10 hover:text-primary"
            onClick={() => onViewEvidence(incident)}
          >
            <Play className="h-3 w-3 mr-1" />
            Evidence
          </Button>
        )}
      </div>
    </div>
  );
}
