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
gcloud compute ssh mv-2-southamerica --zone=southamerica-west1-b --project=gestiondocumental-473815```

(Ajusta nombre y zona si son distintos.)

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

Si **no** tienes aún la carpeta `carrierSync`:

```bash
git clone https://github.com/TU_USUARIO/carrierSync.git
cd carrierSync
```

(Cambia `TU_USUARIO` por tu usuario u org de GitHub.)

Si **ya** tienes `carrierSync`:

```bash
cd carrierSync
git pull
```

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

# Ver logs en tiempo real
sudo journalctl -u carrier-sii-scraper -f

# Ver últimas 100 líneas
sudo journalctl -u carrier-sii-scraper -n 100

# Reiniciar (después de actualizar código)
sudo systemctl restart carrier-sii-scraper

# Detener / iniciar
sudo systemctl stop carrier-sii-scraper
sudo systemctl start carrier-sii-scraper
```

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
