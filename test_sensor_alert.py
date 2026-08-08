import time
import requests

# URL de tu backend en Render
BASE_URL = "https://epicentro-backend.onrender.com"
ENDPOINT = f"{BASE_URL}/api/v1/sensor/report"

# Coordenadas de prueba (Caracas)
LAT = 10.4806
LNG = -66.9036

print("🚀 Enviando 3 reportes simulados para activar alerta M5.0...")

# Se ajustan las aceleraciones para dar un promedio de ~12.5 m/s² de
# desviación (M5.0)
devices = [
    {
        "userId": "sim_device_01",
        "latitude": LAT,
        "longitude": LNG,
        "accelX": 8.0,
        "accelY": 6.0,
        # Vector total ≈ 22.36 m/s² -> Desviación ≈ 12.55 m/s² (M5.0)
        "accelZ": 20.0
    },
    {
        "userId": "sim_device_02",
        "latitude": LAT + 0.001,
        "longitude": LNG + 0.001,
        "accelX": 7.5,
        "accelY": 6.5,
        # Vector total ≈ 22.51 m/s² -> Desviación ≈ 12.70 m/s² (M5.1)
        "accelZ": 20.2
    },
    {
        "userId": "sim_device_03",
        "latitude": LAT - 0.001,
        "longitude": LNG - 0.001,
        "accelX": 8.2,
        "accelY": 5.8,
        # Vector total ≈ 22.20 m/s² -> Desviación ≈ 12.39 m/s² (M5.0)
        "accelZ": 19.8
    },
]

for dev in devices:
    dev["timestampMs"] = int(time.time() * 1000)

    try:
        res = requests.post(ENDPOINT, json=dev, timeout=10)
        print(
            f"Dispositivo {dev['userId']}: HTTP {res.status_code} -> {res.json()}")
    except Exception as e:
        print(f"❌ Error al enviar datos desde {dev['userId']}: {e}")

    time.sleep(1)

print("\n✅ Proceso completado. Revisa la notificación M5.0 en tu teléfono.")
