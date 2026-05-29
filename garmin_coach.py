#!/usr/bin/env python3
"""
garmin_coach.py
---------------
Descarga tus datos diarios de Garmin Connect y genera un JSON completo
listo para pegar en Claude como coach de entrenamiento.

Uso:
    python3 garmin_coach.py

La primera vez te pedirá usuario y contraseña de Garmin Connect.
Las siguientes veces los recuerda automáticamente (sesión guardada).
"""

import json
import os
import sys
import datetime
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# ── Credenciales Garmin ───────────────────────────────────────────────────────
GARMIN_EMAIL    = ""
GARMIN_PASSWORD = ""

# ── Email (Gmail) ─────────────────────────────────────────────────────────────
# Necesitas una "Contraseña de aplicación" de Google (no tu contraseña normal).
# Cómo obtenerla: myaccount.google.com/apppasswords
GMAIL_SENDER   = "marcosarranz96@gmail.com"
GMAIL_APP_PASS = ""  # Rellena con tu contraseña de aplicación de Google
GMAIL_TO       = "marcosarranz96@gmail.com"
# ─────────────────────────────────────────────────────────────────────────────

SESSION_FILE   = Path.home() / ".garmin_session"
OUTPUT_FILE    = Path.home() / "Desktop" / "garmin_hoy.json"
INFORMES_DIR   = Path.home() / "Desktop" / "garmin_informes"

def login():
    from garminconnect import Garmin
    import garth

    email    = GARMIN_EMAIL    or input("Email de Garmin Connect: ").strip()
    password = GARMIN_PASSWORD or __import__('getpass').getpass("Contraseña: ")

    client = Garmin(email, password)

    if SESSION_FILE.exists():
        try:
            client.login(str(SESSION_FILE))
            print("✓ Sesión restaurada")
            return client
        except Exception:
            print("Sesión expirada, iniciando sesión nueva...")

    try:
        client.login()
        client.garth.dump(str(SESSION_FILE))
        print("✓ Sesión iniciada y guardada")
    except Exception as e:
        print(f"Error al iniciar sesión: {e}")
        sys.exit(1)

    return client


