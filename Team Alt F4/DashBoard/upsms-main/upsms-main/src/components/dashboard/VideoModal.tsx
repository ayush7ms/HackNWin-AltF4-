import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SeverityBadge } from "./SeverityBadge";
import type { Incident } from "@/types/incident";
import { format } from "date-fns";
import { MapPin, Clock } from "lucide-react";

interface VideoModalProps {
  incident: Incident | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function VideoModal({ incident, open, onOpenChange }: VideoModalProps) {
  if (!incident) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {incident.event_type}
            <SeverityBadge severity={incident.severity} />
          </DialogTitle>
          <div className="flex items-center gap-4 text-sm text-muted-foreground pt-1">
            <span className="flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" />
              {incident.location}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {format(new Date(incident.timestamp), "PPpp")}
            </span>
          </div>
        </DialogHeader>

        <div className="mt-2 rounded-lg overflow-hidden bg-background border border-border">
          {incident.clip_url ? (
            <video
              src={incident.clip_url}
              controls
              autoPlay
              className="w-full aspect-video"
            />
          ) : (
            <div className="flex items-center justify-center aspect-video text-muted-foreground text-sm">
              No video evidence available
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
