"""
API de scraping SII para VM.
Expone POST /api/v1/sii/giros con {"rut": "..."} y devuelve las actividades económicas.
Ejecutar en VM para no bloquear IPs (usar Oxylabs u otro proxy si se desea).

Limpieza de espacio: cada sesión de Chrome usa un directorio temporal que se borra
al terminar; además se ejecuta limpieza periódica para evitar llenar el disco
(carga inicial 1000 RUTs, actualizaciones, consultas individuales).
"""

import os
import re
import time
import shutil
import logging
import threading
import zipfile
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

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

app = FastAPI(title="CarrierSync VM - SII Scraper", version="1.0.0")

OXY_USER = os.getenv("OXY_USER", "")
OXY_PASS = os.getenv("OXY_PASS", "")
OXY_HOST = os.getenv("OXY_HOST", "unblock.oxylabs.io")
OXY_PORT = os.getenv("OXY_PORT", "60000")

# Proxy alternativo por env (compatible con ProxyManager: HTTP_PROXY + PROXY_USER / PROXY_PASSWORD)
HTTP_PROXY = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

# Desactivar proxy para pruebas (SII_SCRAPER_USE_PROXY=false en la VM)
SII_SCRAPER_USE_PROXY = os.getenv("SII_SCRAPER_USE_PROXY", "true").lower() not in ("false", "0", "no")

# 2Captcha (misma API key que gestion_documental / verification_api)
API_KEY_2CAPTCHA = os.getenv("API_KEY_2CAPTCHA", "e716e4f00d5e2225bcd8ed2a04981fe3")
SII_RECAPTCHA_SITEKEY = os.getenv("SII_RECAPTCHA_SITEKEY", "").strip()
SII_CONSULTA_URL = "https://www2.sii.cl/stc/noauthz"


def _get_proxy_config() -> Optional[Dict[str, str]]:
    """
    Devuelve configuración de proxy para uso con extensión Chrome.
    Prioridad: OXY_* > HTTP_PROXY + PROXY_USER/PROXY_PASSWORD.
    Si SII_SCRAPER_USE_PROXY=false, no usa proxy (para probar desde la VM sin proxy).
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


def _crear_proxy_auth_extension(proxy_host: str, proxy_port: str, proxy_user: str, proxy_pass: str, out_dir: Path) -> str:
    """
    Crea una extensión de Chrome para autenticación de proxy (Oxylabs u otro proxy residencial).
    Chrome no soporta user/pass en --proxy-server; la extensión responde a onAuthRequired.
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

# --- Limpieza de espacio en disco (evitar llenar /tmp con 1000+ RUTs) ---
# Directorio base para temporales de Chrome; se borra cada sesión y se hace limpieza periódica
VM_TEMP_BASE = Path(os.getenv("VM_TEMP_BASE_DIR", "/tmp/carriersync_scraper"))
# Borrar directorios de sesión más viejos que N minutos (por si un run crasheó sin limpiar)
VM_CLEANUP_MAX_AGE_MINUTES = int(os.getenv("VM_CLEANUP_MAX_AGE_MINUTES", "15"))
# Ejecutar limpieza de residuos cada N requests
VM_CLEANUP_EVERY_N_REQUESTS = int(os.getenv("VM_CLEANUP_EVERY_N_REQUESTS", "50"))

_request_count = 0
_request_count_lock = threading.Lock()


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


def _rut_con_puntos(rut_normalizado: str) -> str:
    """Formatea RUT con puntos de miles para el SII (ej: 17807161-0 -> 17.807.161-0)."""
    if not rut_normalizado or "-" not in rut_normalizado:
        return rut_normalizado or ""
    numero, dv = rut_normalizado.rsplit("-", 1)
    numero = numero.replace(".", "")
    if not numero.isdigit():
        return rut_normalizado
    partes = []
    while numero:
        partes.append(numero[-3:])
        numero = numero[:-3]
    return ".".join(reversed(partes)) + "-" + dv.upper()


def _parsear_fecha_sii(texto: str) -> Optional[datetime]:
    """Intenta parsear fecha tipo dd-mm-yyyy o similar."""
    if not texto or not texto.strip():
        return None
    texto = texto.strip()
    # dd-mm-yyyy o dd/mm/yyyy
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", texto)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d)
        except ValueError:
            return None
    return None


