
# import json
# import logging
# import os
# import threading
# import time
# from datetime import datetime, timezone

# import google.auth
# from google.auth.transport.requests import Request
# from google.oauth2 import service_account
# from flask import Flask, jsonify
# import requests

# # Configuración de logs limpia y visible para la consola de Render
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

# app = Flask(__name__)

# PROJECT_ID = "epicentro-66146"
# GEOAPIFY_KEY = "3fad5afd6cf6486192be6561c4e7462a"

# PROCESSED_EVENTS = set()
# MAX_CACHE_SIZE = 500


# @app.route("/")
# def health_check():
#     """Endpoint de salud para que UptimeRobot / Render mantengan el servicio activo."""
#     logging.info("💓 Health Check recibido (Ping de mantenimiento).")
#     return jsonify({
#         "status": "online",
#         "service": "Epicentro Seismic Monitor Worker",
#         "processed_events_count": len(PROCESSED_EVENTS),
#         "timestamp": datetime.now(timezone.utc).isoformat()
#     }), 200


# def get_fcm_access_token():
#     service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
#     if not service_account_env:
#         logging.error("❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT en Render")
#         raise ValueError("❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT")

#     service_account_info = json.loads(service_account_env)
#     credentials = service_account.Credentials.from_service_account_info(
#         service_account_info,
#         scopes=["https://www.googleapis.com/auth/firebase.messaging"],
#     )
#     credentials.refresh(Request())
#     return credentials.token


# def get_static_map_url(lat, lng):
#     return (
#         f"https://maps.geoapify.com/v1/staticmap"
#         f"?style=osm-bright&width=600&height=300"
#         f"&center=lonlat:{lng},{lat}&zoom=7"
#         f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
#         f"&apiKey={GEOAPIFY_KEY}"
#     )


# def check_usgs_and_notify():
#     timestamp_param = int(time.time())
#     usgs_url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson?t={timestamp_param}"

#     headers_req = {
#         "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
#         "Accept": "application/json",
#         "Cache-Control": "no-cache",
#     }

#     try:
#         response = requests.get(usgs_url, headers=headers_req, timeout=10)
#         if response.status_code != 200:
#             logging.warning(f"⚠️ USGS devolvió código de respuesta HTTP: {response.status_code}")
#             return

#         data = response.json()
#         features = data.get("features", [])
        
#         logging.info(f"🔍 Consulta USGS OK | Eventos en el feed de la última hora: {len(features)}")

#         if not features:
#             return

#         now_ms = datetime.now(timezone.utc).timestamp() * 1000
#         max_age_ms = 10 * 60 * 1000  # Ventana de 10 minutos
#         access_token = None
#         fcm_url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"

#         for sismo in features:
#             event_id = sismo.get("id")
#             if not event_id or event_id in PROCESSED_EVENTS:
#                 continue

#             properties = sismo.get("properties", {})
#             geometry = sismo.get("geometry", {})
#             coordinates = geometry.get("coordinates", [0, 0, 0])
#             timestamp_ms = properties.get("time", 0)

#             # Ignorar si el evento ocurrió hace más de 10 min
#             if (now_ms - timestamp_ms) > max_age_ms:
#                 continue

#             raw_mag = properties.get("mag")
#             mag = str(raw_mag) if raw_mag is not None else "N/A"
#             place = properties.get("place", "Ubicación no especificada")
#             lng = str(coordinates[0])
#             lat = str(coordinates[1])
#             depth = str(coordinates[2])
#             event_url = properties.get("url", "")

#             sismo_time = datetime.fromtimestamp(
#                 timestamp_ms / 1000, tz=timezone.utc
#             ).strftime("%H:%M UTC")

#             logging.info(f"🚨 ¡NUEVO SISMO DETECTADO! M{mag} - {place} ({lat}, {lng}) | Event ID: {event_id}")

#             if not access_token:
#                 access_token = get_fcm_access_token()

#             map_url = get_static_map_url(lat, lng)

#             payload = {
#                 "message": {
#                     "topic": "sismos_alertas",
#                     "data": {
#                         "eventId": str(event_id),
#                         "title": f"⚠️ ¡ALERTA DE SISMO M {mag}!",
#                         "message": f"Ubicación: {place}",
#                         "latitude": lat,
#                         "longitude": lng,
#                         "imageUrl": map_url,
#                         "time": sismo_time,
#                         "depth": depth,
#                         "eventUrl": event_url,
#                     },
#                     "android": {
#                         "priority": "HIGH",
#                         "direct_boot_ok": True,
#                         "ttl": "60s"
#                     },
#                 }
#             }

#             headers_fcm = {
#                 "Authorization": f"Bearer {access_token}",
#                 "Content-Type": "application/json",
#             }

#             res = requests.post(fcm_url, headers=headers_fcm, data=json.dumps(payload), timeout=10)
            
#             if res.status_code == 200:
#                 logging.info(f"✅ Alerta enviada con éxito a FCM para el evento {event_id}")
#             else:
#                 logging.error(f"❌ Error al enviar a FCM (Status {res.status_code}): {res.text}")

#             PROCESSED_EVENTS.add(event_id)
#             if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
#                 PROCESSED_EVENTS.pop()

#     except Exception as e:
#         logging.error(f"❌ Excepción durante el procesamiento de sismos: {e}", exc_info=True)


