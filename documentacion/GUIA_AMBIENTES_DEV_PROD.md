# Guía: Ambientes de Desarrollo y Producción - CarrierSync

Esta guía describe cómo tener **desarrollo (dev)** y **producción (prod)** separados: bases de datos, Cloud Run, VM del scraper SII y variables de entorno.

---

## 1. Resumen: qué cambia entre dev y prod

| Aspecto | Desarrollo (dev) | Producción (prod) |
|--------|-------------------|--------------------|
| **Base de datos** | MongoDB dev (ej. `Samanta_Dev`) | MongoDB prod (ej. `Samanta`) |
| **Cloud Run** | Servicio `carriersync-dev` | Servicio `carriersync` o `carriersync-prod` |
| **Proyecto GCP** | `carriersync-dev` (opcional) | `carriersync-prod` |
| **VM Scraper SII** | **Misma VM y mismo puerto** (ej. `http://IP_VM:8080`) | **Misma VM y mismo puerto** |
| **Archivo variables** | `env.dev.yaml` | `env.prod.yaml` |
| **Rama Git** | `develop` | `production` |

---

## 2. Arquitectura

- **Cloud Run**: API CarrierSync (FastAPI). Recibe POST `/api/v1/carga-giros`, orquesta la carga y llama a la VM.
- **VM**: API de scraping SII (FastAPI + Selenium). Expone `POST /api/v1/sii/giros` con `{"rut": "..."}`. Se ejecuta en VM para no bloquear IPs de Google.
- **MongoDB**: Colecciones `RT_carrier` (datos de transportistas) y `carrier_giros_sync_log` (logs de cada job de carga).

---

## 3. Archivos de variables

| Archivo | Uso | En Git |
|---------|-----|--------|
| `env.dev.yaml` | Desarrollo | No (.gitignore) |
| `env.prod.yaml` | Producción | No (.gitignore) |

Crear a partir de `env.dev.yaml.example` y `env.prod.yaml.example`. Variables importantes:

- `MONGODB_URL`, `MONGODB_DATABASE` (distintos entre dev y prod)
- `VM_SII_SCRAPER_URL`: **misma URL en dev y prod** (ej. `http://34.x.x.x:8080`)
- `ENVIRONMENT`: `dev` o `prod`
- `LOG_LEVEL`: `DEBUG` (dev) o `INFO` (prod)

---

## 4. Despliegue desde la consola (Windows)

Si **nunca has desplegado en Cloud** (crear proyecto GCP, habilitar APIs, env, primer deploy): **[SETUP_CLOUD_PASO_A_PASO.md](SETUP_CLOUD_PASO_A_PASO.md)** (todo con comandos).

Desde la raíz del proyecto:

```bat
REM Desarrollo
tools\DESPLEGAR.bat dev
REM o
tools\DESPLEGAR_DEV.bat

REM Producción
tools\DESPLEGAR.bat prod
REM o
tools\DESPLEGAR_PROD.bat
```

---

## 5. VM del Scraper SII

**Dev y prod usan la misma VM y el mismo puerto.** Solo se diferencia la base de datos y el servicio de Cloud Run; la VM del scraper es compartida.

1. Crear **una** VM (GCP o cualquiera) con Chrome/Chromium y Python 3.11.
2. Clonar el repo y ejecutar en la VM:
   ```bash
   chmod +x scripts/setup-vm.sh
   ./scripts/setup-vm.sh
   ```
3. El servicio `carrier-sii-scraper` escucha en el puerto **8080**.
4. En **ambos** `env.dev.yaml` y `env.prod.yaml` configurar la **misma** URL:
   - `VM_SII_SCRAPER_URL: "http://IP_VM:8080"` (misma IP y mismo puerto en dev y prod).

---

## 6. CI/CD (GitHub Actions)

- **Push a `develop`**: despliega `carriersync-dev` (usa secret `ENV_DEV_YAML` y `GCP_SA_KEY_DEV`).
- **Push a `production`**: despliega `carriersync-prod` (usa `ENV_PROD_YAML` y `GCP_SA_KEY_PROD`).

En GitHub: Settings → Secrets → crear `ENV_DEV_YAML`, `ENV_PROD_YAML` (contenido completo del YAML) y las claves de cuenta de servicio GCP.

---

## 7. Resumen de comandos

```bash
# Desarrollo
gcloud config set project carriersync-dev
tools\DESPLEGAR.bat dev

# Producción
gcloud config set project carriersync-prod
tools\DESPLEGAR.bat prod
```

---

## 8. Docker local y qué corre en la VM

**¿Qué significa “la VM no se incluye en docker-compose”?**

- **docker-compose** (y Cloud Run) levantan solo la **API de CarrierSync** que corre en la nube: la que recibe `POST /api/v1/carga-giros`, habla con MongoDB y **llama por HTTP** a la VM.
- El **scraper** (Chrome/Selenium que entra al SII para obtener giros) no puede ir en ese contenedor: necesita un navegador en una máquina con IP distinta para no bloquear. Por eso el scraper corre en una **máquina virtual (VM)** que tú despliegas aparte (script `setup-vm.sh`, servicio systemd). La API en la nube solo necesita la URL de esa VM (`VM_SII_SCRAPER_URL`).

Para probar la API en local con Docker:

```bash
# Crear .env con MONGODB_URL y VM_SII_SCRAPER_URL (opcional)
docker-compose up -d
# API en http://localhost:8080
```

La VM del scraper debe estar desplegada por separado (misma VM que gestion_documental o una VM solo para CarrierSync; ver sección 9).

---

## 9. Usar la misma VM que gestion_documental

**Sí, puedes usar la misma máquina virtual** que ya usas para el proyecto **gestion_documental** (verificación DT, F30, etc.). En esa VM conviven dos cosas:

| Servicio | Proyecto | Puerto típico |
|----------|----------|----------------|
| API de verificación (DT, F30, etc.) | gestion_documental | 8080 (prod), 8081 (dev) |
| API scraper SII (giros) | CarrierSync | **8082** (dev y prod comparten este puerto) |

**Por qué otro puerto:** en la misma VM no pueden escuchar dos servicios en el mismo puerto. gestion_documental ya usa 8080 y 8081, así que el scraper SII de CarrierSync usa **8082**.

**Pasos para compartir la VM:**

Toda la configuración de la VM (con script, comandos, actualizar código y opción manual) está en un solo documento: **[README_VM.md](README_VM.md)**.

En **[README_VM.md](README_VM.md)** tienes los 7 pasos en orden (firewall → SSH → Chromium → clonar → script → comprobar → env), la tabla resumen, comandos útiles, cómo actualizar y la opción manual con nano.

**Actualizaciones: cada proyecto por su lado**

- Si cambias algo **solo del scraper SII** (código en CarrierSync, p. ej. `vm_services/sii_scraper_api.py`): en la VM actualizas solo el repo **CarrierSync**, reinicias solo el servicio del scraper (ej. `sudo systemctl restart carrier-sii-scraper`). No tocas gestion_documental.
- Si cambias algo **solo de la verificación DT** (código en gestion_documental, p. ej. `vm_services/verification_api.py`): en la VM actualizas solo el repo **gestion_documental** y reinicias el servicio de verificación. No tocas CarrierSync.

Cada proyecto tiene su propio código de VM en su repo y su propio servicio systemd; se actualizan de forma independiente.
