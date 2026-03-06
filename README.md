# CarrierSync

API para **sincronización de giros** (actividades económicas) de transportistas con el SII. Pobla el campo `economicActivities` en la colección **RT_carrier** de MongoDB, con trazabilidad en **carrier_giros_sync_log**.

- **Cloud**: API en **Google Cloud Run** (FastAPI).
- **VM**: Scraping al SII corre en una **máquina virtual** para no bloquear IPs (Selenium/Chrome).
- **Ambientes**: Dev y Prod separados (DB, Cloud Run); **misma VM y mismo puerto** para el scraper SII.

## Requisitos

- Python 3.11+
- MongoDB (colección `RT_carrier` existente)
- VM con Chrome/Chromium para el scraper SII (opcional Oxylabs)

## Estructura

```
carrierSync/
├── main.py              # API FastAPI (Cloud Run)
├── database/            # MongoDB (RT_carrier, carrier_giros_sync_log)
├── models/              # Pydantic (EconomicActivity, CargaGirosRequest/Response)
├── routes/              # health, carga-giros
├── services/            # carrier_giros_service, sync_log_service, sii_vm_client
├── vm_services/         # API scraper SII para VM (sii_scraper_api.py)
├── utils/               # logging, rut_chileno
├── tools/               # deploy dev/prod (PowerShell + .bat)
├── scripts_vm/          # systemd (scraper en 8080; dev y prod comparten VM)
└── documentacion/       # Guía ambientes, doc técnica giros
```

## Probar en local (API + VM + base de datos dev)

Para probar todo en tu PC apuntando a la **base de datos de dev** y a la **VM del scraper** (sin desplegar en Cloud):

1. **VM ya configurada** (firewall 8082 + scraper corriendo en la VM, ver [README_VM.md](documentacion/README_VM.md)).

2. **Variables de entorno:** En la raíz del proyecto ten **env.dev.yaml** con al menos:
   - `MONGODB_URL`, `MONGODB_DATABASE` (base de dev, ej. `Rocktruck` o `Samanta_Dev`),
   - `VM_SII_SCRAPER_URL` (ej. `http://34.176.102.209:8082`).
   La app carga automáticamente `env.dev.yaml` cuando corres en local (no en Cloud Run).

3. **Desde la raíz del proyecto** (ej. `C:\Users\pc\Documents\GitHub\carrierSync`):

```powershell
# Dependencias (solo la primera vez)
pip install -r requirements.txt

# Levantar la API en local (puerto 8000)
python main.py
```

   O con recarga al cambiar código:

```powershell
uvicorn main:app --reload --port 8000
```

4. **Probar:**
   - **Health:** http://localhost:8000/health  
   - **Docs:** http://localhost:8000/docs  
   - **Carga de giros:** POST http://localhost:8000/api/v1/carga-giros con body por ejemplo `{"run_type": "inicial"}` o `{"run_type": "inicial", "rut_list": ["12345678-9"]}` para un solo RUT. La API usará la VM (`VM_SII_SCRAPER_URL`) y escribirá en la base de dev (`MONGODB_DATABASE`).

Si quieres sobreescribir algo (ej. otra base), crea un `.env` con las variables que necesites; se aplican después de `env.dev.yaml`.

## Despliegue Cloud Run (Windows)

```bat
tools\DESPLEGAR.bat dev   # desarrollo
tools\DESPLEGAR.bat prod  # producción
```

Requiere `env.dev.yaml` y/o `env.prod.yaml` (copiar desde `env.dev.yaml.example` y `env.prod.yaml.example`).

## VM Scraper SII

En la VM donde correrá el scraper:

```bash
chmod +x scripts/setup-vm.sh
./scripts/setup-vm.sh
```

Configurar en **ambos** `env.dev.yaml` y `env.prod.yaml` la **misma** variable **VM_SII_SCRAPER_URL** (ej. `http://IP_VM:8080`). Dev y prod usan la misma VM y el mismo puerto.

**Compartir la VM con gestion_documental:** misma VM donde corre la verificación (DT/F30), scraper SII en puerto **8082**. Todo (script, comandos, actualizar, problemas, opción manual): **[README_VM.md](documentacion/README_VM.md)**.

## API - Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | /api/v1/carga-giros | Inicia carga/actualización de giros (body: run_type, opcional rut_list, carrier_ids). Devuelve job_id, total_carriers y **ruts_no_encontrados_en_rt_carrier** (RUTs enviados que no están en RT_carrier). |
| GET | /api/v1/carga-giros/{job_id} | Estado del job (totales, status, ruts_no_encontrados_en_rt_carrier). |
| GET | /api/v1/carga-giros/{job_id}/detalle | Detalle completo (incluye details por carrier y ruts_no_encontrados_en_rt_carrier). |
| GET | /api/v1/carga-giros | Lista de jobs (query: limit, run_type). |
| GET | /health | Health check. |

Cuando se envía **rut_list**, la respuesta indica cuántos carriers se procesarán (`total_carriers`) y qué RUTs de la lista no existen en RT_carrier (`ruts_no_encontrados_en_rt_carrier`). Ver [Cómo llamar al servicio](documentacion/COMO_LLAMAR_SERVICIO.md) para la estructura completa de las respuestas.

## Documentación

- **[Cómo llamar al servicio](documentacion/COMO_LLAMAR_SERVICIO.md)** – Ejemplos: todos los RUTs, lista de RUTs, por carrier_id (ObjectId), consultar estado del job.
- [Guía ambientes Dev/Prod](documentacion/GUIA_AMBIENTES_DEV_PROD.md) (incluye compartir la VM con gestion_documental)
- [Documentación técnica giros](documentacion/DOCUMENTACION_TECNICA_GIROS.md)
- **Solo comandos:** [Cloud – crear proyecto y desplegar](documentacion/SETUP_CLOUD_PASO_A_PASO.md) | [VM – todo en uno (script + comandos)](documentacion/README_VM.md)

## Licencia

Uso interno.
