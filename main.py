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

# # ==========================================
# # CONFIGURACIÓN DE LOGS Y SERVIDOR WEB
# # ==========================================
# # Formato detallado de logs con timestamp, nivel de severidad y mensaje
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

# app = Flask(__name__)

# # ==========================================
# # CONSTANTES Y CONFIGURACIONES GLOBALES
# # ==========================================
# PROJECT_ID = "epicentro-66146"
# GEOAPIFY_KEY = "3fad5afd6cf6486192be6561c4e7462a"

# # Cache en memoria para evitar notificar eventos duplicados
# PROCESSED_EVENTS = set()
# MAX_CACHE_SIZE = 3000

# # Variables globales para cliente FCM y zona horaria
# fcm_credentials = None
# tf = TimezoneFinder()

# # Configuración del motor de reintentos HTTP para resiliencia ante caídas breves de red
# retries = Retry(
#     total=3,
#     backoff_factor=0.3,
#     status_forcelist=[500, 502, 503, 504],
#     raise_on_status=False,
# )
# adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)


# def create_http_session():
#     """Crea y configura una sesión HTTP reutilizable con estrategia de reintentos."""
#     session = requests.Session()
#     session.mount("https://", adapter)
#     session.mount("http://", adapter)
#     return session


# http_session = create_http_session()


# # ==========================================
# # RUTAS FLASK (HEALTH CHECK)
# # ==========================================
# @app.route("/")
# def health_check():
#     """Endpoint de estado para verificar que la app sigue viva en PaaS (Render, Heroku, etc)."""
#     return jsonify({
#         "status": "online",
#         "service": "Epicentro Realtime Seismic Worker (Global M2.5+)",
#         "processed_events_count": len(PROCESSED_EVENTS),
#         "timestamp": datetime.now(timezone.utc).isoformat()
#     }), 200


# # ==========================================
# # FUNCIONES AUXILIARES Y DE AUTENTICACIÓN
# # ==========================================
# def get_fcm_access_token():
#     """Obtiene y refresca el Token de Acceso OAuth2 para Firebase Cloud Messaging v1."""
#     global fcm_credentials

#     if not fcm_credentials:
#         service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
#         if not service_account_env:
#             logging.error("❌ CRÍTICO: La variable FIREBASE_SERVICE_ACCOUNT no está configurada.")
#             raise ValueError("❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT")

#         service_account_info = json.loads(service_account_env)
#         fcm_credentials = service_account.Credentials.from_service_account_info(
#             service_account_info,
#             scopes=["https://www.googleapis.com/auth/firebase.messaging"],
#         )

#     if not fcm_credentials.valid:
#         logging.info("🔑 Refrescando OAuth2 Access Token para Firebase FCM...")
#         fcm_credentials.refresh(Request())

#     return fcm_credentials.token


# def get_static_map_url(lat, lng):
#     """Genera la URL del mapa estático usando la API de Geoapify."""
#     return (
#         f"https://maps.geoapify.com/v1/staticmap"
#         f"?style=osm-bright&width=600&height=300"
#         f"&center=lonlat:{lng},{lat}&zoom=7"
#         f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
#         f"&apiKey={GEOAPIFY_KEY}"
#     )


# def format_local_time(timestamp_ms, lat, lng):
#     """Convierte el timestamp UTC a la hora local exacta según las coordenadas (lat, lng)."""
#     utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
#     try:
#         tz_name = tf.timezone_at(lat=lat, lng=lng)
#         if tz_name:
#             local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
#             return local_dt.strftime("%H:%M HS (Local)")
#     except Exception as e:
#         logging.warning(f"⚠️ No se pudo determinar huso horario para ({lat}, {lng}): {e}")

#     return utc_dt.strftime("%H:%M UTC")


# # ==========================================
# # FETCHERS DE FUENTES DE DATOS SISMO
# # ==========================================
# def fetch_usgs_events():
#     """Consulta sismos de la última hora desde el feed oficial de USGS."""
#     start_time = time.time()
#     timestamp_param = int(time.time())
#     usgs_url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson?t={timestamp_param}"
#     headers = {
#         "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
#         "Accept": "application/json",
#         "Cache-Control": "no-cache, no-store, must-revalidate",
#         "Pragma": "no-cache",
#     }

