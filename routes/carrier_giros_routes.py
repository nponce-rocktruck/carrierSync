"""
Rutas para carga masiva e inicial de giros (actividades económicas) en RT_carrier.
Dispara automatización SII en VM y registra logs en carrier_giros_sync_log.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from models.carrier_models import CargaGirosRequest, CargaGirosResponse, JobStatusResponse
from services.carrier_giros_service import run_carga_giros, get_carriers_to_process
from services.sync_log_service import create_sync_job, get_job, list_jobs
from utils.rut_chileno import normalizar_rut_para_busqueda

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["carrier-giros"])

# Ejecutor para correr el job en background (no bloquear la request)
_executor = ThreadPoolExecutor(max_workers=2)


def _run_job_in_background(job_id: str, run_type: str, rut_list: List[str] | None, carrier_ids: List[str] | None):
    """Ejecuta run_carga_giros en un thread (para no bloquear)."""
    logger.info("Job %s: iniciando proceso en background (run_type=%s)", job_id, run_type)
    try:
        result = run_carga_giros(job_id=job_id, run_type=run_type, rut_list=rut_list, carrier_ids=carrier_ids)
        logger.info(
            "Job %s: completado status=%s processed=%s updated=%s not_found=%s sii_failed=%s not_processed=%s",
            job_id,
            result.get("status"),
            result.get("processed", 0),
            result.get("updated", 0),
            result.get("not_found_in_sii", 0),
            result.get("sii_failed", 0),
            result.get("not_processed", 0),
        )
    except Exception as e:
        logger.exception("Job %s: fallido con error: %s", job_id, e)
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
    logger.info(
        "POST /carga-giros: job_id=%s run_type=%s total_carriers=%s (rut_list=%s carrier_ids=%s)",
        job_id, request.run_type, total,
        "sí" if request.rut_list else "no", "sí" if request.carrier_ids else "no",
    )
    if total == 0 and request.rut_list:
        logger.warning(
            "POST /carga-giros: 0 carriers para rut_list con %s RUT(s). Ejemplo recibido: %s. Verifique que existan en RT_carrier (tax_id o legal_tax_id).",
            len(request.rut_list), request.rut_list[:5] if request.rut_list else [],
        )
    ruts_no_en_rt_carrier: List[str] = []
    if request.rut_list:
        requested_norm = set(normalizar_rut_para_busqueda(r) for r in request.rut_list if r)
        found_norm = set(
            normalizar_rut_para_busqueda((c.get("tax_id") or c.get("legal_tax_id") or "").strip())
            for c in carriers
        )
        ruts_no_en_rt_carrier = sorted(requested_norm - found_norm)
    create_sync_job(
        job_id=job_id,
        run_type=request.run_type,
        total_carriers=total,
        ruts_no_encontrados_en_rt_carrier=ruts_no_en_rt_carrier,
    )
    # Ejecutar en background
    background_tasks.add_task(
        _run_job_in_background,
        job_id,
        request.run_type,
        request.rut_list,
        request.carrier_ids,
    )
    from datetime import datetime
    msg = f"Job iniciado. Total carriers a procesar: {total}."
    if ruts_no_en_rt_carrier:
        msg += f" RUT(s) no encontrado(s) en RT_carrier: {', '.join(ruts_no_en_rt_carrier)}."
    msg += f" Consulta GET /api/v1/carga-giros/{job_id} para el estado."
    return CargaGirosResponse(
        job_id=job_id,
        run_type=request.run_type,
        status="running",
        started_at=datetime.utcnow(),
        total_carriers=total,
        message=msg,
        ruts_no_encontrados_en_rt_carrier=ruts_no_en_rt_carrier,
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
        ruts_no_encontrados_en_rt_carrier=job.get("ruts_no_encontrados_en_rt_carrier", []),
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
