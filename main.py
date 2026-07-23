
# import json
# import logging
# import os
# import threading
# import time
# from datetime import datetime, timezone
# from zoneinfo import ZoneInfo
# from timezonefinder import TimezoneFinder

# import google.auth
# from google.auth.transport.requests import Request
# from google.oauth2 import service_account
# from flask import Flask, jsonify
# import requests
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry

# # Configuración detallada de logs para monitoreo en tiempo real (Render / Cloud Logs)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

# app = Flask(__name__)

# # Configuración del proyecto Firebase y Apis externas
# PROJECT_ID = "epicentro-66146"
# GEOAPIFY_KEY = "3fad5afd6cf6486192be6561c4e7462a"

# # Caché en memoria de IDs procesados para evitar duplicados
# PROCESSED_EVENTS = set()
# MAX_CACHE_SIZE = 2000  # Expandido para soportar mayor histórico sin duplicar

# # Inicializador de zona horaria por coordenadas GPS
# tf = TimezoneFinder()

# # Configuración de Sesión HTTP con Reintentos Rápidos (Keep-Alive)
# http_session = requests.Session()
# retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
# http_session.mount("https://", HTTPAdapter(max_retries=retries))


# @app.route("/")
# def health_check():
#     """Endpoint de verificación de estado y métricas del worker."""
#     return jsonify({
#         "status": "online",
#         "service": "Epicentro Realtime Seismic Worker",
#         "processed_events_count": len(PROCESSED_EVENTS),
#         "timestamp": datetime.now(timezone.utc).isoformat()
#     }), 200


# def get_fcm_access_token():
#     """
#     Genera un Bearer Token OAuth 2.0 válido para Firebase Cloud Messaging HTTP v1 API.
#     """
#     service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
#     if not service_account_env:
#         logging.error("❌ CRÍTICO: La variable FIREBASE_SERVICE_ACCOUNT no está configurada.")
#         raise ValueError("❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT")

#     service_account_info = json.loads(service_account_env)
#     credentials = service_account.Credentials.from_service_account_info(
#         service_account_info,
#         scopes=["https://www.googleapis.com/auth/firebase.messaging"],
#     )
#     credentials.refresh(Request())
#     return credentials.token


# def get_static_map_url(lat, lng):
#     """Construye la URL para obtener el mapa estático en Geoapify."""
#     return (
#         f"https://maps.geoapify.com/v1/staticmap"
#         f"?style=osm-bright&width=600&height=300"
#         f"&center=lonlat:{lng},{lat}&zoom=7"
#         f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
#         f"&apiKey={GEOAPIFY_KEY}"
#     )


# def format_local_time(timestamp_ms, lat, lng):
#     """Calcula y formatea la hora exacta del evento según la zona horaria de las coordenadas."""
#     utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
#     try:
#         tz_name = tf.timezone_at(lat=lat, lng=lng)
#         if tz_name:
#             local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
#             return local_dt.strftime("%H:%M HS (Local)")
#     except Exception as e:
#         logging.warning(f"⚠️ No se pudo determinar huso horario local para ({lat}, {lng}): {e}")
    
#     return utc_dt.strftime("%H:%M UTC")


# def check_usgs_and_notify():
#     """
#     RUTINA PRINCIPAL DE MONITOREO EN TIEMPO REAL:
#     Consulta el Feed de la USGS, evalúa sismos nuevos y los transmite por FCM.
#     """
#     timestamp_param = int(time.time())
#     usgs_url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson?t={timestamp_param}"

#     headers_req = {
#         "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
#         "Accept": "application/json",
#         "Cache-Control": "no-cache, no-store, must-revalidate",
#         "Pragma": "no-cache",
#     }

#     try:
#         response = http_session.get(usgs_url, headers=headers_req, timeout=8)
#         if response.status_code != 200:
#             logging.warning(f"⚠️ USGS API devolvió código HTTP {response.status_code}")
#             return

#         data = response.json()
#         features = data.get("features", [])
#         if not features:
#             return

#         now_ms = datetime.now(timezone.utc).timestamp() * 1000
#         # MEJORA CLAVE: 60 minutos de tolerancia para atrapar sismos publicados con retraso
#         max_age_ms = 60 * 60 * 1000 
#         access_token = None
#         fcm_url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"

#         for sismo in features:
#             event_id = sismo.get("id")
            
#             # 1. Descartar si el evento carece de ID o ya fue notificado a los usuarios
#             if not event_id or event_id in PROCESSED_EVENTS:
#                 continue

