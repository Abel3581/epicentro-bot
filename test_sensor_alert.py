import time
import requests

# ⚠️ REEMPLAZA ESTA URL CON LA TUYA REAL DE RENDER
BASE_URL = "https://epicentro-backend.onrender.com" 
ENDPOINT = f"{BASE_URL}/api/v1/sensor/report"

# Usamos coordenadas de Caracas (o cámbialas a tu ubicación actual)
LAT = 10.4806
LNG = -66.9036

print("🚀 Enviando 3 reportes en la misma zona para activar la alerta comunitaria...")

# Enviamos 3 reportes continuos desde 3 IDs simulados diferentes en la misma zona
devices = ["sim_device_01", "sim_device_02", "sim_device_03"]

for dev_id in devices:
    payload = {
        "device_id": dev_id,
        "timestamp": int(time.time()),
        "latitude": LAT,
        "longitude": LNG,
        "peak_g": 3.2
    }
    
    try:
        res = requests.post(ENDPOINT, json=payload, timeout=10)
        print(f"Dispositivo {dev_id}: HTTP {res.status_code} -> {res.json()}")
    except Exception as e:
        print(f"❌ Error al enviar datos: {e}")
    
    time.sleep(1) # Esperamos 1 segundo entre cada envio

print("\n✅ Proceso completado. Si la app en tu celular está suscrita al tema 'sismos_alertas', debería llegar la notificación.")