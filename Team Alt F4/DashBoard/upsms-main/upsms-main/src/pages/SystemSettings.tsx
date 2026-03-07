import { useState, useEffect } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Save, Bell, Webhook, ExternalLink } from "lucide-react";

export default function SystemSettings() {
  const [webhookUrl, setWebhookUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(Notification.permission === "granted");

  useEffect(() => {
    const fetchSettings = async () => {
      const { data } = await supabase
        .from("system_settings")
        .select("*")
        .eq("key", "n8n_webhook_url")
        .maybeSingle();
      if (data) setWebhookUrl(data.value);
    };
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    const { error } = await supabase
      .from("system_settings")
      .upsert({ key: "n8n_webhook_url", value: webhookUrl }, { onConflict: "key" });

    if (error) {
      toast.error("Failed to save webhook URL");
    } else {
      toast.success("Webhook URL saved successfully");
    }
    setSaving(false);
  };

  const requestNotifications = async () => {
    const permission = await Notification.requestPermission();
    setNotificationsEnabled(permission === "granted");
    if (permission === "granted") {
      toast.success("Browser notifications enabled");
      new Notification("🛡️ UPSMS Notifications Active", {
        body: "You will now receive alerts for new incidents.",
      });
    } else {
      toast.error("Notification permission denied");
    }
  };

  return (
    <div className="flex-1 p-4 lg:p-6 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold tracking-tight">System Settings</h1>
        <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider mt-0.5">
          Configure alerts and integrations
        </p>
      </div>

      <div className="space-y-6">
        {/* Notifications */}
        <div className="rounded-lg border bg-card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Bell className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">Browser Notifications</h2>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Receive real-time browser alerts when new incidents are detected.
          </p>
          <Button
            variant={notificationsEnabled ? "outline" : "default"}
            onClick={requestNotifications}
            disabled={notificationsEnabled}
            className={notificationsEnabled ? "border-success/30 text-success" : ""}
          >
            {notificationsEnabled ? "✓ Notifications Enabled" : "Enable Notifications"}
          </Button>
        </div>

        {/* Webhook */}
        <div className="rounded-lg border bg-card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Webhook className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">n8n Webhook URL</h2>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Enter your n8n webhook endpoint to trigger automated alert workflows (Pushcut, Telegram, WhatsApp, etc.)
          </p>
          <div className="space-y-3">
            <div>
              <Label htmlFor="webhook" className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                Webhook URL
              </Label>
              <Input
                id="webhook"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="https://your-n8n-instance.com/webhook/..."
                className="mt-1 bg-background border-border font-mono text-sm"
              />
            </div>
            <Button onClick={handleSave} disabled={saving} className="bg-primary text-primary-foreground hover:bg-primary/90">
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {saving ? "Saving..." : "Save Webhook URL"}
            </Button>
          </div>
        </div>

        {/* Info */}
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-5">
          <h3 className="text-sm font-semibold mb-2 text-primary">How the Alert Loop Works</h3>
          <ol className="text-sm text-muted-foreground space-y-1.5 list-decimal list-inside">
            <li>AI detection identifies an incident (fall, accident, conflict)</li>
            <li>Clip is saved to storage, data inserted into the incidents table</li>
            <li>Python script triggers your n8n webhook</li>
            <li>n8n sends a push notification (Pushcut/Telegram/WhatsApp)</li>
            <li>User clicks the link → opens this dashboard to the incident</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