def safe(fn, *args, **kwargs):
    """Ejecuta una llamada a la API y devuelve None si falla."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"  ⚠ {fn.__name__}: {e}")
        return None


def fetch_all(client, today, yesterday):
    today_str     = today.isoformat()
    yesterday_str = yesterday.isoformat()

    print(f"\n📡 Descargando datos de Garmin Connect para {today_str}...\n")

    data = {}

    # ── Perfil ────────────────────────────────────────────────────────────────
    print("👤 Perfil...")
    profile = safe(client.get_full_name)
    unit    = safe(client.get_unit_system)
    data["perfil"] = {"nombre": profile, "sistema_unidades": unit}

    # ── Estadísticas diarias ──────────────────────────────────────────────────
    print("📊 Estadísticas del día...")
    stats = safe(client.get_stats, today_str)
    data["estadisticas_dia"] = stats

    # ── Body Battery ──────────────────────────────────────────────────────────
    print("🔋 Body Battery...")
    bb = safe(client.get_body_battery, today_str, today_str)
    data["body_battery"] = bb

    # ── HRV ───────────────────────────────────────────────────────────────────
    print("💓 HRV...")
    hrv = safe(client.get_hrv_data, today_str)
    data["hrv"] = hrv

    # ── Sueño ─────────────────────────────────────────────────────────────────
    print("😴 Sueño...")
    sleep = safe(client.get_sleep_data, yesterday_str)  # sueño de la noche anterior
    data["sueno"] = sleep

    # ── Frecuencia cardíaca en reposo ─────────────────────────────────────────
    print("❤️  FC en reposo...")
    rhr = safe(client.get_rhr_day, today_str)
    data["fc_reposo"] = rhr

    # ── Estrés ────────────────────────────────────────────────────────────────
    print("😰 Estrés...")
    stress = safe(client.get_stress_data, today_str)
    data["estres"] = stress

    # ── SpO2 ──────────────────────────────────────────────────────────────────
    print("🫁 SpO2...")
    spo2 = safe(client.get_spo2_data, today_str)
    data["spo2"] = spo2

    # ── Respiración ───────────────────────────────────────────────────────────
    print("🌬️  Respiración...")
    resp = safe(client.get_respiration_data, today_str)
    data["respiracion"] = resp

    # ── Pasos ─────────────────────────────────────────────────────────────────
    print("🚶 Pasos...")
    steps = safe(client.get_steps_data, today_str)
    data["pasos"] = steps

    # ── Actividades recientes ─────────────────────────────────────────────────
    print("🏃 Actividades recientes...")
    activities = safe(client.get_activities, 0, 20)
    data["actividades_recientes"] = activities

    # ── Carga de entrenamiento ────────────────────────────────────────────────
    print("⚡ Carga de entrenamiento...")
    load = None
    for m in ['get_training_load', 'get_training_load_details', 'get_stats_and_body']:
        if hasattr(client, m):
            load = safe(getattr(client, m), today_str)
            break
    data["carga_entrenamiento"] = load

    # ── Estado de entrenamiento / Readiness ───────────────────────────────────
    print("🎯 Estado de entrenamiento...")
    status = None
    for m in ['get_training_status', 'get_training_readiness', 'get_training_load_stats']:
        if hasattr(client, m):
            status = safe(getattr(client, m), today_str)
            if status:
                break
    data["estado_entrenamiento"] = status

    # ── VO2max ────────────────────────────────────────────────────────────────
    print("🫀 VO2max...")
    vo2 = safe(client.get_max_metrics, today_str)
    data["vo2max"] = vo2

    # ── Hidratación ───────────────────────────────────────────────────────────
    print("💧 Hidratación...")
    hydration = safe(client.get_hydration_data, today_str)
    data["hidratacion"] = hydration

    # ── Calorías ─────────────────────────────────────────────────────────────
    print("🔥 Calorías...")
    calories = None
    for m in ['get_calories_burned_data', 'get_daily_calories', 'get_calories']:
        if hasattr(client, m):
            calories = safe(getattr(client, m), today_str)
            break
    data["calorias"] = calories

    # ── Peso ─────────────────────────────────────────────────────────────────
    print("⚖️  Peso...")
    weight = safe(client.get_weigh_ins, today_str, today_str)
    data["peso"] = weight

    return data


def build_summary(data, today):
    """Construye un resumen legible para pegar directamente en Claude."""
    lines = [
        f"=== DATOS GARMIN CONNECT — {today.strftime('%A %d %B %Y').upper()} ===",
        f"Atleta: {data.get('perfil', {}).get('nombre', 'Marcos Arranz')}",
        "",
    ]

    # Body Battery
    bb = data.get("body_battery")
    if bb:
        try:
            latest = bb[-1] if isinstance(bb, list) else bb
            val = latest.get("charged") or latest.get("bodyBatteryLevel") or "?"
            lines.append(f"🔋 Body Battery: {val}")
        except: pass

    # HRV
    hrv = data.get("hrv")
    if hrv:
        try:
            summary = hrv.get("hrvSummary", {})
            lines.append(f"💓 HRV nocturno: {summary.get('lastNightAvg', '?')} ms  |  Máximo 5min: {summary.get('lastNight5MinHigh', '?')} ms  |  Media semanal: {summary.get('weeklyAvg', '?')} ms")
            lines.append(f"   Zona óptima: {summary.get('baseline', {}).get('balancedLow', '?')}-{summary.get('baseline', {}).get('balancedUpper', '?')} ms  |  Estado: {summary.get('status', '?')}")
        except: pass

    # Sueño
    sleep = data.get("sueno")
    if sleep:
        try:
            sd = sleep.get("dailySleepDTO", {})
            total_min = (sd.get("sleepTimeSeconds", 0) or 0) // 60
            h, m = divmod(total_min, 60)
            score = sd.get("sleepScores", {}).get("overall", {}).get("value", "?")
            lines.append(f"😴 Sueño: {h}h {m}min  |  Puntuación: {score}")
            deep = (sd.get("deepSleepSeconds", 0) or 0) // 60
            rem  = (sd.get("remSleepSeconds", 0) or 0) // 60
            lines.append(f"   Profundo: {deep}min  |  REM: {rem}min")
        except: pass

    # FC reposo
    rhr = data.get("fc_reposo")
    if rhr:
        try:
            metrics = rhr.get("allMetrics", {}).get("metricsMap", {})
            rhr_list = metrics.get("WELLNESS_RESTING_HEART_RATE", [])
            val = int(rhr_list[0]["value"]) if rhr_list else "?"
            lines.append(f"❤️  FC reposo: {val} bpm")
        except: pass

    # Estrés
    stress = data.get("estres")
    if stress:
        try:
            avg = stress.get("avgStressLevel") or stress.get("averageStressLevel") or "?"
            lines.append(f"😰 Estrés medio: {avg}/100")
        except: pass

    # Estado entrenamiento
    status = data.get("estado_entrenamiento")
    if status:
        try:
            vo2 = status.get("mostRecentVO2Max", {}).get("generic", {})
            vo2val = vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue") or "?"
            vo2date = vo2.get("calendarDate", "")
            lines.append(f"🫀 VO2max: {vo2val} ml/kg/min (medido {vo2date})")
            # training status if present
            ts = status.get("trainingStatus") or status.get("latestTrainingStatus")
            if ts:
                lines.append(f"🎯 Estado entrenamiento: {ts}")
        except: pass

    # VO2max
    # VO2max ya incluido en estado_entrenamiento

    # Estadísticas
    stats = data.get("estadisticas_dia")
    if stats:
        try:
            floors = stats.get("floorsAscended", "?")
            bmr    = stats.get("bmrKilocalories", "?")
            lines.append(f"🏢 Pisos subidos: {floors}  |  Calorías basales (BMR): {bmr} kcal")
        except: pass

    # Carga entrenamiento
    load = data.get("carga_entrenamiento")
    if load:
        try:
            steps = load.get("totalSteps") or "?"
            kcal  = load.get("totalKilocalories") or "?"
            aktiv = load.get("activeKilocalories") or "?"
            dist  = round((load.get("totalDistanceMeters") or 0) / 1000, 1)
            lines.append(f"⚡ Pasos: {steps}  |  Calorías totales: {kcal} kcal  |  Activas: {aktiv} kcal  |  Distancia: {dist} km")
        except: pass

    # Actividades recientes
    acts = data.get("actividades_recientes")
    if acts:
        lines.append(f"\n🏃 ÚLTIMAS ACTIVIDADES ({len(acts)}):")
        for a in acts[:20]:
            try:
                name     = a.get("activityName", "Actividad")
                atype    = a.get("activityType", {}).get("typeKey", "?")
                dist_km  = (a.get("distance", 0) or 0) / 1000
                dur_min  = (a.get("duration", 0) or 0) / 60
                hr_avg   = a.get("averageHR", "?")
                elev     = a.get("elevationGain", 0) or 0
                date_str = (a.get("startTimeLocal") or "")[:10]
                lines.append(f"  · {date_str} {name} ({atype}) — {dist_km:.1f} km · {dur_min:.0f} min · FC {hr_avg} bpm · +{elev:.0f}m")
            except: pass

    lines += [
        "",
        "=== FIN DE DATOS ===",
        "",
        "Basándote en estos datos, actúa como mi coach personal de entrenamiento.",
        "Analiza mi estado de recuperación, predisposición para entrenar hoy,",
        "y dame recomendaciones concretas para la sesión de hoy."
    ]

    return "\n".join(lines)


def send_email(summary, today, json_file):
    if not GMAIL_APP_PASS:
        print("
⚠️  Email no configurado. Añade tu contraseña de aplicación de Gmail en el script.")
        print("   Guía: myaccount.google.com/apppasswords")
        return

    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_SENDER
        msg["To"]      = GMAIL_TO
        msg["Subject"] = f"🏃 Coach Garmin · {today.strftime('%d/%m/%Y')}"

        # Body
        body = f"""¡Buenos días Marcos! Aquí tienes tu informe de entrenamiento de hoy.

