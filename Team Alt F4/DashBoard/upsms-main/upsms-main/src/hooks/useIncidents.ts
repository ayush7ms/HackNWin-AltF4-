import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import type { Incident } from "@/types/incident";

export function useIncidents() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchIncidents = async () => {
    const { data, error } = await supabase
      .from("incidents")
      .select("*")
      .order("timestamp", { ascending: false })
      .limit(50);

    if (!error && data) {
      setIncidents(data as unknown as Incident[]);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchIncidents();

    const channel = supabase
      .channel("incidents-realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "incidents" },
        (payload) => {
          const newIncident = payload.new as unknown as Incident;
          setIncidents((prev) => [newIncident, ...prev].slice(0, 50));

          // Browser notification
          if (Notification.permission === "granted") {
            new Notification(`🚨 ${newIncident.event_type}`, {
              body: `${newIncident.severity.toUpperCase()} severity at ${newIncident.location}`,
              icon: "/favicon.ico",
            });
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  return { incidents, loading, refetch: fetchIncidents };
}