#     events = []
#     try:
#         response = http_session.get(usgs_url, headers=headers, timeout=8)
#         elapsed_ms = round((time.time() - start_time) * 1000, 2)

#         if response.status_code == 200:
#             data = response.json()
#             features = data.get("features", [])

#             for feat in features:
#                 props = feat.get("properties", {})
#                 geom = feat.get("geometry", {})
#                 coords = geom.get("coordinates", [0, 0, 0])

#                 mag = props.get("mag")
#                 # Filtro directo: Magnitud mayor o igual a 2.5
#                 if mag is None or float(mag) < 2.5:
#                     continue

#                 events.append({
#                     "id": f"usgs_{feat.get('id')}",
#                     "source": "USGS",
#                     "magnitude": float(mag),
#                     "place": props.get("place", "Ubicación no especificada"),
#                     "lat": float(coords[1]),
#                     "lng": float(coords[0]),
#                     "depth": float(coords[2]),
#                     "timestamp_ms": props.get("time", 0),
#                     "url": props.get("url", "")
#                 })

#             logging.info(f"🔍 [USGS] Petición exitosa en {elapsed_ms} ms. Eventos válidos M2.5+: {len(events)}")
#         else:
#             logging.warning(f"⚠️ [USGS] Código de respuesta inesperado HTTP {response.status_code} ({elapsed_ms} ms)")
#     except Exception as e:
#         elapsed_ms = round((time.time() - start_time) * 1000, 2)
#         logging.error(f"❌ [USGS] Error consultando API ({elapsed_ms} ms): {e}")

#     return events


# def fetch_emsc_events():
#     """Consulta sismos en tiempo real desde EMSC (Centro Sismológico Euro-Mediterráneo)."""
#     start_time = time.time()
#     emsc_url = "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&minmag=2.5&limit=100"
#     headers = {
#         "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
#         "Accept": "application/json",
#     }

#     events = []
#     try:
#         response = http_session.get(emsc_url, headers=headers, timeout=8)
#         elapsed_ms = round((time.time() - start_time) * 1000, 2)

#         if response.status_code == 200:
#             data = response.json()
#             features = data.get("features", [])

#             for feat in features:
#                 props = feat.get("properties", {})
#                 geom = feat.get("geometry", {})
#                 coords = geom.get("coordinates", [0, 0, 0])

#                 mag = props.get("mag")
#                 if mag is None or float(mag) < 2.5:
#                     continue

#                 time_str = props.get("time")
#                 timestamp_ms = 0
#                 if time_str:
#                     dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
#                     timestamp_ms = int(dt.timestamp() * 1000)

#                 raw_unid = feat.get("id") or props.get("unid")
#                 event_url = props.get("url") or f"https://www.seismicportal.eu/eventdetails.html?unid={raw_unid}"

#                 events.append({
#                     "id": f"emsc_{raw_unid}",
#                     "source": "EMSC",
#                     "magnitude": float(mag),
#                     "place": props.get("flynn_region", "Ubicación no especificada"),
#                     "lat": float(coords[1]),
#                     "lng": float(coords[0]),
#                     "depth": float(coords[2]),
#                     "timestamp_ms": timestamp_ms,
#                     "url": event_url
#                 })

#             logging.info(f"🔍 [EMSC] Petición exitosa en {elapsed_ms} ms. Eventos válidos M2.5+: {len(events)}")
#         else:
#             logging.warning(f"⚠️ [EMSC] Código de respuesta inesperado HTTP {response.status_code} ({elapsed_ms} ms)")
#     except Exception as e:
#         elapsed_ms = round((time.time() - start_time) * 1000, 2)
#         logging.error(f"❌ [EMSC] Error consultando API ({elapsed_ms} ms): {e}")

#     return events


# def fetch_funvisis_events():
#     """Consulta y parsea los sismos de FUNVISIS desde su GeoJSON maravilla.json."""
#     start_time = time.time()
#     funvisis_url = "http://www.funvisis.gob.ve/maravilla.json"
#     headers = {
#         "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
#         "Accept": "application/json",
#     }

#     events = []
#     try:
#         response = http_session.get(funvisis_url, headers=headers, timeout=8)
#         elapsed_ms = round((time.time() - start_time) * 1000, 2)

