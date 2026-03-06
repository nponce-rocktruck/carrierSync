"""
CarrierSync API - FastAPI
Sincronización de giros (actividades económicas) de transportistas con SII.
Soporta Cloud Run y Cloud Functions Gen2.
La automatización de scraping SII corre en VM (no en Cloud) para no bloquear IPs.
"""

import os
import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from utils.logging_utils import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

if os.path.exists(".env"):
    load_dotenv()
    logger.info("Archivo .env encontrado, cargando variables locales")
else:
    logger.info("Ejecutándose en producción, usando variables de entorno de Cloud Run")

# Importar rutas
health_router = None
carrier_giros_router = None
import_errors = {}

try:
    from routes.health_routes import router as health_router
    logger.info("health_routes importado")
except Exception as e:
    import_errors["health_routes"] = str(e)
    logger.error(f"Error importando health_routes: {e}", exc_info=True)

try:
    from routes.carrier_giros_routes import router as carrier_giros_router
    logger.info("carrier_giros_routes importado")
except Exception as e:
    import_errors["carrier_giros_routes"] = str(e)
    logger.error(f"Error importando carrier_giros_routes: {e}", exc_info=True)

try:
    from database.init_database import verify_database_connection
    logger.info("Verificación de DB importada")
except Exception as e:
    logger.warning(f"Error importando verificación de DB: {e}")
    def verify_database_connection():
        logger.warning("verify_database_connection() no disponible")
        pass

IS_CLOUD_FUNCTION = (
    os.getenv("FUNCTION_NAME") is not None
    or os.getenv("FUNCTION_TARGET") is not None
    or os.getenv("K_SERVICE") is None
)

app = FastAPI(
    title="CarrierSync API",
    description="API para sincronización de giros de transportistas con SII (RT_carrier)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def verify_db_middleware(request: Request, call_next):
    """Verificación lazy de DB en Cloud Functions."""
    if IS_CLOUD_FUNCTION and not hasattr(app.state, "db_verified"):
        try:
            verify_database_connection()
            app.state.db_verified = True
            logger.info("Conexión a base de datos verificada (lazy)")
        except Exception as e:
            logger.error(f"Error al verificar base de datos: {e}")
    return await call_next(request)


if health_router:
    app.include_router(health_router)
if carrier_giros_router:
    app.include_router(carrier_giros_router)


@app.get("/", tags=["health"])
async def root():
    """Endpoint raíz."""
    return {
        "status": "ok",
        "message": "CarrierSync API",
        "version": "1.0.0",
    }


@app.get("/api/v1/routes", tags=["diagnostic"])
async def list_routes():
    """Lista rutas registradas."""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": getattr(route, "name", "unknown"),
            })
    return {
        "total_routes": len(routes),
        "routes": sorted(routes, key=lambda x: x["path"]),
        "routers_imported": {
            "health_router": health_router is not None,
            "carrier_giros_router": carrier_giros_router is not None,
        },
        "import_errors": import_errors,
    }


@app.on_event("startup")
async def startup_event():
    """Inicio de la aplicación."""
    import asyncio
    try:
        logger.info("Iniciando CarrierSync API...")
        logger.info(f"Entorno: {'Cloud Function' if IS_CLOUD_FUNCTION else 'Cloud Run'}")
        port = os.getenv("PORT", "8080")
        logger.info(f"Puerto: {port}")
        if not IS_CLOUD_FUNCTION:
            async def verify_db_background():
                try:
                    verify_database_connection()
                    logger.info("Conexión a base de datos verificada")
                except Exception as e:
                    logger.warning(f"No se pudo verificar la conexión a la base de datos: {e}")
            asyncio.create_task(verify_db_background())
    except Exception as e:
        logger.error(f"Error en startup: {e}", exc_info=True)


if __name__ == "__main__":
    port = os.getenv("PORT", "8000")
    logger.info(f"Servidor local en puerto {port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(port),
        reload=False,
        log_level="info",
    )
