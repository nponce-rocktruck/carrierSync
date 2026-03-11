# CarrierSync – VM (todo en uno): 34.176.102.209, puerto 8082

Un solo documento para la **máquina virtual** del scraper SII. La forma recomendada es **usar el script**; el resto son comandos útiles, actualizaciones y una opción manual por si la necesitas.

**VM:** misma que gestion_documental. **Puerto:** 8082 (8080/8081 son de gestion_documental).

---

## 1. Qué necesitas antes

- **PC con Windows** y **gcloud** instalado (`gcloud --version`). Si usas la VM para gestion_documental, ya lo tienes.
- **Nombre y zona de la VM** (ej. `mv-2-southamerica`, `southamerica-west1-b`). Lo ves en Google Cloud → Compute Engine → Instancias.
- **No hace falta** tener CarrierSync desplegado en Cloud Run ni el proyecto “cargado” en Cloud antes: la VM y el firewall son independientes. Puedes configurar primero la VM y después desplegar la API en Cloud Run (o al revés).

---

## 2. Instalación con script (recomendado)

Sigue los pasos en orden. Casi todo lo hace el script; tú solo ejecutas un comando en la PC y luego dos en la VM.

### 2.1 En la PC – Abrir el puerto 8082

En **PowerShell** o **CMD** (puedes estar en cualquier carpeta; no hace falta entrar a `C:\...\carrierSync`):

```powershell
gcloud compute firewall-rules create allow-carriersync-sii-8082 --allow tcp:8082 --source-ranges 0.0.0.0/0 --description "CarrierSync scraper SII puerto 8082"
```

Si pregunta *"Would you like to enable [compute.googleapis.com] and retry?"* responde **y** y Enter (en proyectos nuevos la API de Compute no suele estar activada; tarda un minuto).

Si la VM está en otro proyecto:

```powershell
gcloud compute firewall-rules create allow-carriersync-sii-8082 --project=gestiondocumental-473815 --allow tcp:8082 --source-ranges 0.0.0.0/0 --description "CarrierSync scraper SII puerto 8082"
```

Si dice que la regla ya existe, sigue al siguiente paso.

---

### 2.2 En la PC – Conectarte a la VM

```powershell
gcloud compute ssh mv-2-southamerica --zone=southamerica-west1-b --project=gestiondocumental-473815
```


Cuando veas algo como `pc@mv-2-southamerica:~$` ya estás **dentro de la VM**. Los siguientes comandos son en la VM.

---

### 2.3 En la VM – Chromium (solo si no está)

Comprobar:

```bash
which chromium-browser || which chromium || which google-chrome
```

Si no sale ninguna ruta, instalar:

```bash
sudo apt-get update
sudo apt-get install -y chromium-browser
```

---

### 2.4 En la VM – Clonar el repo y entrar
gcloud compute ssh mv-2-southamerica --zone=southamerica-west1-b --project=gestiondocumental-473815


```bash
cd /home/pc
```


Si **ya** tienes `carrierSync`:

```bash
cd carrierSync
git pull
```

---
cd ~/carrierSync

git pull
./venv/bin/pip install -r requirements_vm.txt -q
sudo systemctl restart carrier-sii-scraper
curl -s http://localhost:8082/health


nano /home/pc/carrierSync/env.proxy
control 0 enter control x

sudo journalctl -u carrier-sii-scraper -n 80 --no-pager



Acción	Comando
Ver estado	sudo systemctl status carrier-sii-scraper
Reiniciar	sudo systemctl restart carrier-sii-scraper
Ver logs en vivo	sudo journalctl -u carrier-sii-scraper -f
Parar / arrancar	sudo systemctl stop carrier-sii-scraper / sudo systemctl start carrier-sii-scraper

--- 

### 2.5 En la VM – Ejecutar el script (instala todo)

```bash
chmod +x scripts/setup-vm-shared.sh
./scripts/setup-vm-shared.sh
```

El script: crea el venv, instala dependencias, instala el servicio systemd en el puerto 8082 y lo deja activo. Si pide contraseña de `pc`, la escribes.