#         if response.status_code == 200:
#             data = response.json()

#             # En caso de que venga como un string JSON
#             if isinstance(data, str):
#                 data = json.loads(data)

#             features = data.get("features", [])

#             for feat in features:
#                 try:
#                     props = feat.get("properties", {})
#                     geom = feat.get("geometry", {})
#                     coords = geom.get("coordinates", [0, 0])

#                     # 1. Magnitud (viene en el campo "phone")
#                     mag_raw = props.get("phone", "0")
#                     mag = float(mag_raw)

#                     # Filtro de Magnitud M2.5+
#                     if mag < 1.0:
#                         continue

#                     # 2. Coordenadas [lng, lat]
#                     lng = float(coords[0])
#                     lat = float(coords[1])

#                     # 3. Profundidad (viene en "phoneFormatted", e.g. "17.0 km")
#                     depth_raw = props.get("phoneFormatted", "0").replace("km", "").strip()
#                     depth = float(depth_raw)

#                     # 4. Ubicación
#                     place = props.get("address", "Venezuela").strip()

#                     # 5. Timestamp (Fecha en "postalCode" e.g. "02-08-2026", Hora en "city" e.g. "17:46")
#                     date_str = props.get("postalCode", "")
#                     time_str = props.get("city", "")

#                     timestamp_ms = int(time.time() * 1000) # Fallback por defecto
#                     if date_str and time_str:
#                         # FUNVISIS publica en hora local de Venezuela (UTC-4)
#                         dt_str = f"{date_str} {time_str} -0400"
#                         dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M %z")
#                         timestamp_ms = int(dt.timestamp() * 1000)

#                     # ID único combinando fecha, hora y coordenadas para evitar colisiones
#                     raw_id = f"{date_str}_{time_str}_{lat}_{lng}".replace(" ", "_")

#                     events.append({
#                         "id": f"funvisis_{raw_id}",
#                         "source": "FUNVISIS",
#                         "magnitude": mag,
#                         "place": place,
#                         "lat": lat,
#                         "lng": lng,
#                         "depth": depth,
#                         "timestamp_ms": timestamp_ms,
#                         "url": "http://www.funvisis.gob.ve/"
#                     })

#                 except (ValueError, TypeError) as parse_err:
#                     logging.warning(f"⚠️ [FUNVISIS] Error parseando elemento individual: {parse_err}")
#                     continue

#             logging.info(f"🔍 [FUNVISIS] Petición exitosa en {elapsed_ms} ms. Eventos válidos M2.5+: {len(events)}")
#         else:
#             logging.warning(f"⚠️ [FUNVISIS] Código HTTP {response.status_code} ({elapsed_ms} ms)")
#     except Exception as e:
#         elapsed_ms = round((time.time() - start_time) * 1000, 2)
#         logging.error(f"❌ [FUNVISIS] Error consultando API ({elapsed_ms} ms): {e}")

#     return events

# # ==========================================
# # PROCESAMIENTO Y ENVÍO DE NOTIFICACIONES
# # ==========================================
# def process_and_notify_event(sismo, access_token):
#     """Procesa un sismo individual, verifica la antigüedad y envía la notificación vía FCM."""
#     event_id = sismo["id"]
#     timestamp_ms = sismo["timestamp_ms"]
#     now_ms = datetime.now(timezone.utc).timestamp() * 1000
#     max_age_ms = 60 * 60 * 1000  # 60 minutos máximo de tolerancia

#     delay_minutes = round((now_ms - timestamp_ms) / 60000, 1)

#     # Si el evento ocurrió hace más de 1 hora, se descarta para no alertar de cosas viejas
#     if (now_ms - timestamp_ms) > max_age_ms:
#         logging.info(f"⌛ Evento descarta por antigüedad ({delay_minutes} min de retraso): {event_id}")
#         return

#     mag_val = sismo["magnitude"]
#     mag = f"{mag_val:.1f}"

#     place = sismo["place"]
#     float_lat = sismo["lat"]
#     float_lng = sismo["lng"]
#     float_depth = sismo["depth"]

#     depth_str = f"{float_depth:.1f} km"
#     lng_str = str(float_lng)
#     lat_str = str(float_lat)
#     event_url = sismo["url"]
#     source = sismo["source"]

#     sismo_time = format_local_time(timestamp_ms, float_lat, float_lng)

