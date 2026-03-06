"""
Inicialización y verificación de la base de datos MongoDB para CarrierSync.
Colecciones: RT_carrier, carrier_giros_sync_log.
"""

import os
import sys
import logging
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Nombres de colecciones usadas por la API
CARRIER_COLLECTION = "RT_carrier"
SYNC_LOG_COLLECTION = "carrier_giros_sync_log"


def verify_database_connection():
    """Verifica la conexión a la base de datos existente."""

    mongodb_url = os.getenv("MONGODB_URL", "").strip()
    database_name = os.getenv("MONGODB_DATABASE", "Samanta").strip()

    if not mongodb_url:
        raise ValueError(
            "MONGODB_URL no configurada. Debe establecerse como variable de entorno en Cloud Run."
        )

    client = MongoClient(
        mongodb_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
    )
    db = client[database_name]

    try:
        collections = db.list_collection_names()
        # RT_carrier es la colección principal; carrier_giros_sync_log puede crearse al primer uso
        if CARRIER_COLLECTION not in collections:
            raise Exception(
                f"Colección '{CARRIER_COLLECTION}' no existe. Ejecuta los scripts de configuración primero."
            )
        logger.info(f"Conexión a base de datos '{database_name}' verificada correctamente")
        logger.info(f"Colecciones: {collections}")
    except Exception as e:
        logger.error(f"Error al verificar la base de datos: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Verificando conexión a base de datos MongoDB...")
    verify_database_connection()
    print("Base de datos verificada correctamente.")
