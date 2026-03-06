#!/bin/bash
# Despliegue a producción
set -e
if [ -f env.prod.yaml ]; then
  gcloud run deploy carriersync-prod --source . --platform managed --region us-central1 \
    --allow-unauthenticated --set-env-vars-from-file env.prod.yaml \
    --memory=1Gi --cpu=1 --min-instances=1 --port=8080 --quiet
else
  echo "Crear env.prod.yaml a partir de env.prod.yaml.example"
  exit 1
fi