#     logging.info(
#         f"🚨 ¡NUEVO SISMO M{mag}! ID: {event_id} [{source}] | {place} "
#         f"| Hora: {sismo_time} | Profundidad: {depth_str}"
#     )

#     map_url = get_static_map_url(lat_str, lng_str)
#     fcm_url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"

#     # Estructura del Payload exacto consumido por la app Android
#     payload = {
#         "message": {
#             "topic": "sismos_alertas",
#             "data": {
#                 "eventId": str(event_id),
#                 "source": str(source),
#                 "title": f"¡ALERTA DE SISMO M {mag}! ({source})",
#                 "magnitude": str(mag),
#                 "message": f"Ubicación: {place}",
#                 "latitude": lat_str,
#                 "longitude": lng_str,
#                 "imageUrl": map_url,
#                 "time": sismo_time,
#                 "depth": depth_str,
#                 "eventUrl": event_url,
#             },
#             "android": {
#                 "priority": "HIGH",
#                 "direct_boot_ok": True,
#                 "ttl": "60s"
#             },
#         }
#     }

#     headers_fcm = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json",
#     }

#     fcm_start_time = time.time()
#     res = http_session.post(fcm_url, headers=headers_fcm, data=json.dumps(payload), timeout=8)
#     fcm_elapsed_ms = round((time.time() - fcm_start_time) * 1000, 2)

#     if res.status_code == 200:
#         logging.info(f"✅ FCM Notificado con éxito: {event_id} ({fcm_elapsed_ms} ms)")
#         PROCESSED_EVENTS.add(event_id)
#     else:
#         logging.error(f"❌ Error enviando FCM ({res.status_code}) [{fcm_elapsed_ms} ms]: {res.text}")

#     # Control del tamaño del Cache en memoria RAM
#     if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
#         popped = PROCESSED_EVENTS.pop()
#         logging.debug(f"🧹 Cache lleno. Eliminado evento antiguo: {popped}")


# # ==========================================
# # RUTINA DE MONITOREO PRINCIPAL
# # ==========================================
# def check_earthquakes_and_notify():
#     """Rutina principal que recolecta, unifica y gestiona los eventos sísmicos de todas las fuentes."""
#     global http_session
#     cycle_start = time.time()
#     try:
#         usgs_events = fetch_usgs_events()
#         emsc_events = fetch_emsc_events()
#         funvisis_events = fetch_funvisis_events()

#         all_events = usgs_events + emsc_events + funvisis_events
#         if not all_events:
#             return

#         access_token = None
#         new_events_count = 0

#         for sismo in all_events:
#             event_id = sismo.get("id")

#             # Omitir si el evento no tiene ID o ya fue procesado previamente
#             if not event_id or event_id in PROCESSED_EVENTS:
#                 continue

#             # Obtención perezosa (lazy loading) del Access Token de Firebase
#             if not access_token:
#                 access_token = get_fcm_access_token()

#             process_and_notify_event(sismo, access_token)
#             new_events_count += 1

#         total_elapsed = round((time.time() - cycle_start) * 1000, 2)
#         logging.info(f"⏱️ Monitoreo completado en {total_elapsed} ms. Eventos procesados en este ciclo: {new_events_count}")

#     except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
#         logging.warning("⚠️ Conexión de red reseteada. Recreando sesión HTTP...", exc_info=False)
#         http_session = create_http_session()
#     except Exception as e:
#         logging.error(f"❌ Error no controlado en rutina de monitoreo: {e}", exc_info=True)


# def worker_loop():
#     """Hilo secundario que ejecuta el chequeo infinito cada 15 segundos."""
#     logging.info("🚀 Worker Global M2.5+ iniciado. Frecuencia de escaneo: 15 segundos.")
#     while True:
#         try:
#             check_earthquakes_and_notify()
#         except Exception as e:
#             logging.error(f"❌ Error en el bucle del worker: {e}", exc_info=True)
#         time.sleep(15)


# # ==========================================
# # INICIALIZACIÓN
# # ==========================================
# # Arrancar el hilo de segundo plano para el monitoreo sísmico
# threading.Thread(target=worker_loop, daemon=True).start()

