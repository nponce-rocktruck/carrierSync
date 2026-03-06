# Cómo llamar al servicio CarrierSync (carga de giros)

La API expone un único endpoint para iniciar la carga/actualización de giros: **POST /api/v1/carga-giros**. El trabajo se ejecuta en segundo plano; puedes consultar el estado con **GET /api/v1/carga-giros/{job_id}**.

**Base URL:**
- Local: `http://localhost:8000`
- Cloud Run dev: `https://carriersync-dev-XXXX.run.app` (la que te dé el despliegue)
- Cloud Run prod: `https://carriersync-prod-XXXX.run.app`

---

## 1. Cuerpo del request (POST /api/v1/carga-giros)

| Campo          | Tipo   | Obligatorio | Descripción |
|----------------|--------|-------------|-------------|
| `run_type`     | string | Sí          | `"initial_load"` (carga inicial) o `"periodic_update"` (actualización periódica). Solo afecta al tipo de job en el log. |
| `rut_list`     | array  | No          | Lista de RUTs (strings). Si se envía, **solo se procesan esos RUTs**. Ej: `["12345678-9", "98765432-1"]`. |
| `carrier_ids`  | array  | No          | Lista de **ObjectId** de la colección RT_carrier. Si se envía, **solo se procesan esos carriers**. Ej: `["507f1f77bcf86cd799439011"]`. |

**Reglas:**
- Si **no** envías `rut_list` ni `carrier_ids`: se procesan **todos** los transportistas que haya en RT_carrier (según la base de datos configurada: dev o prod).
- Si envías **rut_list**: solo se procesan los carriers cuyo RUT (`tax_id` o `legal_tax_id`) esté en esa lista. Los RUTs que envíes y **no** existan en RT_carrier se devuelven en la respuesta en `ruts_no_encontrados_en_rt_carrier` (ver más abajo).
- Si envías **carrier_ids**: solo se procesan los documentos de RT_carrier con ese `_id`.
- Si envías **ambos** `rut_list` y `carrier_ids`: se procesan los que cumplan cualquiera de los dos (unión).

**Formato de RUT:** puedes enviar con o sin puntos (ej. `12.345.678-9` o `12345678-9`). El servicio normaliza internamente; en las respuestas los RUTs “no encontrados” aparecen en formato normalizado (ej. `12345678-9`).

---

## 2. Respuestas de la API (qué devuelve en cada caso)

### 2.1 POST /api/v1/carga-giros – Respuesta inmediata

La API responde de inmediato con el `job_id` y un resumen. El trabajo se ejecuta en segundo plano.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `job_id` | string | UUID del job. Úsalo para consultar el estado. |
| `run_type` | string | `initial_load` o `periodic_update` (eco del request). |
| `status` | string | Siempre `"running"` en la respuesta del POST (el job sigue en background). |
| `started_at` | string (ISO) | Fecha/hora de inicio. |
| `finished_at` | null | Null hasta que el job termine (consultar con GET). |
| `total_carriers` | int | **Cantidad de carriers que se van a procesar** (los que sí están en RT_carrier). Si enviaste `rut_list` y alguno no está en la base, aquí verás solo los que sí existen. |
| `processed`, `updated`, `not_found_in_sii`, `sii_failed`, `not_processed` | int | En la respuesta del POST suelen ser 0; se actualizan cuando el job termina (GET). |
| `details` | array | Vacío en el POST; se llena al terminar el job. |
| `message` | string | Mensaje descriptivo. Si hay RUTs no encontrados en RT_carrier, los lista aquí. |
| **`ruts_no_encontrados_en_rt_carrier`** | **array de string** | **Solo cuando enviaste `rut_list`.** Lista de RUTs (normalizados) que estaban en tu lista pero **no tienen documento en RT_carrier**. Así sabes de inmediato cuáles no se procesarán. Si todos existen, es `[]`. |

**Ejemplo – Todos los RUTs están en RT_carrier (rut_list de 3, los 3 existen):**
```json
{
  "job_id": "97410906-4092-4de6-8882-e50af0a54e74",
  "run_type": "initial_load",
  "status": "running",
  "started_at": "2026-03-06T15:40:56.548593",
  "finished_at": null,
  "total_carriers": 3,
  "processed": 0,
  "updated": 0,
  "not_found_in_sii": 0,
  "sii_failed": 0,
  "not_processed": 0,
  "details": [],
  "message": "Job iniciado. Total carriers a procesar: 3. Consulta GET /api/v1/carga-giros/97410906-4092-4de6-8882-e50af0a54e74 para el estado.",
  "ruts_no_encontrados_en_rt_carrier": []
}
```

**Ejemplo – Un RUT no está en RT_carrier (rut_list de 3, solo 2 existen):**
```json
{
  "job_id": "97410906-4092-4de6-8882-e50af0a54e74",
  "run_type": "initial_load",
  "status": "running",
  "started_at": "2026-03-06T15:40:56.548593",
  "finished_at": null,
  "total_carriers": 2,
  "processed": 0,
  "updated": 0,
  "not_found_in_sii": 0,
  "sii_failed": 0,
  "not_processed": 0,
  "details": [],
  "message": "Job iniciado. Total carriers a procesar: 2. RUT(s) no encontrado(s) en RT_carrier: 12379117-1. Consulta GET /api/v1/carga-giros/97410906-4092-4de6-8882-e50af0a54e74 para el estado.",
  "ruts_no_encontrados_en_rt_carrier": ["12379117-1"]
}
```

