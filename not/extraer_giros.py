import pandas as pd
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def automatizar_sii(lista_ruts):
    # --- CONFIGURACIÓN DE RUTA ---
    # Obtiene la carpeta donde está el script y define el nombre del archivo Excel
    ruta_script = os.path.dirname(os.path.abspath(__file__))
    ruta_excel = os.path.join(ruta_script, "giros_extraidos.xlsx")
    
    options = Options()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    # options.add_argument("--headless") # Opcional: Descomentar para ejecutar sin ver la ventana
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    resultados = []

    try:
        for rut in lista_ruts:
            print(f"Consultando RUT: {rut}")
            driver.get("https://www2.sii.cl/stc/noauthz")
            wait = WebDriverWait(driver, 15)

            try:
                # 1. Ingresar el RUT
                input_rut = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.rut-form")))
                input_rut.clear()
                input_rut.send_keys(rut)
                time.sleep(0.5)

                # 2. Click en Consultar Situación Tributaria
                btn_consultar = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//input[@value='Consultar Situación Tributaria']")
                ))
                driver.execute_script("arguments[0].scrollIntoView(true);", btn_consultar)
                driver.execute_script("arguments[0].click();", btn_consultar)

                # 3. Esperar el botón de despliegue y presionarlo
                btn_desplegar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.open-btn")))
                driver.execute_script("arguments[0].click();", btn_desplegar)

                # 4. Extraer datos de la tabla cuando sea visible
                wait.until(EC.visibility_of_element_located((By.ID, "DataTables_Table_0")))
                time.sleep(1) # Tiempo para que cargue el contenido de la tabla
                
                filas = driver.find_elements(By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr")
                
                for fila in filas:
                    columnas = fila.find_elements(By.TAG_NAME, "td")
                    if len(columnas) >= 5:
                        datos = {
                            "RUT": rut,
                            "Actividad Económica": columnas[1].text.strip(),
                            "Código": columnas[2].text.strip(),
                            "Categoría": columnas[3].text.strip(),
                            "Afecta IVA": columnas[4].text.strip(),
                            "Fecha": columnas[5].text.strip()
                        }
                        resultados.append(datos)
                
                print(f"   > OK: {len(filas)} giros encontrados.")

            except Exception:
                print(f"   > Aviso: No se encontró información para el RUT {rut}.")

    finally:
        driver.quit()

    # --- GUARDAR EN EXCEL ---
    if resultados:
        df = pd.DataFrame(resultados)
        # Usamos engine='openpyxl' para asegurar la compatibilidad
        df.to_excel(ruta_excel, index=False, engine='openpyxl')
        print(f"\n{'='*40}")
        print(f"PROCESO FINALIZADO CON ÉXITO")
        print(f"Archivo creado en: {ruta_excel}")
        print(f"{'='*40}")
    else:
        print("\nNo se extrajeron datos, no se creó el archivo Excel.")

# --- TU LISTA DE RUTS ---
mis_ruts = [
    "78.018.339-K",
    "77.440.503-8"
] 

if __name__ == "__main__":
    automatizar_sii(mis_ruts)