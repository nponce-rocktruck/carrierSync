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

Comprobar: `curl -s http://localhost:8082/health`.

---

## 7. Solución de problemas

- **No me conecto por SSH:** Revisa `gcloud --version`, nombre de VM y zona (Compute Engine en la consola GCP), y que el proyecto esté bien elegido.
- **El script falla:** Estar en `~/carrierSync` y que existan `vm_services/sii_scraper_api.py` y `scripts/setup-vm-shared.sh`. Errores típicos: falta Python 3.11+ o Chromium (paso 2.3).
- **Desde la PC “connection refused” al 8082:** Comprueba el firewall (paso 2.1) y en la VM: `sudo systemctl status carrier-sii-scraper` (debe decir “active (running)”).
- **En /health sale "selenium": false:** Chromium no está bien instalado o no se instalaron las dependencias del venv; repite el paso de Chromium y `./venv/bin/pip install -r requirements_vm.txt`.
- **Disco lleno en la VM:** El scraper limpia temporales; además puedes llamar a `POST http://34.176.102.209:8082/api/v1/cleanup` para forzar limpieza.
- **El SII bloquea o no devuelve datos:** Configura proxy residencial (Oxylabs) como en gestion_documental; ver sección "Configurar proxy residencial" más abajo. Si el SII responde con **"usuario no autorizado por ReCaptcha"**, ver sección 7.2.

---

## 7.2 Mensaje «usuario no autorizado por ReCaptcha»

Si en los logs o en la respuesta del API aparece que el SII rechazó la consulta por **ReCaptcha**, significa que el portal del SII ha detectado el acceso automatizado (Chrome headless y/o proxy) y no muestra resultados; en su lugar muestra un mensaje de error y un botón "Volver".

**Causa:** El SII usa reCAPTCHA para validar que la consulta la hace un humano. En entornos headless o con ciertos proxies, la validación falla.

**Qué hace el scraper:** Detecta ese mensaje y devuelve `success: false` con `error` indicando "usuario no autorizado por ReCaptcha", para que no se confunda con "RUT sin actividades".

**Opciones posibles (avanzado):**

1. **Sin proxy (solo pruebas):** `SII_SCRAPER_USE_PROXY=false` puede reducir rechazos de reCAPTCHA en algunos entornos, pero **en producción no conviene**: el SII suele bloquear la IP tras pocas solicitudes. Mantener el proxy es necesario para uso continuado.
2. **2Captcha (integrado):** El scraper ya usa la misma API de 2Captcha que gestion_documental. Configura `API_KEY_2CAPTCHA` y, si hace falta, `SII_RECAPTCHA_SITEKEY`. Ver sección **7.3 Configurar 2Captcha**.
3. **Consultas manuales / API oficial:** Si el SII ofrece una API o proceso manual para obtener actividades económicas, usarla como alternativa.

Para confirmar que es reCAPTCHA, en la VM puedes revisar el HTML guardado:
`grep -i recaptcha /tmp/carriersync_scraper/debug/sii_no_open_btn.html`

---

## 7.1 Configurar proxy residencial (Oxylabs)

Si el SII bloquea la IP de la VM, usa el mismo proxy residencial que en gestion_documental.

**Opción A – Archivo de credenciales (recomendado, no sube secretos al repo)**

1. En la VM: `cd ~/carrierSync`, `cp env.proxy.example env.proxy`, `nano env.proxy` y rellena `OXY_USER` y `OXY_PASS`.
2. `sudo systemctl edit --full carrier-sii-scraper` y en `[Service]` añade una línea: `EnvironmentFile=/home/pc/carrierSync/env.proxy`
3. `sudo systemctl daemon-reload && sudo systemctl restart carrier-sii-scraper`

El archivo `env.proxy` no se sube al repo (está en .gitignore). Si reclonas, vuelve a crear `env.proxy` desde `env.proxy.example`.

**Opción B – Variables en systemd**

En `systemctl edit --full carrier-sii-scraper`, bajo `[Service]` añade:

```ini
Environment=OXY_USER=tu_usuario_oxylabs
Environment=OXY_PASS=tu_password_oxylabs
Environment=OXY_HOST=unblock.oxylabs.io
Environment=OXY_PORT=60000
```

Luego: `sudo systemctl daemon-reload && sudo systemctl restart carrier-sii-scraper`. En logs: `[SII] Proxy residencial configurado (extensión auth): ...`.

---

## 7.3 Configurar 2Captcha (reCAPTCHA)

El scraper usa la **misma API de 2Captcha** que gestion_documental (verification_api). Así se evita el mensaje "usuario no autorizado por ReCaptcha" del SII.

**Credenciales:** La misma `API_KEY_2CAPTCHA` que en la VM de verificación DT. En el servicio compartido ya está puesta en `scripts_vm/carrier-sii-scraper-shared-vm.service`. Si usas `env.proxy`, añade en ese archivo:

```bash
API_KEY_2CAPTCHA=tu_api_key_2captcha
```

**Sitekey del SII:** El código intenta leer el sitekey de reCAPTCHA desde la página. Si no lo encuentra (por ejemplo reCAPTCHA invisible), define la variable de entorno:

```bash
SII_RECAPTCHA_SITEKEY=el_sitekey_del_sii
```

Para obtener el sitekey: en el navegador, abre la página de consulta del SII, inspecciona el HTML y busca `data-sitekey` en el div de reCAPTCHA, o el parámetro en el script de recaptcha.

En logs verás: `[SII] Solicitando resolución a 2Captcha...` y `[SII] reCAPTCHA resuelto por 2Captcha` cuando funcione.

**Si el SII sigue mostrando "usuario no autorizado por ReCaptcha"** tras inyectar el token: (1) Pruebe otro `pageAction`: en el servicio defina `SII_RECAPTCHA_PAGE_ACTION=submit` (o el valor que use el SII; puede inspeccionar la pestaña Red del navegador). (2) El backend del SII puede validar el token de forma estricta (ventana de validez, fingerprint); 2Captcha con reCAPTCHA v3 no permite usar el mismo proxy que el navegador, así que no se puede “resolver desde la misma IP”. Mantener el proxy es necesario para no ser bloqueado por IP tras varias solicitudes.

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
ExecStart=/home/pc/carrierSync/venv/bin/uvicorn vm_services.sii_scraper_api:app --host 0.0.0.0 --port 8082
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=carrier-sii-scraper

[Install]
WantedBy=multi-user.target
```

Guardar: **Ctrl+O**, Enter, **Ctrl+X**.

Luego:

```bash
sudo systemctl daemon-reload
sudo systemctl enable carrier-sii-scraper.service
sudo systemctl start carrier-sii-scraper.service
sudo systemctl status carrier-sii-scraper.service
```

El firewall (paso 2.1) y la URL en `env.dev.yaml` / `env.prod.yaml` (paso 2.7) son los mismos.
