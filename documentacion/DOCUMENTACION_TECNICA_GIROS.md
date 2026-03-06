# Documentación Técnica - Sincronización de Giros (CarrierSync)

## 1. Objetivo

Poblar y mantener un **único objeto de giros** en la colección **RT_carrier** de MongoDB, consultando el SII mediante automatización que corre en una **VM** (no en Cloud) para evitar bloqueos de IP. El objeto solo se escribe cuando el proceso termina bien; si falla, no se actualiza. En cada actualización se reemplaza toda la lista de giros. Diferenciar **carga inicial** y **actualizaciones periódicas** y registrar en una colección de log el resultado por cada RUT/carrier.

---

## 2. Modelo de datos

### 2.1 RT_carrier – Objeto `giros_sync`

Se agrega (o se actualiza) **un solo objeto** llamado **giros_sync**, que contiene:

- **updated_giros_at** (fecha): cuándo se actualizó por última vez (solo se setea cuando el proceso de ese carrier resultó bien).
- **initial_sync_at** (fecha): cuándo se hizo la primera carga inicial exitosa de giros para ese carrier (se setea una vez y no se sobrescribe).
- **economicActivities** (array): lista de actividades económicas; **solo se escribe cuando todo el proceso para ese carrier resultó bien**. Si la consulta al SII falla o no encuentra datos, no se toca este objeto (no se borra ni se actualiza).

En cada **actualización exitosa** se **eliminan todos** los giros anteriores y se **reescriben** únicamente los que devolvió el SII (reemplazo total). Es la opción recomendada: la fuente de verdad es siempre la última respuesta del SII y se evitan giros obsoletos o lógica de merge.

Ejemplo del objeto en un documento de RT_carrier:

```json
{
  "_id": ObjectId("..."),
  "tax_id": "13.090.093-3",
  "name": "VICTOR RAMON PARADA MARTINEZ",
  "giros_sync": {
    "updated_giros_at": ISODate("2026-03-05T14:00:00Z"),
    "initial_sync_at": ISODate("2026-03-01T10:00:00Z"),
    "economicActivities": [
      {
        "code": "492300",
        "description": "TRANSPORTE DE CARGA POR CARRETERA",
        "category": "Primera",
        "isVatSubject": true,
        "startDate": ISODate("2003-09-30T00:00:00Z"),
        "lastUpdatedAt": ISODate("2026-03-01T00:00:00Z"),
        "dataSource": "consulta_automatizacion",
        "extractedAt": ISODate("2026-03-05T14:00:00Z")
      },
      {
        "code": "522900",
        "description": "OTRAS ACTIVIDADES ANEXAS AL TRANSPORTE",
        "category": "Primera",
        "isVatSubject": true,
        "startDate": ISODate("2005-06-15T00:00:00Z"),
        "lastUpdatedAt": ISODate("2026-02-15T00:00:00Z"),
        "dataSource": "consulta_automatizacion",
        "extractedAt": ISODate("2026-03-05T14:00:00Z")
      }
    ]
  }
}
```

Si para un carrier la consulta al SII falla (timeout, RUT no encontrado, etc.), el campo **giros_sync** no se crea ni se modifica; el documento del carrier queda como estaba.

### 2.2 carrier_giros_sync_log (colección de log)

La colección **carrier_giros_sync_log** se crea automáticamente la primera vez que se ejecuta un job (no es necesario crearla a mano). Cada ejecución de carga/actualización se registra en un documento con:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| job_id | string | UUID del job |
| run_type | string | `initial_load` o `periodic_update` |
| status | string | `running`, `completed`, `partial`, `failed` |
| started_at | date | Inicio del job |
| finished_at | date | Fin (null si sigue running) |
| total_carriers | int | Total de carriers a procesar (los que sí existen en RT_carrier) |
| processed | int | Procesados |
| updated | int | Actualizados correctamente |
| not_found_in_sii | int | RUT no encontrado en SII |
| sii_failed | int | Error al consultar SII (timeout, fallo VM, etc.) |
| not_processed | int | No procesados (sin tax_id, error al escribir, etc.) |
| details | array | Lista de entradas por carrier (ver abajo) |
| message | string | Mensaje opcional (ej. error global, "No hay carriers que procesar") |
| **ruts_no_encontrados_en_rt_carrier** | **array de string** | **Solo cuando el request incluyó `rut_list`.** RUTs (en formato normalizado, ej. `12345678-9`) que el cliente envió en `rut_list` pero que **no tienen documento en RT_carrier**. Permite saber de inmediato qué RUTs no se procesarán. Si no se usó `rut_list` o todos existían, es `[]`. |

