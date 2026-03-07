import { cn } from "@/lib/utils";

const severityConfig = {
  critical: { label: "CRITICAL", className: "bg-severity-critical/20 text-severity-critical border-severity-critical/40 pulse-danger" },
  high: { label: "HIGH", className: "bg-severity-high/20 text-severity-high border-severity-high/40" },
  medium: { label: "MEDIUM", className: "bg-severity-medium/20 text-severity-medium border-severity-medium/40" },
  low: { label: "LOW", className: "bg-severity-low/20 text-severity-low border-severity-low/40" },
};

export function SeverityBadge({ severity }: { severity: string }) {
  const config = severityConfig[severity as keyof typeof severityConfig] || severityConfig.low;

  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider border", config.className)}>
      {config.label}
    </span>
  );
}
