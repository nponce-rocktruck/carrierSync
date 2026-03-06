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

## Desarrollo local

```bash
# Dependencias
pip install -r requirements.txt

# Variables (crear .env o exportar)
# MONGODB_URL, MONGODB_DATABASE, VM_SII_SCRAPER_URL (opcional si no tienes VM)

# Ejecutar API
python main.py
# o
uvicorn main:app --reload --port 8000
```

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
| POST | /api/v1/carga-giros | Inicia carga/actualización de giros (body: run_type, opcional rut_list, carrier_ids). Devuelve job_id. |
| GET | /api/v1/carga-giros/{job_id} | Estado del job (totales, status). |
| GET | /api/v1/carga-giros/{job_id}/detalle | Detalle completo (incluye details por carrier). |
| GET | /api/v1/carga-giros | Lista de jobs (query: limit, run_type). |
| GET | /health | Health check. |

## Documentación

- [Guía ambientes Dev/Prod](documentacion/GUIA_AMBIENTES_DEV_PROD.md) (incluye compartir la VM con gestion_documental)
- [Documentación técnica giros](documentacion/DOCUMENTACION_TECNICA_GIROS.md)
- **Solo comandos:** [Cloud – crear proyecto y desplegar](documentacion/SETUP_CLOUD_PASO_A_PASO.md) | [VM – todo en uno (script + comandos)](documentacion/README_VM.md)

## Licencia

Uso interno.