# if __name__ == "__main__":
#     # Arrancar la app de Flask para escuchar peticiones Web/Healthchecks
#     port = int(os.environ.get("PORT", 10000))
#     logging.info(f"🌍 Servidor Flask iniciando en puerto {port}")
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
from flask import Flask, jsonify, request
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 📥 Módulo de detección sísmica comunitaria por acelerómetro
from sensor_detector import SeismicSensorDetector

# ==========================================
# CONFIGURACIÓN DE LOGS Y SERVIDOR WEB
# ==========================================
# Formato detallado de logs con timestamp, nivel de severidad y mensaje
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = Flask(__name__)

# ==========================================
# CONSTANTES Y CONFIGURACIONES GLOBALES
# ==========================================
PROJECT_ID = "epicentro-66146"
GEOAPIFY_KEY = "3fad5afd6cf6486192be6561c4e7462a"

# Cache en memoria para evitar notificar eventos duplicados
PROCESSED_EVENTS = set()
MAX_CACHE_SIZE = 3000

# Variables globales para cliente FCM y zona horaria
fcm_credentials = None
tf = TimezoneFinder()

# ⚡ Instancia global del Detector Sísmico Comunitario
community_detector = SeismicSensorDetector(
    threshold_g=2.5,
    time_window_seconds=10,
    min_reports_for_alert=3,
    cluster_radius_km=20.0
)

# Configuración del motor de reintentos HTTP para resiliencia ante caídas
# breves de red
retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504],
    raise_on_status=False,
)
adapter = HTTPAdapter(
    max_retries=retries,
    pool_connections=10,
    pool_maxsize=10)


def create_http_session():
    """Crea y configura una sesión HTTP reutilizable con estrategia de reintentos."""
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


http_session = create_http_session()


# ==========================================
# RUTAS FLASK (HEALTH CHECK Y SENSORES)
# ==========================================
@app.route("/")
def health_check():
    """Endpoint de estado para verificar que la app sigue viva en PaaS (Render, Heroku, etc)."""
    return jsonify({
        "status": "online",
        "service": "Epicentro Realtime Seismic Worker & Community Sensor System",
        "processed_events_count": len(PROCESSED_EVENTS),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@app.route("/api/v1/sensor/report", methods=["POST"])
def receive_sensor_report():
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"error": "Payload JSON requerido"}), 400

        cluster_detected = community_detector.process_incoming_report(payload)

        if cluster_detected:
            if cluster_detected.cluster_id not in PROCESSED_EVENTS:
                PROCESSED_EVENTS.add(cluster_detected.cluster_id)

                resolved_place = getattr(cluster_detected, 'place', None)
                if not resolved_place:
                    resolved_place = f"Cerca de {
                        round(
                            cluster_detected.center_lat,
                            2)}, {
                        round(
                            cluster_detected.center_lng,
                            2)}"

                estimated_magnitude = round(
                    cluster_detected.avg_intensity / 2.5, 1)

                sismo_comunitario = {
                    "id": str(cluster_detected.cluster_id),
                    "title": f"¡ALERTA DE SISMO M {estimated_magnitude}! (COMUNITARIO)",
                    "place": resolved_place,
                    "magnitude": estimated_magnitude,
                    "timestamp": cluster_detected.timestamp_ms,
                    "timestamp_ms": cluster_detected.timestamp_ms,
                    "depth": 0.0,
                    "latitude": cluster_detected.center_lat,
                    "longitude": cluster_detected.center_lng,
                    "radiusKm": 100.0,
                    "source": "COMUNITARIO",
                    "url": "https://epicentro.app"
                }

                # 🟢 FUNCIÓN AUXILIAR PARA PROCESAR Y NOTIFICAR
                def send_alert_task(event_data):
                    try:
                        token = get_fcm_access_token()
                        # Llama a tu función de envío FCM
                        process_and_notify_event(event_data, token)
                        logging.info(
                            f"🚀 Notificación FCM enviada con éxito para {
                                event_data['id']}")
                    except Exception as err:
                        logging.error(
                            f"❌ Error al enviar notificación FCM en hilo: {err}",
                            exc_info=True)

                # Ejecutar el envío en segundo plano
                threading.Thread(
                    target=send_alert_task,
                    args=(sismo_comunitario,),
                    daemon=True
                ).start()

                return jsonify({
                    "status": "alert_triggered",
                    "cluster_id": cluster_detected.cluster_id,
                    "place": resolved_place
                }), 200

        return jsonify({"status": "received"}), 200

    except Exception as e:
        logging.error(
            f"❌ Error procesando /api/v1/sensor/report: {e}",
            exc_info=True)
        return jsonify({"error": "Error interno al procesar lectura"}), 500
