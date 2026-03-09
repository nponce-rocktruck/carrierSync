"""
API de scraping SII para VM.
Expone POST /api/v1/sii/giros con {"rut": "..."} y devuelve las actividades económicas.
Arquitectura: 1 navegador Selenium + generador de tokens reCAPTCHA + requests al API del SII.
Ejecutar en VM para no bloquear IPs (Oxylabs u otro proxy, mismo patrón que la API de verificación DT).

- Proxy: mismo enfoque que DT (gestion_documental): Oxylabs vía OXY_* o HTTP_PROXY + extensión Chrome.
- Captcha: SII usa reCAPTCHA v3 Enterprise → CapSolver (ProxyLess). DT usa reCAPTCHA v2 → 2captcha.
- Uso estimado proxy: SII ~0.02 MB/consulta (solo POST getConsultaData). DT ~0.5-1 MB/verificación (página + captcha + PDF).
  Variable SII_ESTIMATED_MB_PER_REQUEST para ajustar. Respuesta incluye proxy_usage; GET /api/v1/proxy-stats para totales.

Limpieza de espacio: se usa un directorio temporal para el navegador global que se borra al apagar;
además se ejecuta limpieza periódica de sesiones viejas (VM_CLEANUP_EVERY_N_REQUESTS) para evitar
llenar el disco.
"""

import os
import re
import time
import shutil
import queue
import logging
import threading
import zipfile
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from urllib.parse import quote

import requests

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Selenium/Chrome - en VM
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium no disponible; instalar requirements_vm.txt en la VM")

try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    uc = None
    logger.info("undetected_chromedriver no instalado; se usará Selenium estándar")

app = FastAPI(title="CarrierSync VM - SII Scraper", version="1.0.0")

# ----------------------------
# CONFIG (tus variables)
# ----------------------------
# Strip para evitar 401 por espacios/CRLF si env.proxy se editó en Windows
OXY_USER = (os.getenv("OXY_USER") or "").strip()
OXY_PASS = (os.getenv("OXY_PASS") or "").strip()
OXY_HOST = (os.getenv("OXY_HOST") or "unblock.oxylabs.io").strip() or "unblock.oxylabs.io"
OXY_PORT = (os.getenv("OXY_PORT") or "60000").strip() or "60000"

HTTP_PROXY = (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "").strip() or None
PROXY_USER = (os.getenv("PROXY_USER") or "").strip()
PROXY_PASSWORD = (os.getenv("PROXY_PASSWORD") or "").strip()

SII_SCRAPER_USE_PROXY = os.getenv("SII_SCRAPER_USE_PROXY", "true").lower() not in ("false", "0", "no")

SII_RECAPTCHA_SITEKEY = os.getenv("SII_RECAPTCHA_SITEKEY", "").strip()
SII_RECAPTCHA_SITEKEY_DEFAULT = "6Lc_DPAqAAAAAB7QWxHsaPDNxLLOUj9VkiuAXRYP"
SII_CONSULTA_URL = "https://www2.sii.cl/stc/noauthz.html"
SII_GET_CONSULTA_DATA_URL = "https://www2.sii.cl/app/stc/recurso/v1/consulta/getConsultaData/"
SII_RECAPTCHA_PAGE_ACTION = os.getenv("SII_RECAPTCHA_PAGE_ACTION", "consultaSTC")

# CapSolver: si está definido, se usan tokens de CapSolver en lugar del navegador (evita timeouts).
CAPSOLVER_API_KEY = (os.getenv("CAPSOLVER_API_KEY") or "").strip()
CAPSOLVER_API_URL = (os.getenv("CAPSOLVER_API_URL") or "https://api.capsolver.com").strip().rstrip("/")

TOKEN_QUEUE_SIZE = int(os.getenv("TOKEN_QUEUE_SIZE", "100"))

# Timeout para scripts en el navegador (reCAPTCHA con proxy puede ser lento). Aumentar si ves "script timeout".
SCRIPT_TIMEOUT_SEC = int(os.getenv("SCRIPT_TIMEOUT_SEC", "120"))

# Undetected Chrome: menos detección por reCAPTCHA (usar si está instalado)
SII_USE_UC = UC_AVAILABLE and os.getenv("SII_USE_UC", "true").lower() in ("true", "1", "yes")
# Versión principal de Chrome para UC (ej: 145, 146). Si 0 o vacío, UC auto-detecta.
UC_VERSION_MAIN = int(os.getenv("UC_VERSION_MAIN", "145") or "0")

