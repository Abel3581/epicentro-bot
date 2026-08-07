import time
import requests

# URL de tu backend en Render
BASE_URL = "https://epicentro-backend.onrender.com"
ENDPOINT = f"{BASE_URL}/api/v1/sensor/report"

# Coordenadas de prueba (Caracas)
LAT = 10.4806
LNG = -66.9036

print("🚀 Enviando 3 reportes simulados en la misma zona para activar la alerta comunitaria...")

# Tres dispositivos simulados en ubicaciones muy cercanas
devices = [
    {"userId": "sim_device_01", "latitude": LAT, "longitude": LNG,
        "accelX": 1.2, "accelY": 0.8, "accelZ": 13.0},
    {"userId": "sim_device_02",
     "latitude": LAT + 0.001,
     "longitude": LNG + 0.001,
     "accelX": 0.5,
     "accelY": 2.1,
     "accelZ": 13.5},
    {"userId": "sim_device_03",
     "latitude": LAT - 0.001,
     "longitude": LNG - 0.001,
     "accelX": 1.8,
     "accelY": 1.1,
     "accelZ": 12.8},
]

for dev in devices:
    # Agregamos timestamp actual en milisegundos
    dev["timestampMs"] = int(time.time() * 1000)

    try:
        res = requests.post(ENDPOINT, json=dev, timeout=10)
        print(
            f"Dispositivo {dev['userId']}: HTTP {res.status_code} -> {res.json()}")
    except Exception as e:
        print(f"❌ Error al enviar datos desde {dev['userId']}: {e}")

    time.sleep(1)  # Espera de 1 segundo entre envíos

print("\n✅ Proceso completado. Si la app en tu celular está suscrita al tema 'sismos_alertas', debería llegar la notificación push.")