# def worker_loop():
#     """Bucle que consulta la USGS cada 15 segundos en un hilo secundario."""
#     logging.info("🚀 Iniciando Worker de Monitoreo Continuo (Intervalo: 15s)...")
#     while True:
#         try:
#             check_usgs_and_notify()
#         except Exception as e:
#             logging.error(f"❌ Error grave no controlado en el loop: {e}")
#         time.sleep(15)


# # Iniciar el worker en segundo plano
# threading.Thread(target=worker_loop, daemon=True).start()

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 10000))
#     app.run(host="0.0.0.0", port=port)

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from flask import Flask, jsonify
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = Flask(__name__)

PROJECT_ID = "epicentro-66146"
GEOAPIFY_KEY = "3fad5afd6cf6486192be6561c4e7462a"

PROCESSED_EVENTS = set()
MAX_CACHE_SIZE = 500

# Inicializador de zona horaria por coordenadas
tf = TimezoneFinder()


@app.route("/")
def health_check():
    return jsonify({
        "status": "online",
        "service": "Epicentro Seismic Monitor Worker",
        "processed_events_count": len(PROCESSED_EVENTS),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


def get_fcm_access_token():
    service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not service_account_env:
        raise ValueError("❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT")

    service_account_info = json.loads(service_account_env)
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    credentials.refresh(Request())
    return credentials.token


def get_static_map_url(lat, lng):
    return (
        f"https://maps.geoapify.com/v1/staticmap"
        f"?style=osm-bright&width=600&height=300"
        f"&center=lonlat:{lng},{lat}&zoom=7"
        f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
        f"&apiKey={GEOAPIFY_KEY}"
    )


def format_local_time(timestamp_ms, lat, lng):
    """Calcula la hora local según las coordenadas exactas del sismo."""
    utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    try:
        tz_name = tf.timezone_at(lat=lat, lng=lng)
        if tz_name:
            local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
            # Muestra ej: "18:28 (Hora local)"
            return local_dt.strftime("%H:%M HS (Local)")
    except Exception:
        pass
    
    return utc_dt.strftime("%H:%M UTC")


def check_usgs_and_notify():
    timestamp_param = int(time.time())
    usgs_url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson?t={timestamp_param}"

    headers_req = {
        "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    }

    try:
        response = requests.get(usgs_url, headers=headers_req, timeout=10)
        if response.status_code != 200:
            return

        data = response.json()
        features = data.get("features", [])
        if not features:
            return

        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        max_age_ms = 10 * 60 * 1000  # Ventana de 10 min
        access_token = None
        fcm_url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"

        for sismo in features:
            event_id = sismo.get("id")
            if not event_id or event_id in PROCESSED_EVENTS:
                continue

            properties = sismo.get("properties", {})
            geometry = sismo.get("geometry", {})
            coordinates = geometry.get("coordinates", [0, 0, 0])
            timestamp_ms = properties.get("time", 0)

            if (now_ms - timestamp_ms) > max_age_ms:
                continue

            # --- CORRECCIÓN 1: Redondeo de magnitud a 1 decimal ---
            raw_mag = properties.get("mag")
            if raw_mag is not None:
                mag = f"{float(raw_mag):.1f}"
            else:
                mag = "N/A"

            place = properties.get("place", "Ubicación no especificada")
            
            float_lng = float(coordinates[0])
            float_lat = float(coordinates[1])
            float_depth = float(coordinates[2])

            # --- CORRECCIÓN 2: Redondeo de profundidad a 1 decimal (ej. 11.8 km) ---
            depth_str = f"{float_depth:.1f} km"
            
            lng_str = str(float_lng)
            lat_str = str(float_lat)
            event_url = properties.get("url", "")

            # --- CORRECCIÓN 3: Hora basada en la ubicación exacta del sismo ---
            sismo_time = format_local_time(timestamp_ms, float_lat, float_lng)

            logging.info(f"🚨 ¡NUEVO SISMO! M{mag} - {place} | Hora: {sismo_time} | Prof: {depth_str}")

            if not access_token:
                access_token = get_fcm_access_token()

            map_url = get_static_map_url(lat_str, lng_str)

            payload = {
                "message": {
                    "topic": "sismos_alertas",
                    "data": {
                        "eventId": str(event_id),
                        "title": f"⚠️ ¡ALERTA DE SISMO M {mag}!",
                        "message": f"Ubicación: {place}",
                        "latitude": lat_str,
                        "longitude": lng_str,
                        "imageUrl": map_url,
                        "time": sismo_time,
                        "depth": depth_str,
                        "eventUrl": event_url,
                    },
                    "android": {
                        "priority": "HIGH",
                        "direct_boot_ok": True,
                        "ttl": "60s"
                    },
                }
            }

            headers_fcm = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            res = requests.post(fcm_url, headers=headers_fcm, data=json.dumps(payload), timeout=10)
            
            if res.status_code == 200:
                logging.info(f"✅ Alerta enviada a FCM para {event_id}")

            PROCESSED_EVENTS.add(event_id)
            if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
                PROCESSED_EVENTS.pop()

    except Exception as e:
        logging.error(f"❌ Error en rutina de sismos: {e}")


def worker_loop():
    logging.info("🚀 Worker activo consultando USGS cada 15s...")
    while True:
        try:
            check_usgs_and_notify()
        except Exception as e:
            logging.error(f"❌ Error en bucle: {e}")
        time.sleep(15)


threading.Thread(target=worker_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)