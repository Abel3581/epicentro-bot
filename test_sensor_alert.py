import time
import requests

BASE_URL = "https://epicentro-backend.onrender.com"
ENDPOINT = f"{BASE_URL}/api/v1/sensor/report"

LAT = 10.4806
LNG = -66.9036

# 1. Petición de calentamiento para despertar la instancia de Render
print("⏳ Despertando servidor Render...")
try:
    requests.get(BASE_URL, timeout=15)
    print("✅ Servidor activo.")
except Exception:
    print("⚠️ El servidor tardó en responder, continuando...")

time.sleep(2)

print("\n🚀 Enviando 3 reportes simulados para activar alerta M5.0...")

devices = [
    {
        "userId": "sim_device_01",
        "latitude": LAT,
        "longitude": LNG,
        "accelX": 8.0,
        "accelY": 6.0,
        "accelZ": 20.0,
    },
    {
        "userId": "sim_device_02",
        "latitude": LAT + 0.001,
        "longitude": LNG + 0.001,
        "accelX": 7.5,
        "accelY": 6.5,
        "accelZ": 20.2,
    },
    {
        "userId": "sim_device_03",
        "latitude": LAT - 0.001,
        "longitude": LNG - 0.001,
        "accelX": 8.2,
        "accelY": 5.8,
        "accelZ": 19.8,
    },
]

for dev in devices:
    dev["timestampMs"] = int(time.time() * 1000)

    # Reintento en caso de respuesta no JSON
    for intento in range(2):
        try:
            res = requests.post(ENDPOINT, json=dev, timeout=30)
            data = res.json()  # Intenta parsear JSON
            print(
                f"Dispositivo {dev['userId']}: HTTP {res.status_code} -> {data}"
            )
            break
        except Exception as e:
            if intento == 0:
                print(
                    f"⚠️ Fallo en {dev['userId']}, reintentando en 1s... ({e})"
                )
                time.sleep(1)
            else:
                print(f"❌ Error definitivo en {dev['userId']}: {e}")

    time.sleep(1)

print("\n✅ Simulación finalizada.")