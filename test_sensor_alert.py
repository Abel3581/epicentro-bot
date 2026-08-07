import time
import requests

SERVER_URL = "https://epicentro-backend.onrender.com/api/v1/sensor/report"  # Cambia por la URL de tu backend en Render si aplica

# Simulamos 3 dispositivos diferentes en coordenadas muy cercanas
devices = [
    {"device_id": "phone_test_01", "latitude": 10.4806, "longitude": -66.9036, "peak_g": 3.2},
    {"device_id": "phone_test_02", "latitude": 10.4820, "longitude": -66.9010, "peak_g": 2.8},
    {"device_id": "phone_test_03", "latitude": 10.4795, "longitude": -66.9050, "peak_g": 3.5},
]

print("🚀 Enviando reportes simulados de sensores al servidor...")

for dev in devices:
    payload = {
        "device_id": dev["device_id"],
        "timestamp": int(time.time()),
        "latitude": dev["latitude"],
        "longitude": dev["longitude"],
        "peak_g": dev["peak_g"]
    }
    
    response = requests.post(SERVER_URL, json=payload)
    print(f"Device {dev['device_id']}: HTTP {response.status_code} -> {response.json()}")

print("✅ Peticiones enviadas. Verifica los logs del servidor para ver si se disparó la alerta FCM.")