Cada elemento de **details**:

| Campo | Descripción |
|-------|-------------|
| carrier_id | ObjectId del carrier (como string) |
| tax_id | RUT del carrier |
| status | `updated`, `not_found_sii`, `sii_failed`, `not_processed`, `error` |
| error_message | Mensaje si hubo error |
| activities_count | Cantidad de actividades escritas (si status updated) |

---

## 3. Flujo de proceso

1. **Cliente** llama a `POST /api/v1/carga-giros` con body:
   - `run_type`: `"initial_load"` o `"periodic_update"`
   - `rut_list`: (opcional) lista de RUTs a procesar; si no se envía, se procesan todos los carriers (o los indicados en `carrier_ids`).
   - `carrier_ids`: (opcional) lista de `_id` de RT_carrier a procesar.

2. **API (Cloud Run)**:
   - Resuelve la lista de carriers (todos o filtrados por `rut_list` / `carrier_ids`).
   - Genera un `job_id` (UUID) y crea un documento en `carrier_giros_sync_log` con status `running`.
   - Devuelve de inmediato el `job_id` y lanza el trabajo en **background**.

3. **Background**:
   - Para cada carrier: obtiene `tax_id` (o `legal_tax_id`), llama a la **VM** con `POST /api/v1/sii/giros` y body `{"rut": "<tax_id>"}`.
   - La **VM** ejecuta el scraping al SII (Selenium) y devuelve la lista de actividades.
   - **Solo si la consulta fue exitosa y hay actividades**: la API escribe el objeto `giros_sync` en `RT_carrier` (reemplazando toda la lista `economicActivities`, actualizando `updated_giros_at` y manteniendo o setando `initial_sync_at`). Si falla, no se escribe nada en ese carrier.
   - Se anota en `details` del job el resultado (updated / not_found_sii / sii_failed / not_processed).
   - Al terminar, actualiza el documento del job en `carrier_giros_sync_log` (status, contadores, finished_at, details).

4. **Cliente** puede consultar:
   - `GET /api/v1/carga-giros/{job_id}`: resumen del job (status, totales, `ruts_no_encontrados_en_rt_carrier`).
   - `GET /api/v1/carga-giros/{job_id}/detalle`: documento completo del job incluyendo `details` y `ruts_no_encontrados_en_rt_carrier`.
   - `GET /api/v1/carga-giros`: listado de los últimos jobs (opcional filtro `run_type`).

