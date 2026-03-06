"""
Servicio para crear y consultar jobs de sincronización de giros (carrier_giros_sync_log).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import DESCENDING

from database.mongodb_connection import get_collection, get_database
from database.init_database import SYNC_LOG_COLLECTION

logger = logging.getLogger(__name__)


def ensure_sync_log_collection() -> None:
    """Asegura que la colección carrier_giros_sync_log exista; la crea si no existe."""
    db = get_database()
    names = db.list_collection_names()
    if SYNC_LOG_COLLECTION not in names:
        db.create_collection(SYNC_LOG_COLLECTION)
        logger.info("Colección '%s' creada (no existía)", SYNC_LOG_COLLECTION)
    else:
        logger.debug("Colección '%s' ya existe", SYNC_LOG_COLLECTION)


def create_sync_job(
    job_id: str,
    run_type: str,
    total_carriers: int = 0,
    ruts_no_encontrados_en_rt_carrier: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Crea un documento de job en carrier_giros_sync_log con status running."""
    ensure_sync_log_collection()
    coll = get_collection(SYNC_LOG_COLLECTION)
    ruts_no = ruts_no_encontrados_en_rt_carrier if ruts_no_encontrados_en_rt_carrier is not None else []
    doc = {
        "job_id": job_id,
        "run_type": run_type,
        "status": "running",
        "started_at": datetime.utcnow(),
        "finished_at": None,
        "total_carriers": total_carriers,
        "processed": 0,
        "updated": 0,
        "not_found_in_sii": 0,
        "sii_failed": 0,
        "not_processed": 0,
        "details": [],
        "ruts_no_encontrados_en_rt_carrier": ruts_no,
    }
    coll.insert_one(doc)
    logger.info(
        "Job creado en carrier_giros_sync_log: job_id=%s run_type=%s total_carriers=%s",
        job_id, run_type, total_carriers,
    )
    return doc


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene un job por job_id."""
    coll = get_collection(SYNC_LOG_COLLECTION)
    doc = coll.find_one({"job_id": job_id})
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def list_jobs(limit: int = 50, run_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista los últimos jobs, opcionalmente filtrados por run_type."""
    coll = get_collection(SYNC_LOG_COLLECTION)
    q = {}
    if run_type:
        q["run_type"] = run_type
    cursor = coll.find(q).sort("started_at", DESCENDING).limit(limit)
    result = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        result.append(doc)
    return result
