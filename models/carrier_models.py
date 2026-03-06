"""
Modelos Pydantic para CarrierSync: carriers, actividades económicas y jobs de sincronización.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# --- Actividad económica (giro) ---
class EconomicActivity(BaseModel):
    """Una actividad económica (giro) asociada a un carrier."""
    code: str
    description: str
    category: str  # ej. "Primera"
    isVatSubject: bool = True
    startDate: Optional[datetime] = None
    lastUpdatedAt: Optional[datetime] = None
    dataSource: str = "consulta_automatizacion"  # monitoreo | consulta_automatizacion
    extractedAt: Optional[datetime] = None


# --- Objeto giros en RT_carrier (solo se escribe cuando el proceso termina bien) ---
class GirosSync(BaseModel):
    """
    Objeto único en RT_carrier con el estado de sincronización de giros.
    Se actualiza solo cuando la consulta al SII fue exitosa; si falla, no se toca.
    En cada actualización se reemplaza toda la lista economicActivities.
    """
    updated_giros_at: datetime  # Cuándo se actualizó por última vez (solo si resultó bien)
    initial_sync_at: datetime    # Cuándo se hizo la primera carga inicial exitosa
    economicActivities: List[EconomicActivity]  # Lista de giros; se reemplaza entera en cada sync exitoso


# --- Request/Response API ---
class CargaGirosRequest(BaseModel):
    """Request para carga masiva o por lista de RUTs/IDs."""
    run_type: Literal["initial_load", "periodic_update"] = "initial_load"
    rut_list: Optional[List[str]] = None   # Si se envía, solo se procesan estos RUTs
    carrier_ids: Optional[List[str]] = None  # ObjectIds de RT_carrier; si se envía, solo estos


class CarrierGirosSyncLogEntry(BaseModel):
    """Una entrada de log por carrier procesado."""
    carrier_id: str
    tax_id: str
    status: Literal["updated", "not_found_sii", "sii_failed", "not_processed", "error"]
    error_message: Optional[str] = None
    activities_count: Optional[int] = None
    raw_sii_response: Optional[dict] = None


class CargaGirosResponse(BaseModel):
    """Response del job de carga de giros."""
    job_id: str
    run_type: str
    status: Literal["running", "completed", "failed", "partial"]
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_carriers: int = 0
    processed: int = 0
    updated: int = 0
    not_found_in_sii: int = 0
    sii_failed: int = 0
    not_processed: int = 0
    details: List[CarrierGirosSyncLogEntry] = Field(default_factory=list)
    message: Optional[str] = None
    ruts_no_encontrados_en_rt_carrier: List[str] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    """Estado de un job de sincronización."""
    job_id: str
    run_type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_carriers: int
    processed: int
    updated: int
    not_found_in_sii: int
    sii_failed: int
    not_processed: int
    details_count: int
    ruts_no_encontrados_en_rt_carrier: List[str] = Field(default_factory=list)