def _resolver_captcha_2captcha(website_url: str, website_key: str) -> Optional[str]:
    """Resuelve reCAPTCHA con 2captcha (mismo esquema que gestion_documental/verification_api)."""
    if not API_KEY_2CAPTCHA or not website_key:
        return None
    logger.info("[SII] Solicitando resolución a 2Captcha...")
    payload = {
        "clientKey": API_KEY_2CAPTCHA,
        "task": {
            "type": "RecaptchaV2EnterpriseTaskProxyless",
            "websiteURL": website_url,
            "websiteKey": website_key,
            "isInvisible": False,
        },
    }
    try:
        res = requests.post("https://api.2captcha.com/createTask", json=payload, timeout=30).json()
        if res.get("errorId") != 0:
            logger.error("[SII] Error 2captcha createTask: %s", res)
            return None
        task_id = res.get("taskId")
        max_attempts = 60
        for attempt in range(max_attempts):
            time.sleep(5)
            status = requests.post(
                "https://api.2captcha.com/getTaskResult",
                json={"clientKey": API_KEY_2CAPTCHA, "taskId": task_id},
                timeout=30,
            ).json()
            if status.get("status") == "ready":
                token = status.get("solution", {}).get("gRecaptchaResponse")
                logger.info("[SII] reCAPTCHA resuelto por 2Captcha")
                return token
            if status.get("errorId") != 0:
                logger.error("[SII] Error 2captcha getTaskResult: %s", status)
                return None
            if attempt % 6 == 0:
                logger.info("[SII] Esperando resolución reCAPTCHA... (%ds)", (attempt + 1) * 5)
        logger.error("[SII] Timeout esperando resolución reCAPTCHA")
        return None
    except Exception as e:
        logger.exception("[SII] Error al resolver reCAPTCHA: %s", e)
        return None


def _inyectar_token_captcha(driver, token: str) -> None:
    """Inyecta token reCAPTCHA y ejecuta callback (igual que verification_api)."""
    logger.info("[SII] Inyectando token reCAPTCHA...")
    script_js = """
    var token = arguments[0];
    try {
        var area = document.getElementById('g-recaptcha-response');
        if (area) { area.value = token; area.innerHTML = token; }
        if (typeof (___grecaptcha_cfg) !== 'undefined') {
            for (let i in ___grecaptcha_cfg.clients) {
                let client = ___grecaptcha_cfg.clients[i];
                for (let prop in client) {
                    if (client[prop] && typeof client[prop].callback === 'function') {
                        client[prop].callback(token);
                    }
                }
            }
        }
        if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {
            try { grecaptcha.enterprise.getResponse && grecaptcha.enterprise.getResponse(); } catch(e){}
        }
    } catch (e) { console.error(e); }
    """
    driver.execute_script(script_js, token)
    driver.execute_script(
        """
        var t = arguments[0];
        var el = document.getElementById('g-recaptcha-response');
        if (el) {
            el.value = t;
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
    """,
        token,
    )
    logger.info("[SII] Token reCAPTCHA inyectado")


def _obtener_sitekey_sii(driver) -> Optional[str]:
    """Obtiene el sitekey de reCAPTCHA del SII desde la página o env."""
    if SII_RECAPTCHA_SITEKEY:
        return SII_RECAPTCHA_SITEKEY
    try:
        sitekey = driver.execute_script(
            """
            var el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');
            if (typeof ___grecaptcha_cfg !== 'undefined') {
                var clients = ___grecaptcha_cfg.clients || {};
                for (var k in clients) {
                    var c = clients[k];
                    if (c && c.K && c.K.sitekey) return c.K.sitekey;
                }
            }
            return null;
        """
        )
        return (sitekey or "").strip() or None
    except Exception as e:
        logger.warning("[SII] No se pudo obtener sitekey del DOM: %s", e)
    return None