# --- Limpieza de espacio en disco (evitar llenar /tmp con sesiones viejas) ---
VM_TEMP_BASE = Path(os.getenv("VM_TEMP_BASE_DIR", "/tmp/carriersync_scraper"))
VM_CLEANUP_MAX_AGE_MINUTES = int(os.getenv("VM_CLEANUP_MAX_AGE_MINUTES", "15"))
VM_CLEANUP_EVERY_N_REQUESTS = int(os.getenv("VM_CLEANUP_EVERY_N_REQUESTS", "50"))

_request_count = 0
_request_count_lock = threading.Lock()

# ----------------------------
# GLOBALS (1 navegador + cola de tokens)
# ----------------------------
driver = None
session_dir = None
token_queue = queue.Queue(maxsize=TOKEN_QUEUE_SIZE)

# Tracking de uso de proxy (mismo patrón que DT: estimación MB para Oxylabs)
# SII: solo el POST getConsultaData va por proxy → ~0.02 MB por consulta (request+response).
# DT: página + reCAPTCHA v2 + descarga PDF → ~0.5 MB/min ≈ 0.5-1 MB por verificación.
SII_ESTIMATED_MB_PER_REQUEST = float(os.getenv("SII_ESTIMATED_MB_PER_REQUEST", "0.02"))
_proxy_usage_lock = threading.Lock()
_proxy_usage_stats = {
    "requests_count": 0,
    "total_estimated_mb": 0.0,
    "last_reset": datetime.utcnow().isoformat(),
}


def _get_proxy_config() -> Optional[Dict[str, str]]:
    """
    Devuelve configuración de proxy para uso con extensión Chrome y para requests.
    Prioridad: OXY_* > HTTP_PROXY + PROXY_USER/PROXY_PASSWORD.
    Si SII_SCRAPER_USE_PROXY=false, no usa proxy.
    """
    if not SII_SCRAPER_USE_PROXY:
        return None
    if OXY_USER and OXY_PASS and OXY_HOST and OXY_PORT:
        return {"host": OXY_HOST, "port": OXY_PORT, "username": OXY_USER, "password": OXY_PASS}
    if HTTP_PROXY and PROXY_USER and PROXY_PASSWORD:
        from urllib.parse import urlparse
        parsed = urlparse(HTTP_PROXY if "://" in HTTP_PROXY else "http://" + HTTP_PROXY)
        host = parsed.hostname or ""
        port = str(parsed.port or "80")
        if host:
            return {"host": host, "port": port, "username": PROXY_USER, "password": PROXY_PASSWORD}
    return None


def _proxies_for_requests() -> Optional[Dict[str, str]]:
    """Proxies en formato requests. Usuario y contraseña codificados para evitar 401 con caracteres especiales."""
    pc = _get_proxy_config()
    if not pc:
        return None
    user = quote(pc["username"], safe="")
    passwd = quote(pc["password"], safe="")
    url = f"http://{user}:{passwd}@{pc['host']}:{pc['port']}"
    return {"http": url, "https": url}


def _capsolver_proxy_string() -> Optional[str]:
    """Formato proxy para CapSolver. Prueba host:port:user:pass (documentado por CapSolver)."""
    pc = _get_proxy_config()
    if not pc:
        return None
    # Formato: http:host:port:user:pass (evita problemas con @ en URL)
    return f"http:{pc['host']}:{pc['port']}:{pc['username']}:{pc['password']}"


