#!/bin/bash
# Instala el scraper SII de CarrierSync en la VM compartida con gestion_documental.
# Uso: ejecutar DENTRO de la VM (ej. 34.176.102.209), en la carpeta del repo CarrierSync.
# Requiere: Python 3.11+, Chrome/Chromium (si no está: sudo apt install chromium-browser).
#
# Desde la PC primero: abrir puerto 8082 (ver documentacion/README_VM.md).

set -e
echo "=== CarrierSync - Instalación en VM compartida (puerto 8082) ==="

INSTALL_DIR="${INSTALL_DIR:-/home/pc/carrierSync}"
SERVICE_NAME="carrier-sii-scraper"

# Si se ejecuta desde el repo clonado, el directorio actual es la raíz del repo
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "$REPO_ROOT/vm_services/sii_scraper_api.py" ]; then
  echo "Error: Ejecuta este script desde la raíz del repo CarrierSync (donde está main.py)."
  exit 1
fi

echo "Repositorio: $REPO_ROOT"
echo "Instalación: $INSTALL_DIR"

if [ "$REPO_ROOT" != "$INSTALL_DIR" ]; then
  sudo mkdir -p "$INSTALL_DIR"
  sudo cp -r "$REPO_ROOT"/* "$INSTALL_DIR"/
  sudo chown -R pc:pc "$INSTALL_DIR"
  cd "$INSTALL_DIR"
else
  cd "$INSTALL_DIR"
fi

# Venv y dependencias
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements_vm.txt -q
echo "Dependencias instaladas."

# Servicio systemd (puerto 8082)
sudo cp "$INSTALL_DIR/scripts_vm/carrier-sii-scraper-shared-vm.service" /etc/systemd/system/"$SERVICE_NAME".service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sleep 2
sudo systemctl status "$SERVICE_NAME" --no-pager || true

echo ""
echo "=== Listo ==="
echo "Scraper SII escuchando en puerto 8082."
echo "Probar: curl http://localhost:8082/health"
echo "Desde fuera: curl http://34.176.102.209:8082/health"
echo ""
echo "En env.dev.yaml y env.prod.yaml de CarrierSync (en tu PC) pon:"
echo '  VM_SII_SCRAPER_URL: "http://34.176.102.209:8082"'