{summary}

---
Generado automáticamente por tu coach Garmin · {today.isoformat()}
"""
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Adjuntar JSON
        if json_file.exists():
            with open(json_file, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename=garmin_{today.isoformat()}.json")
                msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_SENDER, GMAIL_TO, msg.as_string())

        print(f"
📧 Email enviado a {GMAIL_TO}")
    except Exception as e:
        print(f"
⚠️  Error enviando email: {e}")



def main():
    today     = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    client = login()
    data   = fetch_all(client, today, yesterday)

    # Guardar JSON completo
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    # Generar resumen
    summary = build_summary(data, today)
    summary_file = OUTPUT_FILE.parent / "garmin_resumen.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)

    # Copiar al portapapeles
    try:
        import subprocess
        subprocess.run("pbcopy", input=summary.encode("utf-8"), check=True)
        print("\n✅ ¡Listo! Resumen copiado al portapapeles.")
        print("   Abre claude.ai y pega con Cmd+V para hablar con tu coach.")
    except Exception:
        print("\n✅ ¡Listo!")

    print(f"\n📄 JSON completo guardado en: {OUTPUT_FILE}")
    print(f"📝 Resumen guardado en:       {summary_file}")
    print("\n--- RESUMEN ---")
    print(summary)


if __name__ == "__main__":
    main()
