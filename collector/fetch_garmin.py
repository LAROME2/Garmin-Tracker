#!/usr/bin/env python3
"""
Recolector de datos de Garmin Connect -> Supabase.

Se ejecuta desde GitHub Actions (cron diario) o localmente.
Usa la misma librería (garminconnect) que garmin_mcp, pero en vez de
responder preguntas en vivo, guarda el histórico en una base de datos.

Variables de entorno requeridas:
  GARMIN_TOKENS_B64      tokens OAuth de Garmin, tar+gzip+base64 (ver README)
  SUPABASE_URL           https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY   service_role key (NUNCA la anon key aquí)

Variables opcionales:
  FETCH_DAYS             cuántos días hacia atrás traer (default 5)
  BACKFILL_DAYS          si se pasa, ignora FETCH_DAYS y trae ese rango
                         (úsalo una sola vez para cargar los primeros 90 días)
  GARMIN_IS_CN           "true" si usas Garmin Connect China
  DRY_RUN                "true" -> no llama a Supabase, imprime lo que haría
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import tarfile
import tempfile
from datetime import date, timedelta
from typing import Any, Optional

import requests
from garminconnect import Garmin


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------

def load_garmin_client() -> Garmin:
    """Reconstruye el directorio de tokens desde el secret y arma el cliente."""
    tokens_b64 = os.environ.get("GARMIN_TOKENS_B64")
    if not tokens_b64:
        raise SystemExit(
            "Falta GARMIN_TOKENS_B64. Genera tokens con garmin-mcp-auth y "
            "empácalos como se explica en el README antes de correr esto."
        )

    token_dir = tempfile.mkdtemp(prefix="garmin_tokens_")
    raw = base64.b64decode(tokens_b64)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(token_dir)

    is_cn = os.environ.get("GARMIN_IS_CN", "false").lower() in ("1", "true", "yes")
    client = Garmin(is_cn=is_cn)
    client.login(token_dir)
    return client


# --------------------------------------------------------------------------
# Supabase (REST / PostgREST) — sin dependencias extra, solo requests
# --------------------------------------------------------------------------

class Supabase:
    def __init__(self, url: str, service_key: str, dry_run: bool = False):
        self.url = url.rstrip("/")
        self.key = service_key
        self.dry_run = dry_run

    def upsert(self, table: str, rows: list[dict[str, Any]], conflict_col: str) -> None:
        if not rows:
            return
        if self.dry_run:
            print(f"[dry-run] upsert {len(rows)} filas -> {table} (conflict={conflict_col})")
            print(json.dumps(rows[:2], indent=2, default=str))
            return

        resp = requests.post(
            f"{self.url}/rest/v1/{table}",
            params={"on_conflict": conflict_col},
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            data=json.dumps(rows, default=str),
            timeout=30,
        )
        if resp.status_code >= 300:
            raise RuntimeError(
                f"Supabase upsert falló en '{table}' ({resp.status_code}): {resp.text}"
            )


# --------------------------------------------------------------------------
# Transformación de datos de Garmin -> filas de la base
# --------------------------------------------------------------------------

def safe(fn, *args, **kwargs) -> Optional[Any]:
    """Llama a un endpoint de Garmin sin tumbar todo el run si uno falla."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - queremos seguir con lo demás
        print(f"  [warn] {fn.__name__ if hasattr(fn, '__name__') else fn}: {exc}", file=sys.stderr)
        return None


def build_daily_summary(client: Garmin, day: date) -> dict[str, Any]:
    d = day.isoformat()
    stats = safe(client.get_stats, d) or {}
    sleep = safe(client.get_sleep_data, d) or {}
    hrv = safe(client.get_hrv_data, d) or {}

    sleep_summary = (sleep or {}).get("dailySleepDTO") or {}
    hrv_summary = (hrv or {}).get("hrvSummary") or {}

    return {
        "date": d,
        "steps": stats.get("totalSteps"),
        "resting_hr": stats.get("restingHeartRate"),
        "stress_avg": stats.get("averageStressLevel"),
        "body_battery_min": stats.get("bodyBatteryLowestValue"),
        "body_battery_max": stats.get("bodyBatteryHighestValue"),
        "sleep_score": sleep_summary.get("sleepScores", {}).get("overall", {}).get("value")
        if isinstance(sleep_summary.get("sleepScores"), dict)
        else None,
        "sleep_duration_sec": sleep_summary.get("sleepTimeSeconds"),
        "hrv_avg": hrv_summary.get("lastNightAvg"),
        "weight_kg": None,  # se agrega abajo si hay dato de báscula ese día
        "raw": {"stats": stats, "sleep": sleep_summary, "hrv": hrv_summary},
    }