# ==========================================
# FUNCIONES AUXILIARES Y DE AUTENTICACIÓN
# ==========================================


def get_fcm_access_token():
    """Obtiene y refresca el Token de Acceso OAuth2 para Firebase Cloud Messaging v1."""
    global fcm_credentials

    if not fcm_credentials:
        service_account_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if not service_account_env:
            logging.error(
                "❌ CRÍTICO: La variable FIREBASE_SERVICE_ACCOUNT no está configurada.")
            raise ValueError(
                "❌ Falta la variable de entorno FIREBASE_SERVICE_ACCOUNT")

        service_account_info = json.loads(service_account_env)
        fcm_credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )

    if not fcm_credentials.valid:
        logging.info("🔑 Refrescando OAuth2 Access Token para Firebase FCM...")
        fcm_credentials.refresh(Request())

    return fcm_credentials.token


def get_static_map_url(lat, lng):
    """Genera la URL del mapa estático usando la API de Geoapify."""
    return (
        f"https://maps.geoapify.com/v1/staticmap"
        f"?style=osm-bright&width=600&height=300"
        f"&center=lonlat:{lng},{lat}&zoom=7"
        f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
        f"&apiKey={GEOAPIFY_KEY}"
    )


def format_local_time(timestamp_ms, lat, lng):
    """Convierte el timestamp UTC a la hora local exacta según las coordenadas (lat, lng)."""
    utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    try:
        tz_name = tf.timezone_at(lat=lat, lng=lng)
        if tz_name:
            local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
            return local_dt.strftime("%H:%M HS (Local)")
    except Exception as e:
        logging.warning(
            f"⚠️ No se pudo determinar huso horario para ({lat}, {lng}): {e}")

    return utc_dt.strftime("%H:%M UTC")


# ==========================================
# FETCHERS DE FUENTES DE DATOS SISMO
# ==========================================
def fetch_usgs_events():
    """Consulta sismos de la última hora desde el feed oficial de USGS."""
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

                mag = props.get("mag")
                # Filtro directo: Magnitud mayor o igual a 2.5
                if mag is None or float(mag) < 2.5:
                    continue

                events.append({
                    "id": f"usgs_{feat.get('id')}",
                    "source": "USGS",
                    "magnitude": float(mag),
                    "place": props.get("place", "Ubicación no especificada"),
                    "lat": float(coords[1]),
                    "lng": float(coords[0]),
                    "depth": float(coords[2]),
                    "timestamp_ms": props.get("time", 0),
                    "url": props.get("url", "")
                })

            logging.info(
                f"🔍 [USGS] Petición exitosa en {elapsed_ms} ms. Eventos válidos M2.5+: {len(events)}")
        else:
            logging.warning(
                f"⚠️ [USGS] Código de respuesta inesperado HTTP {
                    response.status_code} ({elapsed_ms} ms)")
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ [USGS] Error consultando API ({elapsed_ms} ms): {e}")

    return events


def fetch_emsc_events():
    """Consulta sismos en tiempo real desde EMSC (Centro Sismológico Euro-Mediterráneo)."""
    start_time = time.time()
    emsc_url = "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&minmag=2.5&limit=100"
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

                mag = props.get("mag")
                if mag is None or float(mag) < 2.5:
                    continue

                time_str = props.get("time")
                timestamp_ms = 0
                if time_str:
                    dt = datetime.fromisoformat(
                        time_str.replace("Z", "+00:00"))
                    timestamp_ms = int(dt.timestamp() * 1000)

                raw_unid = feat.get("id") or props.get("unid")
                event_url = props.get(
                    "url") or f"https://www.seismicportal.eu/eventdetails.html?unid={raw_unid}"

                events.append({
                    "id": f"emsc_{raw_unid}",
                    "source": "EMSC",
                    "magnitude": float(mag),
                    "place": props.get("flynn_region", "Ubicación no especificada"),
                    "lat": float(coords[1]),
                    "lng": float(coords[0]),
                    "depth": float(coords[2]),
                    "timestamp_ms": timestamp_ms,
                    "url": event_url
                })

            logging.info(
                f"🔍 [EMSC] Petición exitosa en {elapsed_ms} ms. Eventos válidos M2.5+: {len(events)}")
        else:
            logging.warning(
                f"⚠️ [EMSC] Código de respuesta inesperado HTTP {
                    response.status_code} ({elapsed_ms} ms)")
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ [EMSC] Error consultando API ({elapsed_ms} ms): {e}")

    return events


