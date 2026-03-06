"""
Cliente HTTP para la API de scraping SII que corre en la VM (Oxylabs/Selenium).
La API en la VM expone un endpoint que consulta el SII por RUT y devuelve los giros.
"""

import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from models.carrier_models import EconomicActivity

logger = logging.getLogger(__name__)


class SIIVMClient:
    """Cliente para llamar a la API de consulta SII en la VM."""

    def __init__(self, vm_url: Optional[str] = None, timeout: int = 120):
        self.vm_url = (vm_url or os.getenv("VM_SII_SCRAPER_URL", "")).rstrip("/")
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.vm_url)

    def get_giros_by_rut(self, rut: str) -> Dict[str, Any]:
        """
        Obtiene los giros (actividades económicas) para un RUT consultando la VM.
        La VM ejecuta la automatización SII (Oxylabs) y devuelve la lista de actividades.

        Returns:
            {
                "success": bool,
                "rut": str,
                "activities": [ { "code", "description", "category", "isVatSubject", "fecha" } ],
                "error": str | None,
                "not_found": bool  # True si el RUT no tiene datos en SII
            }
        """
        if not self.vm_url:
            return {
                "success": False,
                "rut": rut,
                "activities": [],
                "error": "VM_SII_SCRAPER_URL no configurada",
                "not_found": False,
            }

        url = f"{self.vm_url}/api/v1/sii/giros"
        payload = {"rut": rut}

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code != 200:
                return {
                    "success": False,
                    "rut": rut,
                    "activities": [],
                    "error": data.get("detail", data.get("error", resp.text)) or f"HTTP {resp.status_code}",
                    "not_found": resp.status_code == 404 or data.get("not_found", False),
                }
            # Normalizar a lista de actividades con formato esperado
            activities = data.get("activities", data.get("economicActivities", []))
            return {
                "success": True,
                "rut": rut,
                "activities": activities,
                "error": data.get("error"),
                "not_found": data.get("not_found", False),
            }
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout consultando SII para RUT {rut}")
            return {
                "success": False,
                "rut": rut,
                "activities": [],
                "error": "Timeout al consultar SII",
                "not_found": False,
            }
        except Exception as e:
            logger.exception(f"Error consultando SII para RUT {rut}: {e}")
            return {
                "success": False,
                "rut": rut,
                "activities": [],
                "error": str(e),
                "not_found": False,
            }

    def activities_to_economic_activities(
        self, activities: List[Dict[str, Any]], data_source: str = "consulta_automatizacion"
    ) -> List[EconomicActivity]:
        """Convierte la respuesta de la VM al modelo EconomicActivity con extractedAt."""
        now = datetime.utcnow()
        result = []
        for a in activities:
            if isinstance(a, dict):
                # Aceptar fecha como string o datetime
                start_date = a.get("startDate") or a.get("fecha")
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                    except Exception:
                        start_date = now
                last_updated = a.get("lastUpdatedAt") or a.get("lastUpdated") or now
                if isinstance(last_updated, str):
                    try:
                        last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                    except Exception:
                        last_updated = now
                result.append(
                    EconomicActivity(
                        code=str(a.get("code", a.get("codigo", ""))),
                        description=str(a.get("description", a.get("actividad", ""))),
                        category=str(a.get("category", a.get("categoria", "Sin categoría"))),
                        isVatSubject=bool(a.get("isVatSubject", a.get("afecta_iva", True))),
                        startDate=start_date,
                        lastUpdatedAt=last_updated,
                        dataSource=data_source,
                        extractedAt=now,
                    )
                )
        return result