Al terminar bien verás “Listo” y la URL. Si falla, lee el mensaje (por ejemplo falta Python 3.11 o Chromium).

---

### 2.6 Comprobar que responde

**En la VM** (misma sesión SSH):

```bash
curl -s http://localhost:8082/health
```

Deberías ver algo como: `{"status":"healthy","service":"sii-scraper-vm","selenium":true}`.

**Desde la PC** (otra ventana de PowerShell, sin SSH):

```powershell
curl http://34.176.102.209:8082/health
```

Si responde igual, el scraper y el firewall están bien.

---

### 2.7 En la PC – Poner la URL en los env

En el proyecto CarrierSync (ej. `C:\Users\pc\Documents\GitHub\carrierSync`), edita **env.dev.yaml** y **env.prod.yaml** y deja en ambos:

```yaml
VM_SII_SCRAPER_URL: "http://34.176.102.209:8082"
```

Guarda los dos archivos.

---

### 2.8 Variables de entorno en la VM (proxy + CapSolver)

El scraper SII **siempre usa proxy residencial** cuando está configurado. Las variables se cargan desde un archivo en la VM; no van en el repo.

**Dónde ponerlas:** en la VM, archivo `/home/pc/carrierSync/env.proxy` (el servicio systemd ya tiene `EnvironmentFile=/home/pc/carrierSync/env.proxy`).

**Variables obligatorias (proxy residencial, ej. DataImpulse u otro):**

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `PROXY_HOST` | Host del proxy | `gw.dataimpulse.com` |
| `PROXY_PORT` | Puerto | `823` |
| `PROXY_USER` | Usuario (o `PROXY_USERNAME`) | `tu_usuario` |
| `PROXY_PASSWORD` | Contraseña (o `PROXY_PASS`) | `tu_password` |

**Para usar CapSolver (recomendado; evita Chrome y timeouts):**