**Ejemplo – Ninguno está en RT_carrier (rut_list de 2, 0 existen):**
```json
{
  "job_id": "a1b2c3d4-...",
  "run_type": "initial_load",
  "status": "running",
  "total_carriers": 0,
  "message": "Job iniciado. Total carriers a procesar: 0. RUT(s) no encontrado(s) en RT_carrier: 11217075-8, 17807161-0. Consulta GET ...",
  "ruts_no_encontrados_en_rt_carrier": ["11217075-8", "17807161-0"]
}
```

### 2.2 GET /api/v1/carga-giros/{job_id} – Estado del job

Devuelve el estado actual del job (resumen). Cuando el job termina, `status` pasa a `completed`, `partial` o `failed` y se rellenan los contadores y `finished_at`.

| Campo | Descripción |
|-------|-------------|
| `job_id`, `run_type`, `status`, `started_at`, `finished_at` | Igual que en el POST; `finished_at` se rellena al terminar. |
| `total_carriers`, `processed`, `updated`, `not_found_in_sii`, `sii_failed`, `not_processed` | Contadores del resultado. |
| `details_count` | Cantidad de entradas en `details` (una por carrier procesado o con error). |
| **`ruts_no_encontrados_en_rt_carrier`** | Misma lista que en el POST: RUTs que enviaste en `rut_list` y no están en RT_carrier (formato normalizado). Vacío si no usaste `rut_list` o si todos existen. |

### 2.3 GET /api/v1/carga-giros/{job_id}/detalle – Detalle completo

Devuelve el documento completo del job tal como está en MongoDB (`carrier_giros_sync_log`): mismo contenido que el GET de estado más el array `details` con el resultado por cada carrier (carrier_id, tax_id, status, error_message, activities_count, etc.) y el campo `ruts_no_encontrados_en_rt_carrier`.

---

## 3. Ejemplos de uso

### 3.1 Ejecutar todos los transportistas

No envíes `rut_list` ni `carrier_ids`.

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/carga-giros" \
  -H "Content-Type: application/json" \
  -d "{\"run_type\": \"initial_load\"}"
```

**Body (JSON):**
```json
{
  "run_type": "initial_load"
}
```

**Respuesta (ejemplo):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "run_type": "initial_load",
  "status": "running",
  "started_at": "2025-03-05T12:00:00",
  "total_carriers": 150,
  "message": "Job iniciado. Total carriers a procesar: 150. Consulta GET /api/v1/carga-giros/{job_id} para el estado."
}
```

---

### 3.2 Solo una lista de RUTs (por tax id)

Envía `rut_list` con los RUTs que quieras actualizar.

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/carga-giros" \
  -H "Content-Type: application/json" \
  -d "{\"run_type\": \"initial_load\", \"rut_list\": [\"12345678-9\", \"98765432-1\"]}"
```

**Body (JSON):**
```json
{
  "run_type": "initial_load",
  "rut_list": ["12345678-9", "98765432-1", "11222333-4"]
}
```

Solo se procesarán los carriers cuyo RUT (`tax_id` o `legal_tax_id`) esté en RT_carrier. Los RUTs que envíes y no existan en la base se devuelven en la respuesta en `ruts_no_encontrados_en_rt_carrier` y en el `message` (ver sección 2).

---

### 3.3 Solo por IDs de carrier (ObjectId de MongoDB)

Envía `carrier_ids` con los `_id` de los documentos en RT_carrier.

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/carga-giros" \
  -H "Content-Type: application/json" \
  -d "{\"run_type\": \"periodic_update\", \"carrier_ids\": [\"507f1f77bcf86cd799439011\", \"507f191e810c19729de860ea\"]}"
```

**Body (JSON):**
```json
{
  "run_type": "periodic_update",
  "carrier_ids": ["507f1f77bcf86cd799439011", "507f191e810c19729de860ea"]
}
```

Útil cuando ya conoces los `_id` de RT_carrier (por ejemplo desde otra consulta o desde tu aplicación).

---

### 3.4 Un solo RUT (prueba rápida)

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/carga-giros" \
  -H "Content-Type: application/json" \
  -d "{\"run_type\": \"initial_load\", \"rut_list\": [\"12345678-9\"]}"
```

**Body (JSON):**
```json
{
  "run_type": "initial_load",
  "rut_list": ["12345678-9"]
}
```

---

## 4. Consultar el estado del job

Con el `job_id` que devuelve el POST:

**Estado resumido:**
```bash
curl "http://localhost:8000/api/v1/carga-giros/{job_id}"
```

**Detalle completo (incluye resultado por cada carrier):**
```bash
curl "http://localhost:8000/api/v1/carga-giros/{job_id}/detalle"
```

**Listar últimos jobs:**
```bash
curl "http://localhost:8000/api/v1/carga-giros?limit=10"
# Opcional: filtrar por tipo
curl "http://localhost:8000/api/v1/carga-giros?limit=10&run_type=initial_load"
```

---

## 5. Resumen rápido

| Quiero procesar…        | Body (además de run_type)     |
|-------------------------|--------------------------------|
| Todos los transportistas | No agregues rut_list ni carrier_ids |
| Una lista de RUTs       | `"rut_list": ["12.345.678-9", "98.765.432-1"]` |
| Por ID de carrier (MongoDB) | `"carrier_ids": ["507f1f77bcf86cd799439011"]` |
| Un solo RUT (prueba)    | `"rut_list": ["12345678-9"]`   |

Formato de RUT: puedes enviar con o sin puntos (el servicio normaliza); por ejemplo `12345678-9` o `12.345.678-9`.
