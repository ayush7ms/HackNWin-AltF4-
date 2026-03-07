
-- Create incidents table
CREATE TABLE public.incidents (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  location TEXT NOT NULL,
  coordinates JSONB NOT NULL DEFAULT '{"lat": 0, "lng": 0}',
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  clip_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;

-- Allow public read access
CREATE POLICY "Anyone can view incidents" ON public.incidents FOR SELECT USING (true);

-- Allow authenticated insert
CREATE POLICY "Authenticated users can insert incidents" ON public.incidents FOR INSERT TO authenticated WITH CHECK (true);

-- Create settings table
CREATE TABLE public.system_settings (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view settings" ON public.system_settings FOR SELECT USING (true);
CREATE POLICY "Authenticated users can upsert settings" ON public.system_settings FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated users can update settings" ON public.system_settings FOR UPDATE TO authenticated USING (true);