| Variable | Descripción |
|----------|-------------|
| `CAPSOLVER_API_KEY` | API key de [CapSolver](https://dashboard.capsolver.com/) |

**Opcionales:** `PROXY_VERIFY_SSL=true` (por defecto), `PROXY_CA_BUNDLE=/ruta/certificado.crt` si el proxy exige un CA custom, `SCRIPT_TIMEOUT_SEC=120`, `SII_RECAPTCHA_SITEKEY`, `SII_RECAPTCHA_PAGE_ACTION=consultaSTC`.

**Cómo ponerlas en la VM:**

1. Conéctate por SSH (ver 2.2).
2. Edita el archivo (si no existe, créalo):
   ```bash
   nano /home/pc/carrierSync/env.proxy
   ```
3. Escribe una variable por línea, sin espacios alrededor del `=`:
   ```ini
   PROXY_HOST=gw.dataimpulse.com
   PROXY_PORT=823
   PROXY_USER=tu_usuario
   PROXY_PASSWORD=tu_contraseña
   CAPSOLVER_API_KEY=CAP-tu_api_key
   ```
4. Guardar: **Ctrl+O**, Enter, **Ctrl+X**.
5. Reiniciar el servicio para que cargue las variables:
   ```bash
   sudo systemctl restart carrier-sii-scraper
   ```
6. Comprobar: `curl -s http://localhost:8082/health` (debe mostrar `"proxy_configured": true` si el proxy está bien configurado).

**Si editaste env.proxy en Windows:** puede quedar con saltos de línea CRLF y dar 401. En la VM ejecuta:
   ```bash
   sed -i 's/\r$//' /home/pc/carrierSync/env.proxy
   sudo systemctl restart carrier-sii-scraper
   ```

---

## 3. Resumen rápido (solo comandos)

| Dónde | Qué hacer |
|-------|-----------|
| **PC** | `gcloud compute firewall-rules create allow-carriersync-sii-8082 --allow tcp:8082 --source-ranges 0.0.0.0/0` |
| **PC** | `gcloud compute ssh mv-2-southamerica --zone=southamerica-west1-b` |
| **VM** | `which chromium-browser \|\| which chromium` → si no hay: `sudo apt-get update && sudo apt-get install -y chromium-browser` |
| **VM** | `cd /home/pc` → si no hay repo: `git clone https://github.com/TU_USUARIO/carrierSync.git` → `cd carrierSync` (si ya hay: `cd carrierSync` y `git pull`) |
| **VM** | `chmod +x scripts/setup-vm-shared.sh` → `./scripts/setup-vm-shared.sh` |
| **VM** | `curl -s http://localhost:8082/health` |
| **PC** (otra ventana) | `curl http://34.176.102.209:8082/health` |
| **PC** (editor) | En `env.dev.yaml` y `env.prod.yaml`: `VM_SII_SCRAPER_URL: "http://34.176.102.209:8082"` |

---

## 4. URLs en la VM 34.176.102.209

| Servicio            | Proyecto           | Puerto | URL |
|---------------------|--------------------|--------|-----|
| Verificación DT/F30 | gestion_documental | 8080   | http://34.176.102.209:8080 |
| Verificación dev    | gestion_documental | 8081   | http://34.176.102.209:8081 |
| **Scraper SII**     | **CarrierSync**    | **8082** | **http://34.176.102.209:8082** |

---

## 5. Comandos útiles (en la VM)

```bash
# Estado del servicio
sudo systemctl status carrier-sii-scraper

# Ver logs en tiempo real (recomendado para depurar)
sudo journalctl -u carrier-sii-scraper -f

# Ver últimas 100 líneas
sudo journalctl -u carrier-sii-scraper -n 100

# Reiniciar (después de actualizar código)
sudo systemctl restart carrier-sii-scraper

# Detener / iniciar
sudo systemctl stop carrier-sii-scraper
sudo systemctl start carrier-sii-scraper
```

### Ver logs para depurar “no encontrado en SII”

Si los RUTs salen como *not_found_sii* o *Sin actividades en respuesta SII*, en la VM puedes seguir qué hace el scraper:

1. Conéctate por SSH y abre los logs en vivo:
   ```bash
   sudo journalctl -u carrier-sii-scraper -f
   ```
2. Desde otra ventana (o desde tu PC) lanza una carga de giros para el RUT que falla.
3. En los logs verás líneas con prefijo `[SII]`:
   - `[SII] POST /giros recibido RUT=...` — RUT que llegó al endpoint.
   - `[SII] Inicio extracción RUT normalizado=..., enviando al formulario=...` — Formato enviado al input del SII (debe ser tipo 17.807.161-0).
   - `[SII] RUT escrito en input` — Confirmación de que se escribió en el campo.
   - `[SII] Click en Consultar Situación Tributaria` — Se hizo click en consultar.
   - `[SII] No se encontró botón open-btn` — La página no mostró el botón de actividades (RUT sin datos o página distinta).
   - `[SII] Tabla DataTables_Table_0 visible, filas encontradas: N` — Cuántas filas se leyeron.
   - `[SII] RUT ... resultado: success=..., activities=N` — Resumen final.

Si aparece *No se encontró botón open-btn*: el SII no está mostrando actividades para ese RUT (o la página tardó más de 30 s en renderizar). Si aparece *filas encontradas: 0*: la tabla está vacía. Si hay filas pero *activities=0*: la estructura de columnas puede haber cambiado (revisar selectores en `vm_services/sii_scraper_api.py`).

**Revisar qué devolvió el SII cuando no hay botón:** en la VM, tras una consulta que haya guardado debug:
```bash
grep -iE 'open-btn|DataTables|actividad|sin actividad|Situación' /tmp/carriersync_scraper/debug/sii_no_open_btn.html | head -30
```
Así ves si en el HTML hay tabla, botón con otro nombre o mensaje "sin actividades".

---

## 6. Actualizar código en la VM

Cuando cambies algo en el repo CarrierSync (por ejemplo `vm_services/sii_scraper_api.py`):

```bash
cd ~/carrierSync
git pull
./venv/bin/pip install -r requirements_vm.txt -q
sudo systemctl restart carrier-sii-scraper
```
nano /home/pc/carrierSync/env.proxy
Comprobar: `curl -s http://localhost:8082/health`.

---

## 7. Solución de problemas

- **No me conecto por SSH:** Revisa `gcloud --version`, nombre de VM y zona (Compute Engine en la consola GCP), y que el proyecto esté bien elegido.
- **El script falla:** Estar en `~/carrierSync` y que existan `vm_services/sii_scraper_api.py` y `scripts/setup-vm-shared.sh`. Errores típicos: falta Python 3.11+ o Chromium (paso 2.3).
- **Desde la PC “connection refused” al 8082:** Comprueba el firewall (paso 2.1) y en la VM: `sudo systemctl status carrier-sii-scraper` (debe decir “active (running)”).
- **En /health sale "selenium": false:** Chromium no está bien instalado o no se instalaron las dependencias del venv; repite el paso de Chromium y `./venv/bin/pip install -r requirements_vm.txt`.
- **Disco lleno en la VM:** El scraper limpia temporales; además puedes llamar a `POST http://34.176.102.209:8082/api/v1/cleanup` para forzar limpieza.
- **El SII bloquea o no devuelve datos:** Configura proxy residencial (variables PROXY_* en `env.proxy`); ver sección **2.8** y **7.1**. Si el SII responde con **"usuario no autorizado por ReCaptcha"**, ver sección 7.2.
- **Proxy 401 Unauthorized:** Suele ser **CRLF** en `env.proxy` si lo editaste en Windows. En la VM: `sed -i 's/\r$//' ~/carrierSync/env.proxy` y `sudo systemctl restart carrier-sii-scraper`. O reescribe las variables con `nano ~/carrierSync/env.proxy` (Ctrl+O, Enter, Ctrl+X).

---

## 7.2 Mensaje «usuario no autorizado por ReCaptcha»

Si en los logs o en la respuesta del API aparece que el SII rechazó la consulta por **ReCaptcha**, significa que el portal del SII ha detectado el acceso automatizado (Chrome headless y/o proxy) y no muestra resultados; en su lugar muestra un mensaje de error y un botón "Volver".

**Causa:** El SII usa reCAPTCHA para validar que la consulta la hace un humano. En entornos headless o con ciertos proxies, la validación falla.

**Qué hace el scraper:** Detecta ese mensaje y devuelve `success: false` con `error` indicando "usuario no autorizado por ReCaptcha", para que no se confunda con "RUT sin actividades".

**Opciones posibles (avanzado):**

1. **CapSolver (recomendado):** Con proxy residencial configurado (PROXY_*), el scraper usa CapSolver con el mismo proxy para que el token y la petición al SII salgan por la misma IP. Configura `CAPSOLVER_API_KEY` en `env.proxy`; ver sección **7.2**.
2. **Consultas manuales / API oficial:** Si el SII ofrece una API o proceso manual para obtener actividades económicas, usarla como alternativa.

Para confirmar que es reCAPTCHA, en la VM puedes revisar el HTML guardado:
`grep -i recaptcha /tmp/carriersync_scraper/debug/sii_no_open_btn.html`

**Configuración actual del scraper SII:** Se usa **proxy residencial genérico** (variables PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASSWORD), compatible con cualquier proveedor (DataImpulse, etc.). Con **CapSolver** el token de reCAPTCHA v3 Enterprise se obtiene usando el mismo proxy, de modo que la IP al resolver el captcha y al llamar al API del SII coinciden (evita `captchaInvalido`). El flujo es: GET a la página del SII por proxy (para cookies) y POST a getConsultaData con la misma sesión. No hay opción para desactivar el proxy: si las variables están definidas, se usa; si no, las consultas van sin proxy (el SII puede bloquear la IP).

---

## 7.1 Configurar proxy residencial (genérico)

El scraper usa **variables genéricas** (cualquier proveedor: DataImpulse, Oxylabs, etc.). Sin proxy configurado, el SII suele bloquear la IP de la VM.

**Dónde configurar:** archivo `/home/pc/carrierSync/env.proxy` en la VM (el servicio ya carga ese archivo con `EnvironmentFile=`).

**Variables necesarias:**

```ini
PROXY_HOST=gw.dataimpulse.com
PROXY_PORT=823
PROXY_USER=tu_usuario
PROXY_PASSWORD=tu_contraseña
```

(Sustituye por el host/puerto/usuario/contraseña de tu proveedor de proxy residencial, por ejemplo Chile para el SII.)

**Pasos:**

1. En la VM: `nano /home/pc/carrierSync/env.proxy`
2. Añade o edita las cuatro variables (una por línea, sin espacios alrededor del `=`).
3. Guarda (Ctrl+O, Enter, Ctrl+X).
4. Reinicia el servicio: `sudo systemctl restart carrier-sii-scraper`.
5. Comprueba en logs: `sudo journalctl -u carrier-sii-scraper -n 20 --no-pager` — debe aparecer algo como `[SII] Proxy residencial configurado (UC): host:puerto`.

Para cambiar credenciales en el futuro, solo editas `env.proxy` y reinicias; no hace falta tocar el .service.

### Uso estimado de proxy (MB) – SII vs DT

Mismo patrón que la API de verificación DT: proxy residencial y estimación de MB para control de costes.

| Servicio | reCAPTCHA | Proveedor captcha | Uso aprox. proxy por operación |
|----------|-----------|-------------------|---------------------------------|
| **DT** (verificación F30) | v2 | 2captcha | ~0,5–1 MB (página + captcha + descarga PDF) |
| **SII** (giros por RUT)   | v3 Enterprise | CapSolver (con mismo proxy) | ~0,02 MB (GET sesión + POST getConsultaData) |

- Cada respuesta de `POST /api/v1/sii/giros` incluye `proxy_usage` con `proxy_server` y `estimated_mb` cuando hay proxy configurado.
- Total acumulado: `GET /api/v1/proxy-stats` devuelve `requests_count` y `total_estimated_mb`.
- Ajuste: variable de entorno `SII_ESTIMATED_MB_PER_REQUEST` (por defecto `0.02`).

---


## 7.2 CapSolver (reCAPTCHA v3 Enterprise) – recomendado

Con **CapSolver** el scraper obtiene los tokens de reCAPTCHA vía API y **no inicia Chrome** (evita timeouts y uso de memoria). El token se resuelve usando **el mismo proxy** (PROXY_*) que la petición al SII, para que la IP coincida y el SII no devuelva `captchaInvalido`.

1. Crea cuenta y obtén tu API key en [CapSolver](https://dashboard.capsolver.com/).
2. En `/home/pc/carrierSync/env.proxy` añade (junto a PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASSWORD):
   ```ini
   CAPSOLVER_API_KEY=CAP-tu_api_key_aqui
   ```
3. Reinicia: `sudo systemctl restart carrier-sii-scraper`. En logs: `[SII] CapSolver configurado: tokens vía API (sin navegador)`.

En cada consulta se pide un token a CapSolver (ReCaptchaV3EnterpriseTask con tu proxy) y se hace GET a la página SII + POST a getConsultaData con la misma sesión/proxy. No hace falta 2Captcha ni el navegador.

---

## 7.3 reCAPTCHA: token del navegador (sin CapSolver)

**Por defecto el scraper no usa 2Captcha.** Solo intenta obtener el token desde el mismo navegador (`grecaptcha.enterprise.execute()` en la página del SII). Si Google acepta ese token, se llama a la API del SII y se devuelven los giros. Si no, se hace click en "Consultar Situación Tributaria" (en headless/proxy el SII suele mostrar "usuario no autorizado por ReCaptcha").

**Opcional – activar 2Captcha:** Define `SII_USE_2CAPTCHA=true` y `API_KEY_2CAPTCHA` en el servicio para usar 2Captcha cuando falle el token del navegador.

**Sitekey:** El código usa un sitekey por defecto del SII; si hace falta otro, define `SII_RECAPTCHA_SITEKEY`.

**Si el SII sigue mostrando "usuario no autorizado por ReCaptcha"** tras inyectar el token: (1) Pruebe otro `pageAction`: en el servicio defina `SII_RECAPTCHA_PAGE_ACTION=submit` (o el valor que use el SII; puede inspeccionar la pestaña Red del navegador). (2) El backend del SII puede validar el token de forma estricta (ventana de validez, fingerprint); 2Captcha con reCAPTCHA v3 no permite usar el mismo proxy que el navegador, así que no se puede “resolver desde la misma IP”. Mantener el proxy es necesario para no ser bloqueado por IP tras varias solicitudes.

**Si el SII sigue mostrando "usuario no autorizado por ReCaptcha"** tras inyectar el token: (1) Pruebe otro `pageAction`: en el servicio defina `SII_RECAPTCHA_PAGE_ACTION=submit` (o el valor que use el SII; puede inspeccionar la pestaña Red del navegador). (2) El backend del SII puede validar el token de forma estricta (ventana de validez, fingerprint); 2Captcha con reCAPTCHA v3 no permite usar el mismo proxy que el navegador, así que no se puede "resolver desde la misma IP". Mantener el proxy es necesario para no ser bloqueado por IP tras varias solicitudes.

---

## 7.4 Si falla en todas las consultas (captchaInvalido)

Cuando **todas** las consultas devuelven `captchaInvalido=true`, el SII/Google están rechazando el token. Con la configuración actual (proxy + CapSolver con el mismo proxy), el token y la petición salen por la misma IP; si sigue fallando:

- **Comprobar variables:** que `env.proxy` tenga bien PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASSWORD y CAPSOLVER_API_KEY (sin espacios ni CRLF; en la VM `sed -i 's/\r$//' /home/pc/carrierSync/env.proxy` si editaste en Windows).
- **Proveedor de proxy:** debe ser residencial y, si es posible, IP de Chile para el SII.
- **CapSolver:** revisar en el dashboard que las tareas no fallen y que el tipo sea ReCaptchaV3EnterpriseTask con proxy.

Otras opciones: solicitar API o canal oficial al SII; o proceso manual/semiautomático para casos críticos.

---

## 8. Opción manual (sin script): crear el servicio con nano

Solo si no quieres o no puedes usar el script (por ejemplo ya tienes el repo y el venv y solo quieres instalar el servicio a mano).

**En la PC:** conéctate como en 2.2.

**En la VM:**

```bash
cd ~/carrierSync
sudo nano /etc/systemd/system/carrier-sii-scraper.service
```

Pega **todo** este contenido (ajusta la ruta si tu repo no está en `/home/pc/carrierSync`):

```ini
[Unit]
Description=CarrierSync VM - SII Giros Scraper (puerto 8082, VM compartida)
After=network.target

[Service]
Type=simple
User=pc
Group=pc
WorkingDirectory=/home/pc/carrierSync
Environment="PATH=/home/pc/carrierSync/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment=PORT=8082
EnvironmentFile=/home/pc/carrierSync/env.proxy
ExecStart=/home/pc/carrierSync/venv/bin/uvicorn vm_services.sii_scraper_api:app --host 0.0.0.0 --port 8082
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=carrier-sii-scraper

[Install]
WantedBy=multi-user.target
```

Crea también `env.proxy` con PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASSWORD y opcionalmente CAPSOLVER_API_KEY (ver 2.8).

Guardar: **Ctrl+O**, Enter, **Ctrl+X**.

Luego:

```bash
sudo systemctl daemon-reload
sudo systemctl enable carrier-sii-scraper.service
sudo systemctl start carrier-sii-scraper.service
sudo systemctl status carrier-sii-scraper.service
```

El firewall (paso 2.1) y la URL en `env.dev.yaml` / `env.prod.yaml` (paso 2.7) son los mismos.
