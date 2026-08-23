"""
Verifica que todos los archivos necesarios estén presentes antes de compilar con Nuitka.
Ejecutar desde cualquier lugar: python prepare_build_v224.py
"""
import os
import sys
from pathlib import Path

# 🔒 FIX: Usar la ubicación del script como base (no el CWD)
SCRIPT_DIR = Path(__file__).parent.resolve()

def print_status(message, status="INFO"):
    symbols = {
        "INFO":  "[*]  ",
        "OK":    "[OK] ",
        "ERROR": "[ERR]",
        "WARN":  "[!]  "
    }
    print(f"{symbols.get(status, '[*] ')} {message}")

def check_file(path, required=True):
    """Verifica que un archivo exista (ruta absoluta o relativa al script)."""
    full_path = SCRIPT_DIR / path
    if full_path.exists() and full_path.is_file():
        size = full_path.stat().st_size / 1024
        print_status(f"{path} ({size:.1f} KB)", "OK")
        return True
    else:
        status = "ERROR" if required else "WARN"
        print_status(f"{path} NO ENCONTRADO", status)
        return not required

def check_directory(path, required=True):
    """Verifica que un directorio exista."""
    full_path = SCRIPT_DIR / path
    if full_path.exists() and full_path.is_dir():
        count = len(list(full_path.rglob("*")))
        print_status(f"{path}/ ({count} archivos)", "OK")
        return True
    else:
        status = "ERROR" if required else "WARN"
        print_status(f"{path}/ NO ENCONTRADO", status)
        return not required

def main():
    print("=" * 70)
    print("CAICAT v2.24 - Verificación Pre-Build")
    print("=" * 70)
    print(f"\n📁 Directorio base detectado: {SCRIPT_DIR}")
    print()
    
    all_ok = True

    # 1. Módulos Python principales
    print("\n📄 Módulos Python (.py)")
    print("-" * 70)
    required_py = [
        "main.py",
        "gui_inicial.py",
        "gui_tagger.py",
        "gui_setup.py",
        "gui_analysis.py",
        "gui_auditor.py",
        "gui_manual_tagger.py",
        "gui_batch_metadata.py",
        "gui_excel_export.py",
        "procesamiento.py",
        "procesamiento_legacy.py",
        "procesamiento_batch.py",
        "config_utils.py",
        "config_manager.py",
        "export_camtrap.py",
        "export_inabio.py",
        "export_utils.py",
        "embed_metadata.py",
        "sort_rename.py",
    ]
    for f in required_py:
        if not check_file(f, required=True):
            all_ok = False

    # 2. Archivos de configuración
    print("\n⚙️  Archivos de Configuración")
    print("-" * 70)
    if not check_file("config.ini", required=False):
        print_status("config.ini se generará automáticamente en la primera ejecución", "INFO")

    # 3. Recursos
    print("\n🎨 Recursos")
    print("-" * 70)
    if not check_file("caicat_transparente.png", required=True):
        all_ok = False
    if not check_file("manual.pdf", required=False):
        print_status("manual.pdf opcional (se puede agregar después)", "WARN")

    # 4. Carpetas de configuración
    print("\n📁 Carpetas de Configuración")
    print("-" * 70)
    if not check_directory("config", required=True):
        all_ok = False
    if not check_directory("config/paises", required=True):
        all_ok = False
    if not check_directory("config/regions", required=True):
        all_ok = False
    if not check_directory("config/tagger_configs", required=True):
        all_ok = False

    # 5. Carpeta de recursos
    print("\n🎬 Carpeta de Recursos")
    print("-" * 70)
    if not check_directory("resources", required=True):
        all_ok = False
    if not check_directory("resources/ffmpeg", required=True):
        all_ok = False
    else:
        # Verificar ffmpeg y ffprobe
        ffmpeg_exe = SCRIPT_DIR / "resources" / "ffmpeg" / "ffmpeg.exe"
        ffprobe_exe = SCRIPT_DIR / "resources" / "ffmpeg" / "ffprobe.exe"
        if ffmpeg_exe.exists():
            print_status("ffmpeg.exe encontrado", "OK")
        else:
            print_status("ffmpeg.exe NO ENCONTRADO", "ERROR")
            all_ok = False
        if ffprobe_exe.exists():
            print_status("ffprobe.exe encontrado", "OK")
        else:
            print_status("ffprobe.exe NO ENCONTRADO", "ERROR")
            all_ok = False

    # Verificar masters de países
    print("\n🌍 Masters de Países")
    print("-" * 70)
    if not check_file("config/paises/species_master_ecuador.json", required=True):
        all_ok = False
    if not check_file("config/paises/species_master_argentina.json", required=True):
        all_ok = False

    # Verificar regiones
    print("\n🗺️  Regiones")
    print("-" * 70)
    required_regions = [
        "config/regions/ecuador_llanganates.json",
        "config/regions/ecuador_atillo.json",
        "config/regions/ecuador_cubilan.json",
        "config/regions/ecuador_culebrillas.json",
        "config/regions/ecuador_bueran.json",
        "config/regions/argentina_base.json",
        "config/regions/argentina_patagonia_norte.json",
    ]
    for region in required_regions:
        if not check_file(region, required=False):
            print_status(f"Región opcional faltante: {region}", "WARN")

    # Resumen
    print("\n" + "=" * 70)
    if all_ok:
        print_status("✅ VERIFICACIÓN COMPLETA - Listo para compilar", "OK")
        print("=" * 70)
        print("\nPróximos pasos:")
        print("  1. Ejecutar: build_nuitka_v224.bat")
        print("  2. Esperar compilación (~15-25 minutos)")
        print("  3. Ejecutar: python create_dist_zip_v224.py")
        return 0
    else:
        print_status("❌ VERIFICACIÓN FALLIDA - Corregir errores antes de compilar", "ERROR")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())