def fetch_funvisis_events():
    """Consulta y parsea los sismos de FUNVISIS desde su GeoJSON maravilla.json."""
    start_time = time.time()
    funvisis_url = "http://www.funvisis.gob.ve/maravilla.json"
    headers = {
        "User-Agent": "EpicentroMonitor/2.0 (Android Earthquake Alert System)",
        "Accept": "application/json",
    }

    events = []
    try:
        response = http_session.get(funvisis_url, headers=headers, timeout=8)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        if response.status_code == 200:
            data = response.json()

            # En caso de que venga como un string JSON
            if isinstance(data, str):
                data = json.loads(data)

            features = data.get("features", [])

            for feat in features:
                try:
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [0, 0])

                    # 1. Magnitud (viene en el campo "phone")
                    mag_raw = props.get("phone", "0")
                    mag = float(mag_raw)

                    # Filtro de Magnitud M2.5+
                    if mag < 1.0:
                        continue

                    # 2. Coordenadas [lng, lat]
                    lng = float(coords[0])
                    lat = float(coords[1])

                    # 3. Profundidad (viene en "phoneFormatted", e.g. "17.0
                    # km")
                    depth_raw = props.get(
                        "phoneFormatted", "0").replace(
                        "km", "").strip()
                    depth = float(depth_raw)

                    # 4. Ubicación
                    place = props.get("address", "Venezuela").strip()

                    # 5. Timestamp (Fecha en "postalCode" e.g. "02-08-2026",
                    # Hora en "city" e.g. "17:46")
                    date_str = props.get("postalCode", "")
                    time_str = props.get("city", "")

                    timestamp_ms = int(
                        time.time() * 1000)  # Fallback por defecto
                    if date_str and time_str:
                        # FUNVISIS publica en hora local de Venezuela (UTC-4)
                        dt_str = f"{date_str} {time_str} -0400"
                        dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M %z")
                        timestamp_ms = int(dt.timestamp() * 1000)

                    # ID único combinando fecha, hora y coordenadas para evitar
                    # colisiones
                    raw_id = f"{date_str}_{time_str}_{lat}_{lng}".replace(
                        " ", "_")

                    events.append({
                        "id": f"funvisis_{raw_id}",
                        "source": "FUNVISIS",
                        "magnitude": mag,
                        "place": place,
                        "lat": lat,
                        "lng": lng,
                        "depth": depth,
                        "timestamp_ms": timestamp_ms,
                        "url": "http://www.funvisis.gob.ve/"
                    })

                except (ValueError, TypeError) as parse_err:
                    logging.warning(
                        f"⚠️ [FUNVISIS] Error parseando elemento individual: {parse_err}")
                    continue

            logging.info(
                f"🔍 [FUNVISIS] Petición exitosa en {elapsed_ms} ms. Eventos válidos M2.5+: {len(events)}")
        else:
            logging.warning(
                f"⚠️ [FUNVISIS] Código HTTP {
                    response.status_code} ({elapsed_ms} ms)")
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        logging.error(
            f"❌ [FUNVISIS] Error consultando API ({elapsed_ms} ms): {e}")

    return events


