"""
Servicio de negocio: obtener carriers, actualizar economicActivities y orquestar con la VM SII.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import DESCENDING

from database.mongodb_connection import get_collection
from database.init_database import CARRIER_COLLECTION, SYNC_LOG_COLLECTION
from models.carrier_models import EconomicActivity
from services.sii_vm_client import SIIVMClient
from utils.rut_chileno import normalizar_rut_para_busqueda, rut_con_puntos

logger = logging.getLogger(__name__)


def _carrier_tax_id(doc: Dict[str, Any]) -> str:
    """Extrae tax_id o legal_tax_id del documento carrier."""
    return (doc.get("tax_id") or doc.get("legal_tax_id") or "").strip()


def _activities_to_doc(activities: List[EconomicActivity]) -> List[Dict[str, Any]]:
    """Convierte EconomicActivity a documento para MongoDB (con fechas serializables)."""
    return [
        {
            "code": a.code,
            "description": a.description,
            "category": a.category,
            "isVatSubject": a.isVatSubject,
            "startDate": a.startDate,
            "lastUpdatedAt": a.lastUpdatedAt,
            "dataSource": a.dataSource,
            "extractedAt": a.extractedAt,
        }
        for a in activities
    ]


# Clave del objeto giros en RT_carrier (único objeto con updated_giros_at, initial_sync_at y lista de giros)
GIROS_SYNC_FIELD = "giros_sync"


def get_carriers_to_process(
    rut_list: Optional[List[str]] = None,
    carrier_ids: Optional[List[str]] = None,
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """
    Obtiene los carriers a procesar.
    - Si rut_list: filtra por tax_id (o legal_tax_id) en esa lista (normalizados).
    - Si carrier_ids: filtra por _id en esa lista.
    - Si ninguno: todos los de la colección (para carga inicial), opcionalmente limit.
    """
    coll = get_collection(CARRIER_COLLECTION)
    q = {}
    if carrier_ids:
        try:
            ids = [ObjectId(oid) for oid in carrier_ids]
            q["_id"] = {"$in": ids}
        except Exception:
            logger.warning("Algunos carrier_ids no son ObjectId válidos, ignorando filtro")
    elif rut_list:
        ruts_norm = [normalizar_rut_para_busqueda(r) for r in rut_list if r]
        # Sin guión (10444590K) y con puntos de miles (10.444.590-K) por si la BD los guarda así
        ruts_alt = [r.replace("-", "") for r in ruts_norm]
        ruts_con_puntos = [rut_con_puntos(r) for r in ruts_norm]
        ruts_todos = list(dict.fromkeys(ruts_norm + ruts_alt + ruts_con_puntos))
        q["$or"] = [
            {"tax_id": {"$in": ruts_todos}},
            {"legal_tax_id": {"$in": ruts_todos}},
        ]
    cursor = coll.find(q)
    if limit > 0:
        cursor = cursor.limit(limit)
    return list(cursor)


def update_carrier_giros_sync(carrier_id: ObjectId, activities: List[EconomicActivity]) -> bool:
    """
    Actualiza el objeto giros_sync del carrier solo cuando el proceso resultó bien.
    - updated_giros_at: siempre ahora (última actualización exitosa).
    - initial_sync_at: se setea en la primera vez que hay éxito; luego no se sobrescribe.
    - economicActivities: se reemplaza por completo (eliminar todos y escribir los encontrados).
    Si falla la consulta SII, no se llama a esta función y no se escribe nada en giros_sync.
    """
    if not activities:
        return False
    coll = get_collection(CARRIER_COLLECTION)
    now = datetime.utcnow()
    # Mantener initial_sync_at si ya existía (primera carga exitosa); si no, usar now
    existing = coll.find_one({"_id": carrier_id}, {f"{GIROS_SYNC_FIELD}.initial_sync_at": 1})
    prev_giros = (existing or {}).get(GIROS_SYNC_FIELD) or {}
    initial_sync_at = prev_giros.get("initial_sync_at") or now
    doc_list = _activities_to_doc(activities)
    giros_sync = {
        "updated_giros_at": now,
        "initial_sync_at": initial_sync_at,
        "economicActivities": doc_list,
    }
    result = coll.update_one(
        {"_id": carrier_id},
        {"$set": {GIROS_SYNC_FIELD: giros_sync}},
    )
    return result.modified_count > 0


def run_carga_giros(
    job_id: str,
    run_type: str,
    rut_list: Optional[List[str]] = None,
    carrier_ids: Optional[List[str]] = None,
    vm_client: Optional[SIIVMClient] = None,
) -> Dict[str, Any]:
    """
    Ejecuta la carga de giros: para cada carrier obtiene giros vía VM SII y actualiza RT_carrier.
    Registra el resultado en carrier_giros_sync_log.
    """
    log_coll = get_collection(SYNC_LOG_COLLECTION)
    vm = vm_client or SIIVMClient()

    carriers = get_carriers_to_process(rut_list=rut_list, carrier_ids=carrier_ids)
    total = len(carriers)
    # RUTs solicitados en rut_list que no están en RT_carrier (para escribir en el job)
    ruts_no_en_rt_carrier: List[str] = []
    if rut_list:
        requested_norm = set(normalizar_rut_para_busqueda(r) for r in rut_list if r)
        found_norm = set(normalizar_rut_para_busqueda(_carrier_tax_id(c)) for c in carriers)
        ruts_no_en_rt_carrier = sorted(requested_norm - found_norm)
    logger.info("run_carga_giros: job_id=%s total_carriers=%s (iniciando)", job_id, total)
    if total == 0 and (rut_list or carrier_ids):
        # Diagnóstico: se filtró por rut_list o carrier_ids pero no hubo coincidencias
        if rut_list:
            ruts_norm = [normalizar_rut_para_busqueda(r) for r in (rut_list or []) if r]
            logger.warning(
                "run_carga_giros: job_id=%s 0 carriers para rut_list (N=%s). RUTs buscados (normalizados): %s. Verifique tax_id/legal_tax_id en RT_carrier.",
                job_id, len(ruts_norm), ruts_norm[:10] if len(ruts_norm) > 10 else ruts_norm,
            )
        else:
            logger.warning(
                "run_carga_giros: job_id=%s 0 carriers para carrier_ids=%s. Verifique que los _id existan en RT_carrier.",
                job_id, (carrier_ids or [])[:10],
            )
    if total == 0:
        update_payload: Dict[str, Any] = {
            "status": "completed",
            "finished_at": datetime.utcnow(),
            "message": "No hay carriers que procesar",
            "ruts_no_encontrados_en_rt_carrier": ruts_no_en_rt_carrier,
        }
        log_coll.update_one(
            {"job_id": job_id},
            {"$set": update_payload},
            upsert=True,
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "total_carriers": 0,
            "processed": 0,
            "updated": 0,
            "not_found_in_sii": 0,
            "sii_failed": 0,
            "not_processed": 0,
            "details": [],
        }

    details = []
    processed = updated = not_found_in_sii = sii_failed = not_processed = 0

    PROGRESS_LOG_EVERY = 25  # Log cada N carriers en INFO
    for i, carrier in enumerate(carriers):
        if (i + 1) % PROGRESS_LOG_EVERY == 0 or i == 0:
            logger.info("run_carga_giros: job_id=%s progreso %s/%s", job_id, i + 1, total)
        cid = str(carrier["_id"])
        tax_id = _carrier_tax_id(carrier)
        if not tax_id:
            details.append(
                {
                    "carrier_id": cid,
                    "tax_id": "",
                    "status": "not_processed",
                    "error_message": "Carrier sin tax_id",
                }
            )
            not_processed += 1
        else:
            result = vm.get_giros_by_rut(tax_id)
            processed += 1

            if not result.get("success"):
                if result.get("not_found"):
                    status = "not_found_sii"
                    not_found_in_sii += 1
                else:
                    status = "sii_failed"
                    sii_failed += 1
                details.append(
                    {
                        "carrier_id": cid,
                        "tax_id": tax_id,
                        "status": status,
                        "error_message": result.get("error"),
                        "raw_sii_response": result.get("raw_sii_response"),
                    }
                )
            else:
                activities_raw = result.get("activities", [])
                economic_activities = vm.activities_to_economic_activities(activities_raw)
                if not economic_activities:
                    details.append(
                        {
                            "carrier_id": cid,
                            "tax_id": tax_id,
                            "status": "not_found_sii",
                            "error_message": "Sin actividades en respuesta SII",
                            "raw_sii_response": result.get("raw_sii_response"),
                        }
                    )
                    not_found_in_sii += 1
                else:
                    ok = update_carrier_giros_sync(carrier["_id"], economic_activities)
                    if ok:
                        updated += 1
                        details.append(
                            {
                                "carrier_id": cid,
                                "tax_id": tax_id,
                                "status": "updated",
                                "activities_count": len(economic_activities),
                            }
                        )
                    else:
                        not_processed += 1
                        details.append(
                            {
                                "carrier_id": cid,
                                "tax_id": tax_id,
                                "status": "not_processed",
                                "error_message": "Error al actualizar documento",
                            }
                        )

        # Actualizar progreso del job en DB después de cada carrier
        try:
            log_coll.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "running",
                        "total_carriers": total,
                        "processed": processed,
                        "updated": updated,
                        "not_found_in_sii": not_found_in_sii,
                        "sii_failed": sii_failed,
                        "not_processed": not_processed,
                        "details": details,
                        "ruts_no_encontrados_en_rt_carrier": ruts_no_en_rt_carrier,
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("run_carga_giros: no se pudo actualizar progreso del job %s: %s", job_id, e)

    finished_at = datetime.utcnow()
    status = "completed" if processed == total and (updated + not_found_in_sii + sii_failed) == processed else "partial"
    if not vm.is_configured():
        status = "failed"
        details.append(
            {
                "carrier_id": "",
                "tax_id": "",
                "status": "error",
                "error_message": "VM_SII_SCRAPER_URL no configurada",
            }
        )

    log_coll.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": status,
                "finished_at": finished_at,
                "total_carriers": total,
                "processed": processed,
                "updated": updated,
                "not_found_in_sii": not_found_in_sii,
                "sii_failed": sii_failed,
                "not_processed": not_processed,
                "details": details,
                "ruts_no_encontrados_en_rt_carrier": ruts_no_en_rt_carrier,
            }
        },
        upsert=True,
    )

    logger.info(
        "run_carga_giros: job_id=%s terminado status=%s processed=%s updated=%s not_found_in_sii=%s sii_failed=%s not_processed=%s",
        job_id, status, processed, updated, not_found_in_sii, sii_failed, not_processed,
    )
    return {
        "job_id": job_id,
        "status": status,
        "total_carriers": total,
        "processed": processed,
        "updated": updated,
        "not_found_in_sii": not_found_in_sii,
        "sii_failed": sii_failed,
        "not_processed": not_processed,
        "details": details,
        "finished_at": finished_at,
    }
