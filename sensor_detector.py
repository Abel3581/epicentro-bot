import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ==========================================
# CONFIGURACIÓN DE LOGS PARA DEBUGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SENSOR_DETECTOR] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ==========================================
# MODELOS DE DATOS (DATACLASSES)
# ==========================================
@dataclass
class AccelerometerReading:
    """Representa un evento de lectura individual enviado por un dispositivo Android."""
    user_id: str
    lat: float
    lng: float
    accel_x: float
    accel_y: float
    accel_z: float
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

@property
def net_acceleration(self) -> float:
    """
    Calcula la magnitud del vector de aceleración total en m/s² y resta 1G (9.81 m/s²).
    Un valor cercano a 0 representa reposo.
    """
    raw_mag = math.sqrt(self.accel_x**2 + self.accel_y**2 + self.accel_z**2)
    return abs(raw_mag - 9.81)

@dataclass
class SeismicCluster:
    """Representa una concentración de lecturas anómalas en un área y tiempo determinado."""
    cluster_id: str
    center_lat: float
    center_lng: float
    readings_count: int
    avg_intensity: float
    timestamp_ms: int


# ==========================================
# CLASE PRINCIPAL: DETECTOR DE SISMOS COMUNITARIO
# ==========================================
class SeismicSensorDetector:
    """
    Motor de análisis en tiempo real para filtrar ruido, agrupar alertas
    de acelerómetros de teléfonos Android y determinar si hay un sismo activo.
    """

    def __init__(
        self,
        threshold_g: float = 2.5,
        time_window_seconds: int = 10,
        min_reports_for_alert: int = 3,
        cluster_radius_km: float = 20.0,
    ):
        """
        :param threshold_g: Umbral de aceleración sísmica brusca en m/s² (ej: > 2.5 m/s² desviado de 1G)
        :param time_window_seconds: Ventana de tiempo (segundos) para evaluar coincidencia de reportes
        :param min_reports_for_alert: Dispositivos mínimos en la misma zona para confirmar sismo
        :param cluster_radius_km: Radio de proximidad geográfica entre teléfonos
        """
        self.threshold_g = threshold_g
        self.time_window_seconds = time_window_seconds
        self.min_reports_for_alert = min_reports_for_alert
        self.cluster_radius_km = cluster_radius_km

        # Buffer en memoria para mantener lecturas dentro de la ventana de tiempo
        self._buffer: List[AccelerometerReading] = []

    # ----------------------------------------------------------------------
    # MÉTODOS PÚBLICOS
    # ----------------------------------------------------------------------
    def process_incoming_report(self, payload: dict) -> Optional[SeismicCluster]:
        """
        Punto de entrada principal. Recibe un JSON/Dict enviado por la app Android,
        lo valida, actualiza el buffer y retorna un SeismicCluster si se confirma un sismo.
        """
        reading = self._parse_and_validate(payload)
        if not reading:
            return None

        # Verificar si la sacudida supera el umbral de aceleración sísmica
        intensity = reading.net_acceleration
        if intensity < self.threshold_g:
            logging.debug(
                f"ℹ️ Lectura normal omitida de User {reading.user_id[:6]}... "
                f"(Desviación: {intensity:.2f} m/s² < Umbral {self.threshold_g} m/s²)"
            )
            return None

        logging.warn(
            f"⚡ [ANOMALÍA DETECTADA] User: {reading.user_id} | "
            f"Desviación: {intensity:.2f} m/s² | Ubicación: ({reading.lat}, {reading.lng})"
        )

        # Agregar al buffer y purgar eventos caducados
        self._buffer.append(reading)
        self._clean_expired_readings()

        # Analizar si hay acumulación de reportes cercanos (Clustering)
        return self._evaluate_clusters(reading)

    # ----------------------------------------------------------------------
    # MÉTODOS PRIVADOS / LÓGICA INTERNA
    # ----------------------------------------------------------------------
    def _parse_and_validate(self, data: dict) -> Optional[AccelerometerReading]:
        """Valida que la carga útil tenga la estructura y los tipos correctos."""
        try:
            user_id = str(data.get("userId", "unknown"))
            lat = float(data.get("latitude", 0.0))
            lng = float(data.get("longitude", 0.0))
            accel_x = float(data.get("accelX", 0.0))
            accel_y = float(data.get("accelY", 0.0))
            accel_z = float(data.get("accelZ", 0.0))
            ts = int(data.get("timestampMs", time.time() * 1000))

            if lat == 0.0 and lng == 0.0:
                logging.warning("⚠️ Reporte descartado: Coordenadas inválidas (0.0, 0.0)")
                return None

            return AccelerometerReading(
                user_id=user_id,
                lat=lat,
                lng=lng,
                accel_x=accel_x,
                accel_y=accel_y,
                accel_z=accel_z,
                timestamp_ms=ts,
            )
        except (ValueError, TypeError) as parse_err:
            logging.error(f"❌ Error parseando payload de sensor: {parse_err} | Payload: {data}")
            return None

    def _clean_expired_readings(self):
        """Elimina lecturas que superan el límite de la ventana de tiempo."""
        current_time_ms = time.time() * 1000
        cutoff_ms = current_time_ms - (self.time_window_seconds * 1000)

        initial_count = len(self._buffer)
        self._buffer = [r for r in self._buffer if r.timestamp_ms >= cutoff_ms]
        purged = initial_count - len(self._buffer)

        if purged > 0:
            logging.debug(f"🧹 Purgadas {purged} lecturas antiguas fuera de la ventana de {self.time_window_seconds}s")

    def _evaluate_clusters(self, trigger_reading: AccelerometerReading) -> Optional[SeismicCluster]:
        """Agrupa eventos espacialmente cercanos usando la fórmula de Haversine."""
        matching_readings = []

        for r in self._buffer:
            dist = self._haversine_distance(trigger_reading.lat, trigger_reading.lng, r.lat, r.lng)
            if dist <= self.cluster_radius_km:
                matching_readings.append(r)

        report_count = len(matching_readings)
        logging.info(
            f"🔍 Evaluando zona ({trigger_reading.lat:.3f}, {trigger_reading.lng:.3f}): "
            f"{report_count}/{self.min_reports_for_alert} dispositivos detectando movimiento"
        )

        if report_count >= self.min_reports_for_alert:
            # Calcular epicentro estimado (promedio de coordenadas) e intensidad promedio
            avg_lat = sum(r.lat for r in matching_readings) / report_count
            avg_lng = sum(r.lng for r in matching_readings) / report_count
            avg_intensity = sum(r.net_acceleration for r in matching_readings) / report_count

            cluster_id = f"comunitario_{int(time.time())}_{round(avg_lat, 2)}_{round(avg_lng, 2)}"

            logging.critical(
                f"🚨 ¡ALERTA CONFIRMADA POR RED COMUNITARIA! "
                f"Cluster: {cluster_id} | Dispositivos: {report_count} | Intensidad promedio: {avg_intensity:.2f} m/s²"
            )

            # Limpiar el buffer para evitar falsos disparos consecutivos del mismo evento
            self._buffer.clear()

            return SeismicCluster(
                cluster_id=cluster_id,
                center_lat=avg_lat,
                center_lng=avg_lng,
                readings_count=report_count,
                avg_intensity=avg_intensity,
                timestamp_ms=int(time.time() * 1000),
            )

        return None

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcula la distancia geodésica en kilómetros entre dos puntos (lat, lng)."""
        R = 6371.0  # Radio medio de la Tierra en kilómetros

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c