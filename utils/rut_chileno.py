"""
Validación de RUT chileno (Rol Único Nacional) con dígito verificador (módulo 11).
"""

import re
from typing import Tuple


def _normalizar_rut(rut: str) -> Tuple[str, str]:
    """Separa número base y dígito verificador. Acepta 12345678-9, 12.345.678-K, etc."""
    if not rut or not isinstance(rut, str):
        return ("", "")
    s = rut.strip().upper().replace(".", "").replace(" ", "")
    if "-" in s:
        partes = s.split("-", 1)
        return (partes[0].strip(), partes[1].strip() if len(partes) > 1 else "")
    if len(s) >= 2 and s[-1] in "0123456789K":
        return (s[:-1], s[-1])
    return (s, "")


def calcular_digito_verificador(numero_base: str) -> str:
    """Calcula el dígito verificador para el número base del RUT (módulo 11)."""
    multiplicadores = [2, 3, 4, 5, 6, 7]
    suma = 0
    for i, d in enumerate(reversed(numero_base)):
        if not d.isdigit():
            return ""
        suma += int(d) * multiplicadores[i % 6]
    resto = suma % 11
    dv = 11 - resto
    if dv == 11:
        return "0"
    if dv == 10:
        return "K"
    return str(dv)


def validar_rut_chileno(rut: str) -> bool:
    """Valida formato y dígito verificador del RUT chileno."""
    if not rut or not rut.strip():
        return False
    numero, dv = _normalizar_rut(rut)
    if not numero or not dv:
        return False
    if not numero.isdigit():
        return False
    return calcular_digito_verificador(numero) == dv.upper()


def normalizar_rut_para_busqueda(rut: str) -> str:
    """Devuelve RUT sin puntos, con un solo guión antes del dígito verificador (ej: 10444590-K)."""
    if not rut or not isinstance(rut, str):
        return ""
    s = rut.strip().upper().replace(".", "").replace(" ", "").replace("-", "")
    if not s:
        return ""
    if len(s) >= 2 and s[-1] in "0123456789K":
        return f"{s[:-1]}-{s[-1]}"
    return s


def rut_con_puntos(rut_normalizado: str) -> str:
    """Formatea RUT con puntos de miles (ej: 10444590-K -> 10.444.590-K). Usado para buscar en BD donde se guarda así."""
    if not rut_normalizado or "-" not in rut_normalizado:
        return rut_normalizado or ""
    numero, dv = rut_normalizado.rsplit("-", 1)
    numero = numero.replace(".", "")
    if not numero.isdigit():
        return rut_normalizado
    # Agrupar de derecha a izquierda de 3 en 3
    partes = []
    while numero:
        partes.append(numero[-3:])
        numero = numero[:-3]
    return ".".join(reversed(partes)) + "-" + dv.upper()
