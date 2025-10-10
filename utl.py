import subprocess
import sys
import importlib

# Librerías necesarias
LIBRERIAS = [
    "pandas",
    "selenium",
    "webdriver-manager",
    "tqdm",
    "colorama",
    "psutil"
]

def instalar_libreria(libreria):
    """Instalar una librería si no está instalada"""
    try:
        importlib.import_module(libreria.replace("-", "_"))
        print(f"✅ {libreria} ya está instalada")
    except ImportError:
        print(f"📦 Instalando {libreria}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", libreria, "--upgrade"])

def main():
    print("=" * 70)
    print("🔧 Verificando librerías necesarias para el script de validación")
    print("=" * 70)
    for libreria in LIBRERIAS:
        instalar_libreria(libreria)
    print("=" * 70)
    print("✅ Todas las dependencias están listas")
    print("=" * 70)

if __name__ == "__main__":
    main()
