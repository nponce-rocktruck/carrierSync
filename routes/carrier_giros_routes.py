"""
Rutas para carga masiva e inicial de giros (actividades económicas) en RT_carrier.
Dispara automatización SII en VM y registra logs en carrier_giros_sync_log.
"""

import logging
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from models.carrier_models import CargaGirosRequest, CargaGirosResponse, JobStatusResponse
from services.carrier_giros_service import run_carga_giros, get_carriers_to_process
from services.sync_log_service import create_sync_job, get_job, list_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["carrier-giros"])

# Ejecutor para correr el job en background (no bloquear la request)
_executor = ThreadPoolExecutor(max_workers=2)


def _run_job_in_background(job_id: str, run_type: str, rut_list: List[str] | None, carrier_ids: List[str] | None):
    """Ejecuta run_carga_giros en un thread (para no bloquear)."""
    try:
        run_carga_giros(job_id=job_id, run_type=run_type, rut_list=rut_list, carrier_ids=carrier_ids)
    except Exception as e:
        logger.exception(f"Error en job {job_id}: {e}")
        from database.mongodb_connection import get_collection
        from database.init_database import SYNC_LOG_COLLECTION
        from datetime import datetime
        get_collection(SYNC_LOG_COLLECTION).update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "finished_at": datetime.utcnow(), "message": str(e)}},
        )


@router.post("/carga-giros", response_model=CargaGirosResponse)
async def iniciar_carga_giros(request: CargaGirosRequest, background_tasks: BackgroundTasks):
    """
    Inicia la carga/actualización de giros para carriers.
    - initial_load: procesa todos los carriers (o los filtrados por rut_list/carrier_ids).
    - periodic_update: igual pero se registra como actualización periódica.
    Devuelve job_id de inmediato; el trabajo corre en background.
    Consulta el estado con GET /api/v1/carga-giros/{job_id}.
    """
    carriers = get_carriers_to_process(
        rut_list=request.rut_list,
        carrier_ids=request.carrier_ids,
    )
    total = len(carriers)
    job_id = str(uuid.uuid4())
    create_sync_job(job_id=job_id, run_type=request.run_type, total_carriers=total)
    # Ejecutar en background
    background_tasks.add_task(
        _run_job_in_background,
        job_id,
        request.run_type,
        request.rut_list,
        request.carrier_ids,
    )
    from datetime import datetime
    return CargaGirosResponse(
        job_id=job_id,
        run_type=request.run_type,
        status="running",
        started_at=datetime.utcnow(),
        total_carriers=total,
        message=f"Job iniciado. Total carriers a procesar: {total}. Consulta GET /api/v1/carga-giros/{job_id} para el estado.",
    )


@router.get("/carga-giros/{job_id}", response_model=JobStatusResponse)
async def estado_carga_giros(job_id: str):
    """Obtiene el estado y resumen de un job de carga de giros."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} no encontrado")
    details = job.get("details", [])
    return JobStatusResponse(
        job_id=job["job_id"],
        run_type=job.get("run_type", ""),
        status=job.get("status", "unknown"),
        started_at=job["started_at"],
        finished_at=job.get("finished_at"),
        total_carriers=job.get("total_carriers", 0),
        processed=job.get("processed", 0),
        updated=job.get("updated", 0),
        not_found_in_sii=job.get("not_found_in_sii", 0),
        sii_failed=job.get("sii_failed", 0),
        not_processed=job.get("not_processed", 0),
        details_count=len(details),
    )


@router.get("/carga-giros/{job_id}/detalle")
async def detalle_carga_giros(job_id: str) -> Dict[str, Any]:
    """Obtiene el job completo incluyendo la lista de detalles (por RUT/carrier)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} no encontrado")
    if "_id" in job:
        job["_id"] = str(job["_id"])
    return job


@router.get("/carga-giros", response_model=List[Dict[str, Any]])
async def listar_jobs(limit: int = 50, run_type: str | None = None):
    """Lista los últimos jobs de carga de giros."""
    return list_jobs(limit=limit, run_type=run_type)
