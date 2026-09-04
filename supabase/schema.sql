-- Esquema para el histórico de Garmin.
-- Ejecuta esto una vez en el SQL Editor de tu proyecto de Supabase.

create table if not exists daily_summary (
  date date primary key,
  steps integer,
  resting_hr integer,
  stress_avg integer,
  body_battery_min integer,
  body_battery_max integer,
  sleep_score integer,
  sleep_duration_sec integer,
  hrv_avg numeric,
  weight_kg numeric,
  raw jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists activities (
  activity_id bigint primary key,
  start_time timestamptz not null,
  activity_type text,
  name text,
  distance_m numeric,
  duration_sec numeric,
  avg_hr integer,
  max_hr integer,
  avg_pace_min_km numeric,
  elevation_gain_m numeric,
  calories integer,
  cadence_spm integer,
  stride_length_cm numeric,
  ground_contact_time_ms numeric,
  vertical_oscillation_cm numeric,
  training_effect numeric,
  raw jsonb,
  updated_at timestamptz not null default now()
);

-- Si esta tabla ya existía de una corrida anterior, agrega las columnas nuevas:
alter table activities add column if not exists cadence_spm integer;
alter table activities add column if not exists stride_length_cm numeric;
alter table activities add column if not exists ground_contact_time_ms numeric;
alter table activities add column if not exists vertical_oscillation_cm numeric;
alter table activities add column if not exists training_effect numeric;

create index if not exists idx_activities_start_time on activities (start_time desc);
create index if not exists idx_activities_type on activities (activity_type);

-- Nadie puede leer/escribir directo desde el navegador: solo el backend
-- (con la service role key) toca estas tablas. Por eso dejamos RLS activado
-- sin políticas — así ni el anon key puede leer nada por accidente.
alter table daily_summary enable row level security;
alter table activities enable row level security;