#             properties = sismo.get("properties", {})
#             geometry = sismo.get("geometry", {})
#             coordinates = geometry.get("coordinates", [0, 0, 0])
#             timestamp_ms = properties.get("time", 0)

#             # 2. Descartar solo si el origen del sismo fue hace más de 1 hora
#             delay_minutes = round((now_ms - timestamp_ms) / 60000, 1)
#             if (now_ms - timestamp_ms) > max_age_ms:
#                 logging.debug(f"ℹ️ Evento {event_id} descartado por antigüedad antigua ({delay_minutes} min).")
#                 continue

#             # Formateo de Magnitud
#             raw_mag = properties.get("mag")
#             if raw_mag is not None:
#                 mag = f"{float(raw_mag):.1f}"
#             else:
#                 mag = "N/A"

#             place = properties.get("place", "Ubicación no especificada")
            
#             float_lng = float(coordinates[0])
#             float_lat = float(coordinates[1])
#             float_depth = float(coordinates[2])

#             depth_str = f"{float_depth:.1f} km"
#             lng_str = str(float_lng)
#             lat_str = str(float_lat)
#             event_url = properties.get("url", "")

#             # Formateo de hora según ubicación exacta
#             sismo_time = format_local_time(timestamp_ms, float_lat, float_lng)

#             logging.info(
#                 f"🚨 ¡NUEVO SISMO DETECTADO! Evento: {event_id} | M{mag} - {place} "
#                 f"| Hora: {sismo_time} | Profundidad: {depth_str} | Retraso USGS: {delay_minutes} min"
#             )

#             # Autenticar FCM V1 solo si se encuentra un sismo válido a enviar
#             if not access_token:
#                 access_token = get_fcm_access_token()

#             map_url = get_static_map_url(lat_str, lng_str)

#             # Construcción del Payload de Notificación PUSH de alta prioridad
#             payload = {
#                 "message": {
#                     "topic": "sismos_alertas",
#                     "data": {
#                         "eventId": str(event_id),
#                         "title": f"⚠️ ¡ALERTA DE SISMO M {mag}!",
#                         "magnitude": str(mag),
#                         "message": f"Ubicación: {place}",
#                         "latitude": lat_str,
#                         "longitude": lng_str,
#                         "imageUrl": map_url,
#                         "time": sismo_time,
#                         "depth": depth_str,
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

#             # Enviar notificación Push vía Firebase Cloud Messaging
#             res = http_session.post(fcm_url, headers=headers_fcm, data=json.dumps(payload), timeout=8)
            
#             if res.status_code == 200:
#                 logging.info(f"✅ Notificación enviada con éxito a FCM para el sismo {event_id}")
#             else:
#                 logging.error(f"❌ Error al enviar notificación a FCM ({res.status_code}): {res.text}")

#             # Registrar en memoria para evitar re-notificar el mismo evento
#             PROCESSED_EVENTS.add(event_id)
#             if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
#                 # Mantiene el caché ordenado liberando espacio antiguo si supera el máximo
#                 PROCESSED_EVENTS.pop()

#     except Exception as e:
#         logging.error(f"❌ Error inesperado en rutina de sismos: {e}", exc_info=True)


# def worker_loop():
#     """Hilo de ejecución secundaria que monitorea la USGS de forma continua."""
#     logging.info("🚀 Worker de Monitoreo Sísmico activo. Consultando USGS cada 15s...")
#     while True:
#         try:
#             check_usgs_and_notify()
#         except Exception as e:
#             logging.error(f"❌ Error en bucle del worker: {e}")
#         time.sleep(15)


# # Iniciar el Worker en un hilo Daemon paralelo a Flask
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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuración detallada de logs para monitoreo en tiempo real (Render / Cloud Logs)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = Flask(__name__)

# Configuración del proyecto Firebase y APIs externas
PROJECT_ID = "epicentro-66146"
GEOAPIFY_KEY = "3fad5afd6cf6486192be6561c4e7462a"

# Caché en memoria de IDs procesados para evitar duplicados
PROCESSED_EVENTS = set()
MAX_CACHE_SIZE = 2000

# Caché global para el token OAuth2 de FCM
fcm_credentials = None

# Inicializador de zona horaria por coordenadas GPS
tf = TimezoneFinder()

# Configuración de Sesión HTTP con Reintentos Rápidos (Keep-Alive)
http_session = requests.Session()
retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
http_session.mount("https://", HTTPAdapter(max_retries=retries))