# ==========================================
# PROCESAMIENTO Y ENVÍO DE NOTIFICACIONES
# ==========================================
def process_and_notify_event(sismo, access_token):
    """Procesa un sismo individual, verifica la antigüedad y envía la notificación vía FCM."""
    event_id = sismo["id"]
    timestamp_ms = sismo["timestamp_ms"]
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    max_age_ms = 60 * 60 * 1000  # 60 minutos máximo de tolerancia

    delay_minutes = round((now_ms - timestamp_ms) / 60000, 1)

    # Si el evento ocurrió hace más de 1 hora, se descarta para no alertar de
    # cosas viejas
    if (now_ms - timestamp_ms) > max_age_ms:
        logging.info(
            f"⌛ Evento descartado por antigüedad ({delay_minutes} min de retraso): {event_id}")
        return

    mag_val = sismo["magnitude"]
    mag = f"{mag_val:.1f}"

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

    logging.info(
        f"🚨 ¡NUEVO SISMO M{mag}! ID: {event_id} [{source}] | {place} "
        f"| Hora: {sismo_time} | Profundidad: {depth_str}"
    )

    map_url = get_static_map_url(lat_str, lng_str)
    fcm_url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"

    # Estructura del Payload exacto consumido por la app Android
    payload = {
        "message": {
            "topic": "sismos_alertas",
            "data": {
                "eventId": str(event_id),
                "source": str(source),
                "title": f"¡ALERTA DE SISMO M {mag}! ({source})",
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
    res = http_session.post(
        fcm_url,
        headers=headers_fcm,
        data=json.dumps(payload),
        timeout=8)
    fcm_elapsed_ms = round((time.time() - fcm_start_time) * 1000, 2)

    if res.status_code == 200:
        logging.info(
            f"✅ FCM Notificado con éxito: {event_id} ({fcm_elapsed_ms} ms)")
        PROCESSED_EVENTS.add(event_id)
    else:
        logging.error(
            f"❌ Error enviando FCM ({
                res.status_code}) [{fcm_elapsed_ms} ms]: {
                res.text}")

    # Control del tamaño del Cache en memoria RAM
    if len(PROCESSED_EVENTS) > MAX_CACHE_SIZE:
        popped = PROCESSED_EVENTS.pop()
        logging.debug(f"🧹 Cache lleno. Eliminado evento antiguo: {popped}")


# ==========================================
# RUTINA DE MONITOREO PRINCIPAL
# ==========================================
def check_earthquakes_and_notify():
    """Rutina principal que recolecta, unifica y gestiona los eventos sísmicos de todas las fuentes."""
    global http_session
    cycle_start = time.time()
    try:
        # Purgar periódicamente lecturas viejas del detector de sensores
        community_detector._clean_expired_readings()

        usgs_events = fetch_usgs_events()
        emsc_events = fetch_emsc_events()
        funvisis_events = fetch_funvisis_events()

        all_events = usgs_events + emsc_events + funvisis_events
        if not all_events:
            return

        access_token = None
        new_events_count = 0

        for sismo in all_events:
            event_id = sismo.get("id")

            # Omitir si el evento no tiene ID o ya fue procesado previamente
            if not event_id or event_id in PROCESSED_EVENTS:
                continue

            # Obtención perezosa (lazy loading) del Access Token de Firebase
            if not access_token:
                access_token = get_fcm_access_token()

            process_and_notify_event(sismo, access_token)
            new_events_count += 1

        total_elapsed = round((time.time() - cycle_start) * 1000, 2)
        logging.info(
            f"⏱️ Monitoreo completado en {total_elapsed} ms. Eventos procesados en este ciclo: {new_events_count}")

    except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
        logging.warning(
            "⚠️ Conexión de red reseteada. Recreando sesión HTTP...",
            exc_info=False)
        http_session = create_http_session()
    except Exception as e:
        logging.error(
            f"❌ Error no controlado en rutina de monitoreo: {e}",
            exc_info=True)


def worker_loop():
    """Hilo secundario que ejecuta el chequeo infinito cada 15 segundos."""
    logging.info(
        "🚀 Worker Global M2.5+ iniciado. Frecuencia de escaneo: 15 segundos.")
    while True:
        try:
            check_earthquakes_and_notify()
        except Exception as e:
            logging.error(
                f"❌ Error en el bucle del worker: {e}",
                exc_info=True)
        time.sleep(15)


# ==========================================
# INICIALIZACIÓN
# ==========================================
# Arrancar el hilo de segundo plano para el monitoreo sísmico
threading.Thread(target=worker_loop, daemon=True).start()

if __name__ == "__main__":
    # Arrancar la app de Flask para escuchar peticiones
    # Web/Healthchecks/Sensores
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🌍 Servidor Flask iniciando en puerto {port}")
    app.run(host="0.0.0.0", port=port)
