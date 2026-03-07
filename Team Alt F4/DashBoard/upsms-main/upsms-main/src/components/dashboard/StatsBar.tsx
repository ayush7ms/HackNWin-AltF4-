import { AlertTriangle, Activity, Shield, TrendingUp } from "lucide-react";
import type { Incident } from "@/types/incident";

interface StatsBarProps {
  incidents: Incident[];
}

export function StatsBar({ incidents }: StatsBarProps) {
  const total = incidents.length;
  const critical = incidents.filter((i) => i.severity === "critical").length;
  const high = incidents.filter((i) => i.severity === "high").length;
  const today = incidents.filter((i) => {
    const d = new Date(i.timestamp);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  }).length;

  const stats = [
    { label: "Total Incidents", value: total, icon: Activity, color: "text-primary" },
    { label: "Critical", value: critical, icon: AlertTriangle, color: "text-severity-critical" },
    { label: "High Severity", value: high, icon: Shield, color: "text-severity-high" },
    { label: "Today", value: today, icon: TrendingUp, color: "text-primary" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <stat.icon className={`h-4 w-4 ${stat.color}`} />
            <span className="text-xs text-muted-foreground uppercase tracking-wider font-mono">{stat.label}</span>
          </div>
          <div className={`text-2xl font-bold font-mono ${stat.color}`}>{stat.value}</div>
        </div>
      ))}
    </div>
  );
}