def _cleanup_old_sessions() -> int:
    """
    Borra directorios de sesión Chrome en VM_TEMP_BASE más viejos que VM_CLEANUP_MAX_AGE_MINUTES.
    Útil cuando un run crasheó sin hacer cleanup. Devuelve cantidad de directorios eliminados.
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


def _crear_driver(headless: bool = True):
    """
    Crea el driver de Chrome usando un directorio temporal propio que debe borrarse después.
    Returns: (driver, temp_dir_path) o (None, None). Quien llama debe hacer driver.quit() y luego
    shutil.rmtree(temp_dir_path, ignore_errors=True).
    """
    if not SELENIUM_AVAILABLE:
        return None, None
    VM_TEMP_BASE.mkdir(parents=True, exist_ok=True)
    session_dir = VM_TEMP_BASE / f"chrome_{uuid4().hex[:12]}"
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("No se pudo crear directorio de sesión %s: %s", session_dir, e)
        return None, None

    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    # Reducir uso de disco: user-data-dir en nuestro temp y desactivar cachés
    options.add_argument(f"--user-data-dir={session_dir}")
    options.add_argument("--disk-cache-size=0")
    options.add_argument("--disable-application-cache")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    proxy_cfg = _get_proxy_config()
    if proxy_cfg:
        # Proxy residencial (Oxylabs, etc.) requiere autenticación; Chrome no la soporta por argumento.
        # Cargamos una extensión que inyecta user/pass en onAuthRequired (igual que gestion_documental).
        try:
            ext_path = _crear_proxy_auth_extension(
                proxy_cfg["host"], proxy_cfg["port"],
                proxy_cfg["username"], proxy_cfg["password"],
                session_dir
            )
            # Igual que gestion_documental/verification_api: solo extensión, sin --proxy-server.
            # La extensión configura el proxy con chrome.proxy.settings.set().
            options.add_argument(f"--load-extension={ext_path}")
            logger.info("[SII] Proxy residencial configurado (extensión auth): %s:%s", proxy_cfg["host"], proxy_cfg["port"])
        except Exception as e:
            logger.warning("[SII] No se pudo crear extensión de proxy, continuando sin proxy: %s", e)
    elif not SII_SCRAPER_USE_PROXY:
        logger.info("[SII] Proxy desactivado (SII_SCRAPER_USE_PROXY=false)")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # Con proxy la carga puede ser más lenta; timeouts largos evitan fallos sin mensaje
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(5)
        return driver, session_dir
    except Exception as e:
        logger.exception("Error creando Chrome driver: %s", e)
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass
        return None, None


def _extraer_giros_sii(rut: str) -> Dict[str, Any]:
    """
    Abre SII, ingresa RUT, extrae tabla de actividades económicas.
    Usa un directorio temporal por sesión que se borra al terminar para no llenar el disco.
    Returns: {"success", "activities", "not_found", "error"}
    """
    rut = _normalizar_rut(rut)
    if not rut:
        logger.info("[SII] RUT vacío o inválido, rechazando")
        return {"success": False, "activities": [], "not_found": False, "error": "RUT vacío o inválido"}

    rut_para_sii = _rut_con_puntos(rut)
    logger.info("[SII] Inicio extracción RUT normalizado=%s, enviando al formulario=%s", rut, rut_para_sii)

    _maybe_run_periodic_cleanup()

    driver, session_dir = _crear_driver(headless=True)
    if not driver:
        logger.error("[SII] No se pudo crear el driver Chrome")
        return {"success": False, "activities": [], "not_found": False, "error": "Driver Chrome no disponible"}

    activities = []
    not_found = False
    error_msg = None

    try:
        driver.get("https://www2.sii.cl/stc/noauthz")
        # Con proxy residencial la primera carga del SII puede tardar mucho; dar 60 s al input
        wait = WebDriverWait(driver, 60)

        # Ingresar RUT en formato que espera el SII: 17.807.161-0 (con puntos de miles)
        input_rut = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.rut-form")))
        input_rut.clear()
        input_rut.send_keys(rut_para_sii)
        logger.info("[SII] RUT escrito en input: %s", rut_para_sii)
        time.sleep(0.5)

        # Resolver reCAPTCHA con 2Captcha antes de enviar (mismo esquema que gestion_documental)
        sitekey = _obtener_sitekey_sii(driver)
        if API_KEY_2CAPTCHA and sitekey:
            for _ in range(3):
                loaded = driver.execute_script(
                    "return typeof grecaptcha !== 'undefined' || (typeof window.grecaptcha !== 'undefined' && window.grecaptcha && window.grecaptcha.enterprise);"
                )
                if loaded:
                    break
                time.sleep(3)
            token = _resolver_captcha_2captcha(SII_CONSULTA_URL, sitekey)
            if token:
                _inyectar_token_captcha(driver, token)
                time.sleep(2)
            else:
                logger.warning("[SII] 2Captcha no devolvió token, continuando sin él (puede fallar por ReCaptcha)")
        elif not sitekey:
            logger.debug("[SII] Sin SII_RECAPTCHA_SITEKEY ni sitekey en página; no se usa 2Captcha")

        # Consultar Situación Tributaria
        btn_consultar = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@value='Consultar Situación Tributaria']"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", btn_consultar)
        driver.execute_script("arguments[0].click();", btn_consultar)
        logger.info("[SII] Click en Consultar Situación Tributaria, esperando carga...")
        time.sleep(6)  # SPA: dar tiempo a que el SII renderice resultados (proxy/headless puede ser lento)

        # Detección de rechazo por reCAPTCHA (SII bloquea headless/proxy)
        page_source = driver.page_source or ""
        if "no autorizado por ReCaptcha" in page_source or "usuario no autorizado por ReCaptcha" in page_source:
            logger.warning("[SII] RUT %s: SII rechazó la consulta por reCAPTCHA (headless/proxy detectado)", rut)
            try:
                debug_dir = VM_TEMP_BASE / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / "sii_no_open_btn.html").write_text(page_source, encoding="utf-8", errors="replace")
                (debug_dir / "sii_no_open_btn_url.txt").write_text(driver.current_url or "", encoding="utf-8")
            except Exception as ex:
                logger.warning("[SII] No se pudo guardar debug: %s", ex)
            return {
                "success": False,
                "activities": [],
                "not_found": True,
                "error": "SII rechazó la consulta: usuario no autorizado por ReCaptcha (headless o proxy detectado). Ver documentación README_VM.md.",
            }

        # Botón desplegar actividades (en headless + proxy puede tardar bastante)
        btn_desplegar_clicked = False
        try:
            btn_desplegar = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.open-btn"))
            )
            driver.execute_script("arguments[0].click();", btn_desplegar)
            logger.info("[SII] Botón desplegar actividades encontrado y clickeado")
            btn_desplegar_clicked = True
        except Exception as e:
            logger.warning("[SII] No se encontró botón open-btn para RUT %s, intentando tabla directa: %s", rut, e)
            try:
                debug_dir = VM_TEMP_BASE / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                (debug_dir / "sii_no_open_btn.html").write_text(driver.page_source or "", encoding="utf-8", errors="replace")
                (debug_dir / "sii_no_open_btn_url.txt").write_text(driver.current_url or "", encoding="utf-8")
                logger.info("[SII] Debug: HTML guardado en %s/sii_no_open_btn.html", debug_dir)
            except Exception as ex:
                logger.warning("[SII] No se pudo guardar debug (no open-btn): %s", ex)

        # Tabla de actividades (puede estar ya visible sin click en open-btn)
        try:
            wait.until(EC.visibility_of_element_located((By.ID, "DataTables_Table_0")))
        except Exception as e:
            if not btn_desplegar_clicked:
                logger.warning("[SII] RUT %s: tampoco se encontró tabla DataTables_Table_0 (sin actividades en SII)", rut)
                not_found = True
                return {"success": True, "activities": [], "not_found": not_found, "error": None}
            raise
        time.sleep(1.5)

        filas = driver.find_elements(By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr")
        logger.info("[SII] Tabla DataTables_Table_0 visible, filas encontradas: %d", len(filas))
        for fila in filas:
            columnas = fila.find_elements(By.TAG_NAME, "td")
            if len(columnas) >= 6:
                descripcion = columnas[1].text.strip()
                codigo = columnas[2].text.strip()
                categoria = columnas[3].text.strip()
                afecta_iva = columnas[4].text.strip().upper()
                fecha_texto = columnas[5].text.strip()
                activities.append({
                    "code": codigo,
                    "description": descripcion,
                    "category": categoria,
                    "isVatSubject": "SI" in afecta_iva or "SÍ" in afecta_iva,
                    "fecha": fecha_texto,
                    "startDate": _parsear_fecha_sii(fecha_texto),
                    "lastUpdatedAt": datetime.utcnow(),
                })

        if not activities and filas:
            logger.warning("[SII] RUT %s: hay %d filas pero ninguna con >=6 columnas (revisar estructura tabla)", rut, len(filas))
        elif not activities:
            logger.warning("[SII] RUT %s: tabla visible pero 0 filas de actividades", rut)
        else:
            logger.info("[SII] RUT %s: extraídas %d actividades correctamente", rut, len(activities))

    except Exception as e:
        error_type = type(e).__name__
        error_detail = getattr(e, "msg", None) or (e.args[0] if e.args else str(e))
        logger.exception(
            "[SII] Error extrayendo giros para %s: %s - %s (detalle: %s)",
            rut, error_type, error_detail, e.args
        )
        # En timeout de la primera carga, guardar HTML y URL para ver qué recibió Chrome (proxy/página)
        if error_type == "TimeoutException" and driver:
            try:
                debug_dir = VM_TEMP_BASE / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                path_html = debug_dir / "sii_last_timeout.html"
                path_url = debug_dir / "sii_last_timeout_url.txt"
                path_html.write_text(driver.page_source or "", encoding="utf-8", errors="replace")
                path_url.write_text(driver.current_url or "", encoding="utf-8")
                logger.warning("[SII] Debug: guardado %s y %s (revisar qué cargó Chrome)", path_html, path_url)
            except Exception as ex:
                logger.warning("[SII] No se pudo guardar debug: %s", ex)
        error_msg = str(e) or f"{error_type}: {error_detail}"
        not_found = "no se encontró" in str(e).lower() or "not found" in str(e).lower()
    finally:
        try:
            driver.quit()
        except Exception as e:
            logger.warning("Error al cerrar driver: %s", e)
        # Liberar espacio: borrar directorio de sesión de Chrome (caché, user data, etc.)
        if session_dir and session_dir.exists():
            try:
                shutil.rmtree(session_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("No se pudo borrar sesión %s: %s", session_dir, e)

    logger.info("[SII] RUT %s resultado: success=%s, activities=%d, not_found=%s, error=%s", rut, error_msg is None, len(activities), not_found, error_msg)
    return {
        "success": error_msg is None,
        "activities": activities,
        "not_found": not_found,
        "error": error_msg,
    }


@app.on_event("startup")
def startup_cleanup():
    """Al iniciar la API, borrar sesiones Chrome viejas (p. ej. de un reinicio tras crash)."""
    try:
        removed = _cleanup_old_sessions()
        if removed > 0:
            logger.info("Limpieza al inicio: %d directorios de sesión eliminados", removed)
        VM_TEMP_BASE.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning("Limpieza al inicio: %s", e)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "sii-scraper-vm", "selenium": SELENIUM_AVAILABLE}


@app.post("/api/v1/cleanup")
async def cleanup_disk():
    """
    Fuerza limpieza de directorios de sesión antiguos (liberar espacio).
    Útil si el disco se llenó o quieres liberar sin esperar al próximo ciclo.
    """
    try:
        removed = _cleanup_old_sessions()
        return {"ok": True, "removed_sessions": removed, "message": f"Eliminados {removed} directorios de sesión"}
    except Exception as e:
        logger.exception("Error en cleanup manual: %s", e)
        return {"ok": False, "removed_sessions": 0, "error": str(e)}


@app.post("/api/v1/sii/giros")
async def obtener_giros(body: GirosRequest) -> Dict[str, Any]:
    """
    Consulta el SII por RUT y devuelve la lista de actividades económicas (giros).
    Ejecuta el scraping en esta VM para no exponer la IP de Cloud Run.
    """
    rut = (body.rut or "").strip()
    if not rut:
        raise HTTPException(status_code=400, detail="rut es requerido")

    logger.info("[SII] POST /giros recibido RUT=%s", rut)
    result = _extraer_giros_sii(rut)
    logger.info("[SII] POST /giros RUT=%s -> success=%s activities=%d not_found=%s", rut, result["success"], len(result.get("activities", [])), result.get("not_found"))
    return {
        "rut": _normalizar_rut(rut),
        "activities": result["activities"],
        "economicActivities": result["activities"],
        "not_found": result["not_found"],
        "error": result.get("error"),
        "success": result["success"],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
