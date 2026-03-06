import requests
import json

# --- CONFIGURACIÓN SEGÚN TU POSTMAN ---
ACCESS_KEY = "sheriff_LGRIz156"
ACCESS_SECRET = "mIoxh9XKHjr7FguUBp/e"
# Base URL sin el path para construirlo dinámicamente
BASE_URL = "https://prod.api.thesheriff.cl/api/clients/v2"

def obtener_token():
    # EL ENDPOINT CORRECTO SEGÚN TU DOC ES: /apiCredentials/getToken
    auth_url = f"{BASE_URL}/apiCredentials/getToken"
    
    payload = {
        "accessKey": ACCESS_KEY,
        "accessSecret": ACCESS_SECRET
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Intentando obtener token en: {auth_url}")
    
    try:
        response = requests.post(auth_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            res_json = response.json()
            # Según tu script de Postman: pm.environment.set("bearer_token", response.data);
            # Esto indica que el token es el valor de la llave 'data'
            token = res_json.get("data")
            return token
        else:
            print(f"Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"Error de conexión: {e}")
        return None

def consultar_resumen_rut(token, rut):
    # Basado en el endpoint 'resumen' de tu doc: /helper/resumen?rut={{rut}}
    url = f"{BASE_URL}/helper/resumen"
    params = {"rut": rut}
    
    headers = {
        "Authorization": f"Bearer {token}",
        "x-client-identifier": "SheriffSecureClient-v1",
        "accept": "application/json"
    }
    
    print(f"Consultando resumen para RUT: {rut}")
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": response.status_code, "detalle": response.text}

# --- EJECUCIÓN ---
token = obtener_token()

if token:
    print("✅ Token obtenido con éxito")
    
    # 1. Probar Consulta de Resumen (según tu doc)
    rut_a_consultar = "77992230-8"
    resultado = consultar_resumen_rut(token, rut_a_consultar)
    
    print("\n--- Resultado de la consulta ---")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
else:
    print("\n No se pudo obtener el token.")