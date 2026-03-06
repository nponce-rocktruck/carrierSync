"""
Rutas de salud y monitoreo para CarrierSync API.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter
from database.mongodb_connection import get_collection
from database.init_database import CARRIER_COLLECTION

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Endpoint de salud de la API."""
    try:
        db_status = "unknown"
        db_error = None
        try:
            get_collection(CARRIER_COLLECTION).find_one()
            db_status = "healthy"
        except Exception as e:
            db_status = "unhealthy"
            db_error = str(e)
            logger.warning(f"Error de conexión a MongoDB: {e}")

        response = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "database": db_status,
            "service": "carrier-sync",
        }
        if db_error:
            response["database_error"] = db_error
        return response
    except Exception as e:
        logger.error(f"Error en health check: {e}")
        return {
            "status": "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "error": str(e),
        }


@router.get("/")
async def root() -> Dict[str, Any]:
    """Endpoint raíz."""
    return {
        "message": "CarrierSync API",
        "version": "1.0.0",
        "description": "API para sincronización de giros (actividades económicas) de transportistas con SII",
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
    }