def build_activity_row(act: dict[str, Any]) -> Optional[dict[str, Any]]:
    activity_id = act.get("activityId")
    if activity_id is None:
        return None

    distance_m = act.get("distance")
    duration_sec = act.get("duration")
    avg_speed = act.get("averageSpeed")  # m/s
    avg_pace_min_km = None
    if avg_speed and avg_speed > 0:
        avg_pace_min_km = round((1000 / avg_speed) / 60, 3)

    activity_type = None
    if isinstance(act.get("activityType"), dict):
        activity_type = act["activityType"].get("typeKey")

    return {
        "activity_id": activity_id,
        "start_time": act.get("startTimeGMT") or act.get("startTimeLocal"),
        "activity_type": activity_type,
        "name": act.get("activityName"),
        "distance_m": distance_m,
        "duration_sec": duration_sec,
        "avg_hr": act.get("averageHR"),
        "max_hr": act.get("maxHR"),
        "avg_pace_min_km": avg_pace_min_km,
        "elevation_gain_m": act.get("elevationGain"),
        "calories": act.get("calories"),
        "raw": act,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not dry_run and (not supabase_url or not supabase_key):
        raise SystemExit("Faltan SUPABASE_URL / SUPABASE_SERVICE_KEY (o usa DRY_RUN=true).")

    backfill_days = os.environ.get("BACKFILL_DAYS")
    fetch_days = int(backfill_days) if backfill_days else int(os.environ.get("FETCH_DAYS", "5"))

    today = date.today()
    start_day = today - timedelta(days=fetch_days)

    print(f"Trayendo datos de Garmin del {start_day} al {today} (dry_run={dry_run})...")

    client = load_garmin_client() if not dry_run else _FakeClientForDryRun()
    db = Supabase(supabase_url, supabase_key, dry_run=dry_run)

    # --- métricas diarias ---
    daily_rows = []
    d = start_day
    while d <= today:
        daily_rows.append(build_daily_summary(client, d))
        d += timedelta(days=1)
    db.upsert("daily_summary", daily_rows, conflict_col="date")
    print(f"  {len(daily_rows)} días de métricas procesados.")

    # --- actividades (carreras, ciclismo, etc.) ---
    activities = safe(
        client.get_activities_by_date, start_day.isoformat(), today.isoformat()
    ) or []
    activity_rows = [r for r in (build_activity_row(a) for a in activities) if r]
    db.upsert("activities", activity_rows, conflict_col="activity_id")
    print(f"  {len(activity_rows)} actividades procesadas.")

    print("Listo.")


class _FakeClientForDryRun:
    """Cliente falso para probar el script sin credenciales reales de Garmin."""

    def get_stats(self, d):
        return {
            "totalSteps": 8000,
            "restingHeartRate": 55,
            "averageStressLevel": 30,
            "bodyBatteryLowestValue": 20,
            "bodyBatteryHighestValue": 90,
        }

    def get_sleep_data(self, d):
        return {
            "dailySleepDTO": {
                "sleepScores": {"overall": {"value": 82}},
                "sleepTimeSeconds": 27000,
            }
        }

    def get_hrv_data(self, d):
        return {"hrvSummary": {"lastNightAvg": 45}}

    def get_activities_by_date(self, start, end):
        return [
            {
                "activityId": 123456789,
                "startTimeGMT": f"{end} 08:00:00",
                "activityType": {"typeKey": "running"},
                "activityName": "Carrera de prueba",
                "distance": 10000.0,
                "duration": 3000.0,
                "averageHR": 150,
                "maxHR": 170,
                "averageSpeed": 3.33,
                "elevationGain": 80.0,
                "calories": 650,
            }
        ]


if __name__ == "__main__":
    main()