@app.route("/")
def health_check():
    """Endpoint de verificación de estado y métricas del worker."""
    return jsonify({
        "status": "online",
        "service": "Epicentro Realtime Seismic Worker",
        "processed_events_count": len(PROCESSED_EVENTS),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


def get_fcm_access_token():
    """
    Obtiene o refresca de forma eficiente el Bearer Token OAuth 2.0 para FCM v1.
    """
    global fcm_credentials

    if not fcm_credentials:
        service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if not service_account_env:
            logging.error("❌ CRÍTICO: La variable FIREBASE_SERVICE_ACCOUNT no está configurada.")
            raise ValueError("❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT")

        service_account_info = json.loads(service_account_env)
        fcm_credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )

    if not fcm_credentials.valid:
        fcm_credentials.refresh(Request())

    return fcm_credentials.token


def get_static_map_url(lat, lng):
    """Construye la URL para obtener el mapa estático en Geoapify."""
    return (
        f"https://maps.geoapify.com/v1/staticmap"
        f"?style=osm-bright&width=600&height=300"
        f"&center=lonlat:{lng},{lat}&zoom=7"
        f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
        f"&apiKey={GEOAPIFY_KEY}"
    )


def format_local_time(timestamp_ms, lat, lng):
    """Calcula y formatea la hora exacta del evento según la zona horaria de las coordenadas."""
    utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    try:
        tz_name = tf.timezone_at(lat=lat, lng=lng)
        if tz_name:
            local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
            return local_dt.strftime("%H:%M HS (Local)")
    except Exception as e:
        logging.warning(f"⚠️ No se pudo determinar huso horario local para ({lat}, {lng}): {e}")
    
    return utc_dt.strftime("%H:%M UTC")


def fetch_usgs_events():
    """Consulta el feed GeoJSON de la USGS midiendo tiempos de respuesta."""
    start_time = time.time()
    timestamp_param = int(time.time())
    usgs_url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson?t={timestamp_param}"
    headers = {
        "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
        "Accept": "application/json",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }
    
    events = []
    try:
        response = http_session.get(usgs_url, headers=headers, timeout=8)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        if response.status_code == 200:
            data = response.json()
            features = data.get("features", [])
            
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [0, 0, 0])
                
                events.append({
                    "id": feat.get("id"),
                    "source": "USGS",
                    "magnitude": props.get("mag"),
                    "place": props.get("place", "Ubicación no especificada"),
                    "lat": float(coords[1]),
                    "lng": float(coords[0]),
                    "depth": float(coords[2]),
                    "timestamp_ms": props.get("time", 0),
                    "url": props.get("url", "")
                })

            logging.debug(f"🔍 [USGS] Consulta finalizada en {elapsed_ms} ms. Eventos recibidos: {len(events)}")
        else:
            logging.warning(f"⚠️ [USGS] API devolvió código HTTP {response.status_code} ({elapsed_ms} ms)")
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ [USGS] Error consultando API ({elapsed_ms} ms): {e}")
        
    return events


def fetch_emsc_events():
    """
    Consulta la API de EMSC (Centro Sismológico Euro-Mediterráneo) midiendo tiempos de respuesta.
    Cubre sismos globales y agencias locales como FUNVISIS (Venezuela).
    """
    start_time = time.time()
    emsc_url = "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=30"
    headers = {
        "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
        "Accept": "application/json",
    }
    
    events = []
    try:
        response = http_session.get(emsc_url, headers=headers, timeout=8)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        if response.status_code == 200:
            data = response.json()
            features = data.get("features", [])
            
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [0, 0, 0])
                
                time_str = props.get("time")
                timestamp_ms = 0
                if time_str:
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    timestamp_ms = int(dt.timestamp() * 1000)

                events.append({
                    "id": f"emsc_{feat.get('id')}",
                    "source": "EMSC",
                    "magnitude": props.get("mag"),
                    "place": props.get("flynn_region", "Ubicación no especificada"),
                    "lat": float(coords[1]),
                    "lng": float(coords[0]),
                    "depth": float(coords[2]),
                    "timestamp_ms": timestamp_ms,
                    "url": f"https://www.emsc-csem.org/Earthquake/earthquake.php?id={feat.get('id')}"
                })

            logging.debug(f"🔍 [EMSC] Consulta finalizada en {elapsed_ms} ms. Eventos recibidos: {len(events)}")
        else:
            logging.warning(f"⚠️ [EMSC] API devolvió código HTTP {response.status_code} ({elapsed_ms} ms)")
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ [EMSC] Error consultando API ({elapsed_ms} ms): {e}")

    return events