def _get_token_capsolver() -> Optional[str]:
    """
    Obtiene un token reCAPTCHA v3 Enterprise vía CapSolver.
    Usamos ProxyLess porque los workers de CapSolver no pueden usar proxy Oxylabs
    (Oxylabs suele aceptar solo la IP del cliente). La petición al SII sigue yendo por Oxylabs.
    """
    if not CAPSOLVER_API_KEY:
        return None
    sitekey = (SII_RECAPTCHA_SITEKEY or SII_RECAPTCHA_SITEKEY_DEFAULT or "").strip() or SII_RECAPTCHA_SITEKEY_DEFAULT
    # ProxyLess: CapSolver resuelve desde su IP. Si usamos proxy, Oxylabs rechaza la conexión desde sus workers.
    task = {
        "type": "ReCaptchaV3EnterpriseTaskProxyLess",
        "websiteURL": SII_CONSULTA_URL,
        "websiteKey": sitekey,
        "pageAction": SII_RECAPTCHA_PAGE_ACTION,
    }
    proxy_str = None  # no pasar proxy a CapSolver

    create_url = f"{CAPSOLVER_API_URL}/createTask"
    result_url = f"{CAPSOLVER_API_URL}/getTaskResult"
    try:
        r = requests.post(create_url, json={"clientKey": CAPSOLVER_API_KEY, "task": task}, timeout=15)
        if r.status_code != 200:
            try:
                err_body = r.json()
                logger.warning(
                    "[SII] CapSolver createTask %s: errorId=%s errorCode=%s errorDescription=%s",
                    r.status_code,
                    err_body.get("errorId"),
                    err_body.get("errorCode"),
                    err_body.get("errorDescription", r.text[:200]),
                )
            except Exception:
                logger.warning("[SII] CapSolver createTask error: %s %s", r.status_code, r.text[:300])
            return None
        data = r.json()
    except requests.RequestException as e:
        logger.warning("[SII] CapSolver createTask error: %s", e)
        return None
    if data.get("errorId", 0) != 0:
        logger.warning("[SII] CapSolver createTask error: %s", data.get("errorDescription", data))
        return None
    task_id = data.get("taskId")
    if not task_id:
        logger.warning("[SII] CapSolver no devolvió taskId: %s", data)
        return None

    for _ in range(30):
        time.sleep(1)
        try:
            r = requests.post(result_url, json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id}, timeout=15)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.warning("[SII] CapSolver getTaskResult error: %s", e)
            return None
        if data.get("errorId", 0) != 0:
            logger.warning("[SII] CapSolver getTaskResult error: %s", data.get("errorDescription", data))
            return None
        status = data.get("status")
        if status == "ready":
            solution = data.get("solution") or {}
            token = solution.get("gRecaptchaResponse")
            if token and isinstance(token, str) and len(token) > 20:
                logger.info("[SII] Token obtenido vía CapSolver (proxy=%s)", bool(proxy_str))
                return token
            logger.warning("[SII] CapSolver solution sin gRecaptchaResponse: %s", solution)
            return None
        if status == "failed":
            logger.warning("[SII] CapSolver task failed: %s", data)
            return None
    logger.warning("[SII] CapSolver getTaskResult timeout")
    return None


