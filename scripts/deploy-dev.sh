#!/bin/bash
# Despliegue a desarrollo (desde CI o manual)
set -e
export AMBIENTE=dev
if [ -f env.dev.yaml ]; then
  gcloud run deploy carriersync-dev --source . --platform managed --region us-central1 \
    --allow-unauthenticated --set-env-vars-from-file env.dev.yaml \
    --memory=1Gi --cpu=1 --port=8080 --quiet
else
  echo "Crear env.dev.yaml a partir de env.dev.yaml.example"
  exit 1
fi