def process_and_notify_event(sismo, access_token):
    """Procesa un sismo individual, arma el payload y lo envía a Firebase Cloud Messaging."""
    event_id = sismo["id"]
    timestamp_ms = sismo["timestamp_ms"]
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    max_age_ms = 60 * 60 * 1000  # Tolerancia de 60 minutos
    delay_minutes = round((now_ms - timestamp_ms) / 60000, 1)

    if (now_ms - timestamp_ms) > max_age_ms:
        logging.debug(f"ℹ️ Evento {event_id} [{sismo['source']}] descartado por antigüedad antigua ({delay_minutes} min).")
        return

    raw_mag = sismo["magnitude"]
    mag = f"{float(raw_mag):.1f}" if raw_mag is not None else "N/A"

    place = sismo["place"]
    float_lat = sismo["lat"]
    float_lng = sismo["lng"]
    float_depth = sismo["depth"]

    depth_str = f"{float_depth:.1f} km"
    lng_str = str(float_lng)
    lat_str = str(float_lat)
    event_url = sismo["url"]
    source = sismo["source"]

    sismo_time = format_local_time(timestamp_ms, float_lat, float_lng)

    # Log detallado manteniendo la estructura exacta original + la fuente explicitada
    logging.info(
        f"🚨 ¡NUEVO SISMO DETECTADO! Evento: {event_id} [{source}] | M{mag} - {place} "
        f"| Hora: {sismo_time} | Profundidad: {depth_str} | Retraso {source}: {delay_minutes} min"
    )

    map_url = get_static_map_url(lat_str, lng_str)
    fcm_url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"

    payload = {
        "message": {
            "topic": "sismos_alertas",
            "data": {
                "eventId": str(event_id),
                "title": f"⚠️ ¡ALERTA DE SISMO M {mag}!",
                "magnitude": str(mag),
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

    fcm_start_time = time.time()
    res = http_session.post(fcm_url, headers=headers_fcm, data=json.dumps(payload), timeout=8)
    fcm_elapsed_ms = round((time.time() - fcm_start_time) * 1000, 2)

    if res.status_code == 200:
        logging.info(f"✅ Notificación enviada con éxito a FCM para el sismo {event_id} ({fcm_elapsed_ms} ms)")
    else:
        logging.error(f"❌ Error al enviar notificación a FCM ({res.status_code}) [{fcm_elapsed_ms} ms]: {res.text}")

    PROCESSED_EVENTS.add(event_id)
    if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
        PROCESSED_EVENTS.pop()


def check_earthquakes_and_notify():
    """
    RUTINA PRINCIPAL DE MONITOREO EN TIEMPO REAL:
    Consulta USGS y EMSC de forma combinada, procesa y transmite eventos únicos midiendo la latencia total.
    """
    cycle_start = time.time()
    try:
        usgs_events = fetch_usgs_events()
        emsc_events = fetch_emsc_events()
        
        all_events = usgs_events + emsc_events
        if not all_events:
            return

        access_token = None

        for sismo in all_events:
            event_id = sismo.get("id")

            if not event_id or event_id in PROCESSED_EVENTS:
                continue

            if not access_token:
                access_token = get_fcm_access_token()

            process_and_notify_event(sismo, access_token)

        total_elapsed = round((time.time() - cycle_start) * 1000, 2)
        logging.debug(f"⏱️ Ciclo de monitoreo completado en {total_elapsed} ms. Eventos escaneados: {len(all_events)}")

    except Exception as e:
        total_elapsed = round((time.time() - cycle_start) * 1000, 2)
        logging.error(f"❌ Error inesperado en rutina de sismos ({total_elapsed} ms): {e}", exc_info=True)


def worker_loop():
    """Hilo de ejecución secundaria que monitorea múltiples redes de forma continua."""
    logging.info("🚀 Worker de Monitoreo Sísmico activo. Consultando USGS + EMSC cada 15s...")
    while True:
        try:
            check_earthquakes_and_notify()
        except Exception as e:
            logging.error(f"❌ Error en bucle del worker: {e}")
        time.sleep(15)


# Iniciar el Worker en un hilo Daemon paralelo a Flask
threading.Thread(target=worker_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)