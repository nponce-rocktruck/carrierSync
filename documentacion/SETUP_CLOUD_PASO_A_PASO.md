# Guía paso a paso: Cloud (crear proyecto, desplegar CarrierSync)

Todo con **comandos** que puedes copiar y pegar. Desde crear el proyecto en GCP hasta tener la API en Cloud Run (dev y prod).

---

## Requisitos

- **PC con Windows** y el proyecto CarrierSync (ej. `C:\Users\pc\Documents\GitHub\carrierSync`).
- **Google Cloud SDK (gcloud)** instalado. Si no: https://cloud.google.com/sdk/docs/install

---

## 1. Crear proyecto en GCP (o usar uno existente)

**Abrir PowerShell o CMD** y ejecutar.

**Opción A – Crear proyecto nuevo:**

El **ID del proyecto** solo puede tener **minúsculas**, números y guiones (6–30 caracteres). No uses mayúsculas.

```powershell
# Ejemplo: ID en minúsculas (carriersync-7771, carriersync-prod, etc.)
gcloud projects create carriersync-7771 --name="CarrierSync"
gcloud config set project carriersync-7771
```

**Opción B – Usar proyecto existente** (mismo que gestion_documental u otro):

```powershell
gcloud config set project carriersync-7771
```

**Comprobar proyecto actual:**

```powershell
gcloud config get-value project
```

---

## 1.1 Vincular facturación al proyecto (obligatorio en proyectos nuevos)

Cloud Run, Cloud Build y Artifact Registry **requieren que el proyecto tenga una cuenta de facturación** asociada. Si al habilitar las APIs sale un error tipo *"Billing must be enabled"* o *"Billing account for project ... is not found"*, hay que vincular la facturación primero.

**Opción recomendada – Desde la consola (navegador):**

1. Entra en: https://console.cloud.google.com/billing
2. Arriba selecciona el **proyecto** (ej. carriersync-7771).
3. Si no tienes cuenta de facturación, créala (tarjeta; hay crédito gratuito para nuevos usuarios).
4. En **Facturación** → **Vincular un proyecto** (o **Administrar cuentas de facturación** → tu cuenta → **Vincular proyecto**), elige tu proyecto y asígnalo a la cuenta de facturación.

**Desde la línea de comandos** (si ya tienes un ID de cuenta de facturación):

```powershell
# Listar cuentas de facturación (copia el BILLING_ACCOUNT_ID, ej. 012345-ABCDEF-678901)
gcloud billing accounts list

# Vincular el proyecto actual a esa cuenta (sustituye BILLING_ACCOUNT_ID)
gcloud billing projects link NOMBRE_O_ID_DEL_PROYECTO --billing-account=BILLING_ACCOUNT_ID
```

Ejemplo: si tu proyecto es `carriersync-7771` y el ID de facturación es `012345-ABCDEF-678901`:

```powershell
gcloud billing projects link carriersync-7771 --billing-account=012345-ABCDEF-678901
```

Después de vincular, vuelve a ejecutar el paso 2 (habilitar APIs).

---

## 2. Habilitar APIs (solo una vez por proyecto)

```powershell
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```



---

## 3. Crear archivos de variables (env)

En la **raíz del proyecto CarrierSync** (donde está `main.py`) deben existir:

- **env.dev.yaml** (desarrollo)
- **env.prod.yaml** (producción)

**Contenido mínimo** (ajusta valores reales):

**env.dev.yaml:**

```yaml
MONGODB_URL: "mongodb+srv://usuario:password@cluster.mongodb.net/"
MONGODB_DATABASE: "Samanta_Dev"
ENVIRONMENT: "dev"
LOG_LEVEL: "DEBUG"
VM_SII_SCRAPER_URL: "http://34.176.102.209:8082"
```

**env.prod.yaml:**

```yaml
MONGODB_URL: "mongodb+srv://usuario:password@cluster.mongodb.net/"
MONGODB_DATABASE: "Samanta"
ENVIRONMENT: "prod"
LOG_LEVEL: "INFO"
VM_SII_SCRAPER_URL: "http://34.176.102.209:8082"
```

Crea o edita esos archivos en tu editor (no los subas a Git; ya están en `.gitignore`).

---

## 4. Ir a la carpeta del proyecto

```powershell
cd C:\Users\pc\Documents\GitHub\carrierSync
```


---

## 5. Desplegar a desarrollo (dev)

```powershell
.\tools\DESPLEGAR.bat dev
```

O directamente con PowerShell:

```powershell
.\tools\deploy_por_ambiente.ps1 -Ambiente dev
```

Esto usa **env.dev.yaml** y despliega el servicio **carriersync-dev** en Cloud Run.

---

## 6. Desplegar a producción (prod)

```powershell
.\tools\DESPLEGAR.bat prod
```

O:

```powershell
.\tools\deploy_por_ambiente.ps1 -Ambiente prod
```

Esto usa **env.prod.yaml** y despliega el servicio **carriersync** (o **carriersync-prod** según configuración).

---

## 7. Obtener la URL del servicio

**Desarrollo:**

```powershell
gcloud run services describe carriersync-dev --region us-central1 --format="value(status.url)"
```

**Producción:**

```powershell
gcloud run services describe carriersync --region us-central1 --format="value(status.url)"
```

*(Si tu servicio de prod se llama `carriersync-prod`, usa ese nombre.)*

---

## 8. Comprobar que responde

Sustituye `https://TU_URL` por la URL que te devolvió el comando anterior:

```powershell
curl https://TU_URL/health
```

O abre en el navegador: `https://TU_URL/docs`

---

## Resumen de comandos (copy-paste en orden)

**Primera vez (proyecto + APIs + env):**

```powershell
gcloud config set project TU_PROYECTO
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
cd C:\Users\pc\Documents\GitHub\carrierSync
# Crear/editar env.dev.yaml y env.prod.yaml (a mano en el editor)
```

**Desplegar dev:**

```powershell
cd C:\Users\pc\Documents\GitHub\carrierSync
.\tools\DESPLEGAR.bat dev
```

**Desplegar prod:**

```powershell
cd C:\Users\pc\Documents\GitHub\carrierSync
.\tools\DESPLEGAR.bat prod
```

**Ver URL dev:**

```powershell
gcloud run services describe carriersync-dev --region us-central1 --format="value(status.url)"
```

**Ver URL prod:**

```powershell
gcloud run services describe carriersync --region us-central1 --format="value(status.url)"
```

**Ver logs (dev):**

```powershell
gcloud run services logs tail carriersync-dev --region us-central1
```

**Ver logs (prod):**

```powershell
gcloud run services logs tail carriersync --region us-central1
```

---

## Dos proyectos GCP (dev y prod separados)

Si quieres un proyecto para desarrollo y otro para producción:

```powershell
# Proyecto dev
gcloud projects create carriersync-dev --name="CarrierSync Dev"
gcloud config set project carriersync-dev
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
cd C:\Users\pc\Documents\GitHub\carrierSync
.\tools\DESPLEGAR.bat dev

# Proyecto prod (cambiar proyecto y desplegar)
gcloud config set project carriersync-prod
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
.\tools\DESPLEGAR.bat prod
```

Antes de cada despliegue, asegúrate de que el proyecto activo es el correcto: `gcloud config get-value project`.