def _crear_proxy_auth_extension(proxy_host: str, proxy_port: str, proxy_user: str, proxy_pass: str, out_dir: Path) -> str:
    """
    Crea una extensión de Chrome para autenticación de proxy (Oxylabs u otro proxy residencial).
    """
    plugin_path = out_dir / "proxy_auth_plugin.zip"
    manifest_json = json.dumps({
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Oxylabs Proxy",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": {"scripts": ["background.js"]},
        "minimum_chrome_version": "22.0.0"
    })
    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{proxy_host}",
                port: parseInt({proxy_port})
            }},
            bypassList: ["localhost"]
        }}
    }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{
                authCredentials: {{
                    username: "{proxy_user}",
                    password: "{proxy_pass}"
                }}
            }};
        }},
        {{urls: ["<all_urls>"]}},
        ["blocking"]
    );
    """
    with zipfile.ZipFile(plugin_path, "w", zipfile.ZIP_DEFLATED) as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    return str(plugin_path)


# ----------------------------
# Limpieza de memoria / disco (mantener)
# ----------------------------
def _cleanup_old_sessions() -> int:
    """
    Borra directorios de sesión Chrome en VM_TEMP_BASE más viejos que VM_CLEANUP_MAX_AGE_MINUTES.
    Devuelve cantidad de directorios eliminados.
    """
    if not VM_TEMP_BASE.exists():
        return 0
    now = time.time()
    max_age_sec = VM_CLEANUP_MAX_AGE_MINUTES * 60
    removed = 0
    try:
        for p in VM_TEMP_BASE.iterdir():
            if not p.is_dir():
                continue
            if p.name == "sii_main_profile":
                continue
            try:
                age = now - p.stat().st_mtime
                if age > max_age_sec:
                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
                    logger.info("Limpieza VM: borrado sesión antigua %s", p.name)
            except OSError as e:
                logger.warning("No se pudo borrar %s: %s", p, e)
    except OSError as e:
        logger.warning("Error listando %s: %s", VM_TEMP_BASE, e)
    return removed


def _maybe_run_periodic_cleanup() -> None:
    """Cada VM_CLEANUP_EVERY_N_REQUESTS requests ejecuta limpieza de sesiones viejas (en background)."""
    global _request_count
    with _request_count_lock:
        _request_count += 1
        n = _request_count
    if n % VM_CLEANUP_EVERY_N_REQUESTS == 0:
        try:
            removed = _cleanup_old_sessions()
            if removed > 0:
                logger.info("Limpieza periódica VM: %d directorios de sesión eliminados", removed)
        except Exception as e:
            logger.warning("Error en limpieza periódica VM: %s", e)


# ----------------------------
# MODELS
# ----------------------------
class GirosRequest(BaseModel):
    rut: str


def _normalizar_rut(rut: str) -> str:
    """Quita puntos y deja formato 12345678-9."""
    if not rut:
        return ""
    s = rut.strip().upper().replace(".", "").replace(" ", "")
    if "-" not in s and len(s) >= 2 and s[-1] in "0123456789K":
        return f"{s[:-1]}-{s[-1]}"
    return s


def _rut_num_y_dv(rut_normalizado: str) -> tuple:
    """Devuelve (numero_sin_dv, dv) para la API getConsultaData."""
    if not rut_normalizado or "-" not in rut_normalizado:
        return ("", "")
    num, dv = rut_normalizado.rsplit("-", 1)
    return (num.replace(".", "").strip(), dv.strip().upper())


def _parsear_fecha_sii(texto: str) -> Optional[datetime]:
    """Intenta parsear fecha tipo dd-mm-yyyy o similar."""
    if not texto or not texto.strip():
        return None
    texto = texto.strip()
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", texto)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d)
        except ValueError:
            return None
    return None


# ----------------------------
# DRIVER (una sola vez al inicio)
# ----------------------------
def _crear_driver_uc():
    """Crea un driver con undetected_chromedriver (Google no lo detecta como bot)."""
    if not UC_AVAILABLE or uc is None:
        return None, None
    VM_TEMP_BASE.mkdir(parents=True, exist_ok=True)
    profile_dir = VM_TEMP_BASE / "sii_main_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    options = uc.ChromeOptions()
    if os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes"):
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    proxy_cfg = _get_proxy_config()
    if proxy_cfg:
        try:
            ext_path = _crear_proxy_auth_extension(
                proxy_cfg["host"], proxy_cfg["port"],
                proxy_cfg["username"], proxy_cfg["password"],
                profile_dir,
            )
            options.add_argument(f"--load-extension={ext_path}")
            logger.info("[SII] Proxy residencial configurado (UC): %s:%s", proxy_cfg["host"], proxy_cfg["port"])
        except Exception as e:
            logger.warning("[SII] No se pudo crear extensión de proxy para UC: %s", e)
    elif not SII_SCRAPER_USE_PROXY:
        logger.info("[SII] Proxy desactivado (SII_SCRAPER_USE_PROXY=false)")

    try:
        kwargs = {"options": options, "user_data_dir": str(profile_dir)}
        if UC_VERSION_MAIN > 0:
            kwargs["version_main"] = UC_VERSION_MAIN
            logger.info("[SII] UC usando version_main=%s", UC_VERSION_MAIN)
        dr = uc.Chrome(**kwargs)
        dr.set_script_timeout(SCRIPT_TIMEOUT_SEC)
        dr.set_page_load_timeout(max(60, SCRIPT_TIMEOUT_SEC))
        logger.info("[SII] Navegador UC listo (perfil persistente: %s)", profile_dir)
        return dr, profile_dir
    except Exception as e:
        logger.error("[SII] Error al iniciar UC: %s", e)
        return None, None


def _crear_driver(headless: bool = True):
    """
    Crea el driver de Chrome usando un directorio temporal propio.
    Returns: (driver, temp_dir_path) o (None, None).
    """
    if not SELENIUM_AVAILABLE:
        return None, None
    VM_TEMP_BASE.mkdir(parents=True, exist_ok=True)
    session_dir_path = VM_TEMP_BASE / f"chrome_{uuid4().hex[:12]}"
    try:
        session_dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("No se pudo crear directorio de sesión %s: %s", session_dir_path, e)
        return None, None

    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-data-dir={session_dir_path}")
    options.add_argument("--disk-cache-size=0")
    options.add_argument("--disable-application-cache")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    proxy_cfg = _get_proxy_config()
    if proxy_cfg:
        try:
            ext_path = _crear_proxy_auth_extension(
                proxy_cfg["host"], proxy_cfg["port"],
                proxy_cfg["username"], proxy_cfg["password"],
                session_dir_path
            )
            options.add_argument(f"--load-extension={ext_path}")
            logger.info("[SII] Proxy residencial configurado (extensión auth): %s:%s", proxy_cfg["host"], proxy_cfg["port"])
        except Exception as e:
            logger.warning("[SII] No se pudo crear extensión de proxy, continuando sin proxy: %s", e)
    elif not SII_SCRAPER_USE_PROXY:
        logger.info("[SII] Proxy desactivado (SII_SCRAPER_USE_PROXY=false)")

    try:
        service = Service(ChromeDriverManager().install())
        dr = webdriver.Chrome(service=service, options=options)
        dr.set_page_load_timeout(60)
        # Timeout alto para reCAPTCHA con proxy (Oxylabs puede ser lento)
        script_timeout_sec = 120
        dr.set_script_timeout(script_timeout_sec)
        logger.info("[SII] Script timeout del driver: %ds", script_timeout_sec)
        dr.implicitly_wait(5)
        return dr, session_dir_path
    except Exception as e:
        logger.exception("Error creando Chrome driver: %s", e)
        try:
            shutil.rmtree(session_dir_path, ignore_errors=True)
        except Exception:
            pass
        return None, None


def iniciar_navegador() -> None:
    """Inicializa el navegador global una sola vez y carga la página del SII."""
    global driver, session_dir
    if SII_USE_UC:
        driver, session_dir = _crear_driver_uc()
    else:
        driver, session_dir = _crear_driver(headless=True)
    if not driver:
        logger.error("[SII] No se pudo crear el driver Chrome")
        return
    driver.get(SII_CONSULTA_URL)
    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return window.grecaptcha && window.grecaptcha.enterprise")
    )
    logger.info("[SII] Navegador SII listo")


def _generar_un_token() -> Optional[str]:
    """Genera un solo token (mismo script que el thread). Para precalentar al inicio."""
    global driver
    if not driver:
        return None
    sitekey = (SII_RECAPTCHA_SITEKEY or SII_RECAPTCHA_SITEKEY_DEFAULT or "").strip() or SII_RECAPTCHA_SITEKEY_DEFAULT
    try:
        if SII_USE_UC:
            driver.set_script_timeout(60)
            token = driver.execute_async_script(
                """
                const sitekey = arguments[0];
                const action = arguments[1];
                const callback = arguments[arguments.length - 1];
                if (typeof grecaptcha === 'undefined' || !grecaptcha.enterprise) { callback(null); return; }
                grecaptcha.enterprise.ready(function() {
                    grecaptcha.enterprise.execute(sitekey, { action: action })
                        .then(function(t) { callback(t); })
                        .catch(function() { callback(null); });
                });
                """,
                sitekey,
                SII_RECAPTCHA_PAGE_ACTION,
            )
        else:
            driver.set_script_timeout(SCRIPT_TIMEOUT_SEC)
            token = driver.execute_async_script(
                """
                const sitekey = arguments[0];
                const action = arguments[1];
                const callback = arguments[arguments.length - 1];
                const fallbackMs = arguments[2];
                var done = false;
                function finish(t) { if (done) return; done = true; callback(t || null); }
                setTimeout(function() { finish(null); }, fallbackMs);
                if (typeof grecaptcha === 'undefined' || !grecaptcha.enterprise) { finish(null); return; }
                grecaptcha.enterprise.ready(function() {
                    grecaptcha.enterprise.execute(sitekey, { action: action })
                        .then(function(t) { finish(t); }).catch(function() { finish(null); });
                });
                """,
                sitekey,
                SII_RECAPTCHA_PAGE_ACTION,
                JS_FALLBACK_MS,
            )
        if token and isinstance(token, str) and len(token) > 20 and not token.startswith("error_"):
            return token
    except Exception as e:
        logger.warning("[SII] Precalentar token: %s", e)
    return None


# ----------------------------
# GENERADOR DE TOKENS (thread)
# ----------------------------
JS_FALLBACK_MS = 115000  # callback antes del timeout de Selenium (solo Selenium estándar)


def token_generator() -> None:
    """Thread que genera tokens reCAPTCHA. Con UC reinicia el driver si falla."""
    global driver, session_dir
    sitekey = (SII_RECAPTCHA_SITEKEY or SII_RECAPTCHA_SITEKEY_DEFAULT or "").strip()
    if not sitekey:
        sitekey = SII_RECAPTCHA_SITEKEY_DEFAULT

    while True:
        if SII_USE_UC:
            if not driver:
                logger.info("[SII] Iniciando/Reiniciando navegador UC...")
                driver, session_dir = _crear_driver_uc()
                if driver:
                    try:
                        driver.get(SII_CONSULTA_URL)
                        WebDriverWait(driver, 30).until(
                            lambda d: d.execute_script("return window.grecaptcha && window.grecaptcha.enterprise")
                        )
                    except Exception as e:
                        logger.warning("[SII] Error cargando SII en UC: %s", e)
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = None
                else:
                    time.sleep(10)
                    continue

            # Verificación de salud del driver antes de ejecutar (evita RemoteDisconnected)
            try:
                _ = driver.current_url
            except Exception:
                logger.warning("[SII] Driver perdido, reiniciando...")
                driver = None
                continue

            try:
                if token_queue.full():
                    time.sleep(5)
                    continue
                token = driver.execute_async_script(
                    """
                    const sitekey = arguments[0];
                    const action = arguments[1];
                    const callback = arguments[arguments.length - 1];
                    if (typeof grecaptcha === 'undefined' || !grecaptcha.enterprise) {
                        callback('error_no_api');
                        return;
                    }
                    grecaptcha.enterprise.ready(function() {
                        grecaptcha.enterprise.execute(sitekey, { action: action })
                            .then(function(t) { callback(t); })
                            .catch(function(e) { callback('error_' + e); });
                    });
                    """,
                    sitekey,
                    SII_RECAPTCHA_PAGE_ACTION,
                )
                if token and isinstance(token, str) and not token.startswith("error_"):
                    token_queue.put(token)
                else:
                    logger.warning("[SII] ReCAPTCHA devolvió: %s", token)
                    time.sleep(2)
            except Exception as e:
                logger.error("[SII] Error en el loop de tokens (UC): %s", e)
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
                time.sleep(5)
        else:
            try:
                if token_queue.full():
                    time.sleep(1)
                    continue
                if not driver:
                    time.sleep(2)
                    continue
                try:
                    driver.set_script_timeout(SCRIPT_TIMEOUT_SEC)
                except Exception:
                    pass
                token = driver.execute_async_script(
                    """
                    const sitekey = arguments[0];
                    const action = arguments[1];
                    const callback = arguments[arguments.length - 1];
                    const fallbackMs = arguments[2];
                    var done = false;
                    function finish(t) {
                        if (done) return;
                        done = true;
                        callback(t || null);
                    }
                    setTimeout(function() { finish(null); }, fallbackMs);
                    if (typeof grecaptcha === 'undefined' || !grecaptcha.enterprise) {
                        finish(null);
                        return;
                    }
                    grecaptcha.enterprise.ready(function() {
                        grecaptcha.enterprise.execute(sitekey, { action: action })
                            .then(function(t) { finish(t); })
                            .catch(function() { finish(null); });
                    });
                    """,
                    sitekey,
                    SII_RECAPTCHA_PAGE_ACTION,
                    JS_FALLBACK_MS,
                )
                if token and isinstance(token, str) and len(token) > 20:
                    token_queue.put(token)
            except Exception as e:
                err_str = str(e)
                if "script timeout" in err_str.lower():
                    logger.warning("[SII] Token: script timeout (aumentar SCRIPT_TIMEOUT_SEC si el proxy es lento)")
                elif "Connection" in err_str or "Remote" in err_str:
                    logger.warning("[SII] Token: Chrome/driver no disponible (%s)", err_str[:80])
                else:
                    logger.error("[SII] Error generando token: %s", e)
                time.sleep(2)


# ----------------------------
# CONSULTA API SII (requests, sin Chrome por RUT)
# ----------------------------
def _consultar_sii_api(rut: str) -> Dict[str, Any]:
    """
    Consulta el API getConsultaData del SII usando un token de la cola y requests.
    Mismo proxy que Selenium (Oxylabs) si está configurado.
    Returns: {"success", "activities", "not_found", "error"}
    """
    rut = _normalizar_rut(rut)
    if not rut:
        return {"success": False, "activities": [], "not_found": False, "error": "RUT vacío o inválido"}

    rut_num, dv = _rut_num_y_dv(rut)
    if not rut_num or not dv:
        return {"success": False, "activities": [], "not_found": False, "error": "RUT inválido"}

    try:
        if CAPSOLVER_API_KEY:
            token = _get_token_capsolver()
            if not token:
                return {"success": False, "activities": [], "not_found": False, "error": "CapSolver no devolvió token"}
        else:
            token = token_queue.get(timeout=125)
    except queue.Empty:
        logger.error("[SII] Timeout esperando token de la cola")
        return {"success": False, "activities": [], "not_found": False, "error": "No hay tokens reCAPTCHA disponibles (timeout)"}

    payload = {
        "rut": rut_num,
        "dv": dv,
        "reAction": SII_RECAPTCHA_PAGE_ACTION,
        "reToken": token,
    }

    proxies = _proxies_for_requests()
    try:
        r = requests.post(
            SII_GET_CONSULTA_DATA_URL,
            json=payload,
            timeout=20,
            proxies=proxies,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.warning("[SII] Error request getConsultaData: %s", e)
        return {"success": False, "activities": [], "not_found": False, "error": str(e)}

    if data.get("captchaInvalido") is True:
        logger.warning("[SII] API devolvió captchaInvalido=true para RUT %s", rut)
        return {"success": False, "activities": [], "not_found": False, "error": "reCAPTCHA rechazado por el SII"}

    giros = data.get("girosNegocio") or []
    activities = []
    for g in giros:
        activities.append({
            "code": str(g.get("codigo", "")).strip(),
            "description": str(g.get("descripcion", "")).strip(),
            "category": str(g.get("categoriaTributaria", "")).strip(),
            "isVatSubject": str(g.get("indicadorAfectoIva", "")).upper() in ("SI", "SÍ"),
            "fecha": str(g.get("fechaInicio", "")).strip(),
            "startDate": _parsear_fecha_sii(str(g.get("fechaInicio", ""))),
            "lastUpdatedAt": datetime.utcnow(),
        })

    registrado = data.get("registrado", True)
    tiene_giros = data.get("tieneGirosNegocio", True)
    not_found = not activities and (not registrado or not tiene_giros)

    # Uso de proxy (mismo patrón que DT): estimación MB por request para Oxylabs
    proxy_cfg = _get_proxy_config()
    proxy_usage = None
    if proxy_cfg:
        estimated_mb = round(SII_ESTIMATED_MB_PER_REQUEST, 4)
        proxy_usage = {
            "proxy_used": True,
            "proxy_server": f"{proxy_cfg['host']}:{proxy_cfg['port']}",
            "estimated_mb": estimated_mb,
        }
        with _proxy_usage_lock:
            _proxy_usage_stats["requests_count"] += 1
            _proxy_usage_stats["total_estimated_mb"] += estimated_mb

    logger.info("[SII] RUT %s: %d actividades desde API (%s)", rut, len(activities), "CapSolver" if CAPSOLVER_API_KEY else "token pool")
    return {
        "success": True,
        "activities": activities,
        "not_found": not_found,
        "error": None,
        "proxy_usage": proxy_usage,
    }


# ----------------------------
# STARTUP / SHUTDOWN
# ----------------------------
@app.on_event("startup")
def startup():
    """Al iniciar: si CapSolver está configurado no se usa navegador; si no, se inicia navegador + cola de tokens."""
    try:
        removed = _cleanup_old_sessions()
        if removed > 0:
            logger.info("Limpieza al inicio: %d directorios de sesión eliminados", removed)
        VM_TEMP_BASE.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("Limpieza al inicio: %s", e)

    if CAPSOLVER_API_KEY:
        pc = _get_proxy_config()
        if pc:
            # Log usuario (ocultar pass) para verificar que env.proxy se leyó bien; 401 = credenciales rechazadas por Oxylabs
            u = (pc.get("username") or "").strip()
            user_log = (u[:8] + "***") if len(u) > 8 else ("***" if u else "?")
            logger.info(
                "[SII] CapSolver configurado: tokens vía API (sin navegador). Proxy: %s:%s user=%s",
                pc.get("host"), pc.get("port"), user_log,
            )
        else:
            logger.info("[SII] CapSolver configurado: tokens vía API (sin navegador). Proxy Oxylabs: False")
        return

    iniciar_navegador()
    if driver:
        logger.info("[SII] Precalentando primer token (timeout %ds)...", SCRIPT_TIMEOUT_SEC)
        primer_token = _generar_un_token()
        if primer_token:
            token_queue.put(primer_token)
            logger.info("[SII] Primer token en cola (precalentado)")
        else:
            logger.warning("[SII] No se pudo precalentar token; el thread intentará llenar la cola")
        t = threading.Thread(target=token_generator, daemon=True)
        t.start()
        logger.info("[SII] Generador de tokens iniciado")
    else:
        logger.error("[SII] No se pudo iniciar navegador; /giros fallará hasta reinicio")


@app.on_event("shutdown")
def shutdown():
    """Al apagar: cerrar navegador. No borrar sii_main_profile (perfil persistente UC)."""
    global driver, session_dir
    if driver:
        try:
            driver.quit()
            logger.info("[SII] Navegador cerrado")
        except Exception as e:
            logger.warning("Error al cerrar driver: %s", e)
        driver = None
    if session_dir and session_dir.exists():
        if session_dir.name == "sii_main_profile":
            logger.info("[SII] Perfil UC persistente conservado: %s", session_dir)
        else:
            try:
                shutil.rmtree(session_dir, ignore_errors=True)
                logger.info("[SII] Sesión borrada: %s", session_dir)
            except Exception as e:
                logger.warning("No se pudo borrar sesión %s: %s", session_dir, e)
    session_dir = None


# ----------------------------
# ENDPOINTS
# ----------------------------
def _get_proxy_usage_stats() -> Dict[str, Any]:
    """Estadísticas de uso de proxy (mismo patrón que DT)."""
    with _proxy_usage_lock:
        return {
            "requests_count": _proxy_usage_stats["requests_count"],
            "total_estimated_mb": round(_proxy_usage_stats["total_estimated_mb"], 4),
            "last_reset": _proxy_usage_stats["last_reset"],
        }


@app.get("/health")
async def health():
    proxy_cfg = _get_proxy_config()
    with _proxy_usage_lock:
        total_mb = round(_proxy_usage_stats["total_estimated_mb"], 4)
    return {
        "status": "healthy",
        "service": "sii-scraper-vm",
        "selenium": SELENIUM_AVAILABLE,
        "undetected_chrome": UC_AVAILABLE,
        "use_uc": SII_USE_UC,
        "capsolver": bool(CAPSOLVER_API_KEY),
        "proxy_configured": proxy_cfg is not None,
        "proxy_server": (f"{proxy_cfg['host']}:{proxy_cfg['port']}" if proxy_cfg else None),
        "proxy_usage_estimated_mb_total": total_mb,
    }


@app.post("/api/v1/cleanup")
async def cleanup_disk():
    """
    Fuerza limpieza de directorios de sesión antiguos (liberar espacio).
    """
    try:
        removed = _cleanup_old_sessions()
        return {"ok": True, "removed_sessions": removed, "message": f"Eliminados {removed} directorios de sesión"}
    except Exception as e:
        logger.exception("Error en cleanup manual: %s", e)
        return {"ok": False, "removed_sessions": 0, "error": str(e)}


@app.get("/api/v1/proxy-stats")
async def proxy_stats():
    """
    Uso estimado de proxy (Oxylabs). Mismo concepto que en la API de verificación DT.
    SII: ~0.02 MB por consulta (solo POST getConsultaData). DT: ~0.5-1 MB por verificación (página + reCAPTCHA v2 + PDF).
    """
    return _get_proxy_usage_stats()


@app.post("/api/v1/sii/giros")
async def obtener_giros(body: GirosRequest) -> Dict[str, Any]:
    """
    Consulta el SII por RUT y devuelve la lista de actividades económicas (giros).
    Usa 1 navegador + cola de tokens + requests (sin abrir Chrome por RUT).
    """
    rut = (body.rut or "").strip()
    if not rut:
        raise HTTPException(status_code=400, detail="rut es requerido")

    _maybe_run_periodic_cleanup()

    if not CAPSOLVER_API_KEY and not driver:
        raise HTTPException(status_code=503, detail="Scraper no disponible (navegador no iniciado)")

    logger.info("[SII] POST /giros recibido RUT=%s", rut)
    result = _consultar_sii_api(rut)
    logger.info("[SII] POST /giros RUT=%s -> success=%s activities=%d not_found=%s", rut, result["success"], len(result.get("activities", [])), result.get("not_found"))

    if result.get("error") and "captcha" in result["error"].lower():
        raise HTTPException(status_code=429, detail=result["error"])
    if result.get("error") and "timeout" in result["error"].lower():
        raise HTTPException(status_code=503, detail=result["error"])

    out = {
        "rut": _normalizar_rut(rut),
        "activities": result["activities"],
        "economicActivities": result["activities"],
        "not_found": result["not_found"],
        "error": result.get("error"),
        "success": result["success"],
    }
    if result.get("proxy_usage") is not None:
        out["proxy_usage"] = result["proxy_usage"]
    return out


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