**Respuestas según el caso:** Si el request incluye `rut_list`, la respuesta inmediata del POST y el documento del job incluyen el campo `ruts_no_encontrados_en_rt_carrier` con los RUTs (normalizados) que no tienen documento en RT_carrier. Así el consumidor sabe de inmediato cuántos carriers se procesarán (`total_carriers`) y cuáles RUTs de su lista no estaban en la base. Estructura detallada de las respuestas (POST, GET estado, GET detalle) en [Cómo llamar al servicio](COMO_LLAMAR_SERVICIO.md#2-respuestas-de-la-api-qué-devuelve-en-cada-caso).

---

## 4. VM - API de scraping SII

- **Responsabilidad**: recibir un RUT, abrir el portal SII (con Selenium/Chrome), rellenar el formulario, extraer la tabla de actividades económicas y devolverlas en JSON.
- **Endpoint**: `POST /api/v1/sii/giros` con body `{"rut": "12.345.678-9"}`.
- **Respuesta** (ejemplo):
  ```json
  {
    "rut": "12345678-9",
    "activities": [
      {
        "code": "492300",
        "description": "TRANSPORTE DE CARGA POR CARRETERA",
        "category": "Primera",
        "isVatSubject": true,
        "fecha": "30-09-2003",
        "startDate": "2003-09-30T00:00:00",
        "lastUpdatedAt": "..."
      }
    ],
    "not_found": false,
    "error": null,
    "success": true
  }
  ```
- **Despliegue**: servicio systemd en la VM (`carrier-sii-scraper.service` en 8080). Variables de entorno en la VM: opcionalmente `OXY_USER`, `OXY_PASS`, `OXY_HOST`, `OXY_PORT` para proxy Oxylabs.

### 4.1 Liberar espacio en disco (VM)

Con carga inicial de 1000 RUTs, actualizaciones periódicas y consultas individuales, Chrome/Selenium pueden llenar el disco. La API en la VM incluye:

1. **Por cada request**: Chrome usa un directorio temporal propio (`/tmp/carriersync_scraper/chrome_xxx`). Al terminar la petición (tras `driver.quit()`), ese directorio se **borra siempre**, así no se acumulan datos entre llamadas.
2. **Opciones de Chrome**: `--user-data-dir` en ese temp, `--disk-cache-size=0`, `--disable-application-cache` para reducir uso de disco.
3. **Limpieza periódica**: cada N requests (por defecto 50) se ejecuta una limpieza de directorios de sesión **viejos** (por si un run crasheó sin borrar su directorio). Se eliminan los que tengan más de 15 minutos (configurable).
4. **Al arranque**: al iniciar la API se borran sesiones antiguas que hayan quedado de ejecuciones anteriores.
5. **Limpieza manual**: `POST /api/v1/cleanup` en la VM fuerza la eliminación de sesiones antiguas (útil si el disco se llenó).

Variables de entorno **en la VM** (opcionales):

| Variable | Descripción | Por defecto |
|----------|-------------|-------------|
| VM_TEMP_BASE_DIR | Directorio base para temporales de Chrome | `/tmp/carriersync_scraper` |
| VM_CLEANUP_MAX_AGE_MINUTES | Borrar sesiones más viejas que N minutos | `15` |
| VM_CLEANUP_EVERY_N_REQUESTS | Ejecutar limpieza de residuos cada N requests | `50` |

Recomendación: dejar los valores por defecto. Si el disco es muy justo, puedes bajar `VM_CLEANUP_EVERY_N_REQUESTS` (ej. 20) para limpiar más seguido.

---

## 5. Variables de entorno (API en Cloud Run)

| Variable | Descripción |
|----------|-------------|
| MONGODB_URL | Cadena de conexión MongoDB |
| MONGODB_DATABASE | Nombre de la base (ej. Samanta) |
| VM_SII_SCRAPER_URL | URL base de la API en la VM (ej. http://34.x.x.x:8080) |
| ENVIRONMENT | dev | prod |
| LOG_LEVEL | DEBUG | INFO |

---

## 6. Estructura del proyecto

```
carrierSync/
├── main.py                 # FastAPI, Cloud Run / Cloud Functions
├── requirements.txt        # Dependencias API
├── requirements_vm.txt     # Dependencias VM (Selenium, etc.)
├── Dockerfile              # Imagen API (sin navegador)
├── docker-compose.yml      # Desarrollo local
├── database/               # Conexión MongoDB, init, nombres de colecciones
├── models/                 # Pydantic (EconomicActivity, CargaGirosRequest/Response, etc.)
├── routes/                 # health, carrier_giros (carga-giros, estado, detalle, listado)
├── services/               # carrier_giros_service, sync_log_service, sii_vm_client
├── utils/                  # logging, rut_chileno
├── vm_services/           # API del scraper SII para VM (sii_scraper_api.py)
├── tools/                  # deploy_por_ambiente.ps1, deploy_cloud_run.ps1, *.bat
├── scripts/                # setup-vm.sh, deploy-dev.sh, deploy-prod.sh
├── scripts_vm/             # systemd (carrier-sii-scraper.service, -dev)
├── .github/workflows/      # deploy-dev.yml, deploy-prod.yml
└── documentacion/          # GUIA_AMBIENTES_DEV_PROD.md, DOCUMENTACION_TECNICA_GIROS.md
```

---

## 7. Diferenciación carga inicial vs actualización periódica

- **run_type** en el request y en `carrier_giros_sync_log`: `initial_load` o `periodic_update`.
- La lógica de procesamiento es la misma; la diferencia es solo de trazabilidad y reportes (filtrar jobs por `run_type` en `GET /api/v1/carga-giros?run_type=periodic_update`).

---

## 8. Escalabilidad y límites

- La carga se ejecuta en un único worker en background (ThreadPoolExecutor con 2 workers). Para miles de carriers se puede:
  - Partir en lotes (varias llamadas a `POST /api/v1/carga-giros` con `carrier_ids` o `rut_list` por lote).
  - En el futuro, usar Cloud Tasks o un job en Cloud Run con concurrencia controlada.
- La VM debe poder atender varias peticiones secuenciales (o implementar cola en la VM si se desea paralelismo controlado sin saturar el SII).
