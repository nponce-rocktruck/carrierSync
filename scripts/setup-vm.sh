#!/bin/bash
# Configuración de la VM para CarrierSync - Scraper SII
# Ejecutar en la VM donde correrá la API de scraping (no en Cloud Run).

set -e
echo "=== CarrierSync VM - Setup Scraper SII ==="

# Crear usuario si no existe
id -u carriersync &>/dev/null || sudo useradd -r -s /bin/false carriersync

# Directorio de la app
INSTALL_DIR=/opt/carriersync
sudo mkdir -p $INSTALL_DIR
sudo cp -r . $INSTALL_DIR/
sudo chown -R carriersync:carriersync $INSTALL_DIR

# Python y venv
cd $INSTALL_DIR
python3 -m venv venv
./venv/bin/pip install -r requirements_vm.txt

# Servicio systemd: un solo proceso en 8080 (dev y prod usan la misma VM y puerto)
sudo cp scripts_vm/carrier-sii-scraper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable carrier-sii-scraper
sudo systemctl start carrier-sii-scraper
sudo systemctl status carrier-sii-scraper

echo "VM lista. Configura VM_SII_SCRAPER_URL en env.dev.yaml y env.prod.yaml con la misma URL: http://IP_VM:8080"
