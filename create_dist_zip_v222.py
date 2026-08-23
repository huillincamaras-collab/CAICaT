"""
Crea el paquete ZIP de distribución para CAICAT v2.22.
Ejecutar DESPUÉS de compilar con Nuitka y agregar ffmpeg manualmente.
"""
import os
import sys
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

VERSION = "2.23"
APP_NAME = "caicat"
DIST_FOLDER = f"{APP_NAME}.v.{VERSION}"
ZIP_NAME = f"CAICAT_v{VERSION}.zip"

def print_status(message, status="INFO "):
    symbols = { "INFO ":  "[*] ",  "OK ":  "[OK] ",  "ERROR ":  "[ERROR] ",  "WARN ":  "[!] "}
    print(f"{symbols.get(status, '[*]')} {message}")

def verify_build():
    """Verifica que la compilación de Nuitka exista (en múltiples ubicaciones posibles)."""
    dist_path = Path(DIST_FOLDER)
    
    if not dist_path.exists():
        print_status(f"Carpeta de build '{DIST_FOLDER}' no encontrada", "ERROR")
        print_status("Ejecutar build_nuitka_v222.bat primero", "WARN")
        return False, None
    
    # Buscar el ejecutable en múltiples ubicaciones posibles
    exe_candidates = [
        dist_path / f"{APP_NAME}.{VERSION}.exe",  # caicat.2.22.exe
        dist_path / "main.exe",                    # main.exe (si Nuitka usó nombre por defecto)
        dist_path / "main.dist" / f"{APP_NAME}.{VERSION}.exe",  # main.dist/caicat.2.22.exe
        dist_path / "main.dist" / "main.exe",     # main.dist/main.exe
    ]
    
    exe_path = None
    for candidate in exe_candidates:
        if candidate.exists():
            exe_path = candidate
            print_status(f"Build de Nuitka verificado: {exe_path}", "OK")
            break
    
    if exe_path is None:
        print_status("Ejecutable no encontrado en ninguna ubicación esperada", "ERROR")
        print_status("Ubicaciones buscadas:", "WARN")
        for candidate in exe_candidates:
            print_status(f"  - {candidate}", "WARN")
        return False, None
    
    return True, exe_path

def verify_ffmpeg(exe_path):
    """Verifica que FFmpeg esté presente (en múltiples ubicaciones posibles)."""
    # Determinar la carpeta base según dónde está el ejecutable
    if exe_path.parent.name == "main.dist":
        base_path = exe_path.parent  # El ejecutable está en main.dist/
    else:
        base_path = exe_path.parent  # El ejecutable está en la raíz de caicat.v.2.22/
    
    ffmpeg_dir = base_path / "resources" / "ffmpeg"
    ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"
    ffprobe_exe = ffmpeg_dir / "ffprobe.exe"
    
    if not ffmpeg_exe.exists():
        print_status("ffmpeg.exe no encontrado", "ERROR")
        print_status(f"Ubicación esperada: {ffmpeg_dir}", "ERROR")
        return False
    
    if not ffprobe_exe.exists():
        print_status("ffprobe.exe no encontrado", "ERROR")
        print_status(f"Ubicación esperada: {ffmpeg_dir}", "ERROR")
        return False
    
    print_status("FFmpeg verificado", "OK")
    return True

def verify_manual(exe_path):
    """Verifica que manual.pdf esté presente."""
    if exe_path.parent.name == "main.dist":
        base_path = exe_path.parent
    else:
        base_path = exe_path.parent
    
    manual_path = base_path / "manual.pdf"
    
    if not manual_path.exists():
        print_status("manual.pdf no encontrado", "WARN")
        print_status(f"Ubicación esperada: {manual_path}", "WARN")
        print_status("El manual no se incluirá en el ZIP", "WARN")
        return False
    
    print_status("Manual PDF verificado", "OK")
    return True

def create_readme(exe_path):
    """Crea el archivo LEEME.txt para usuarios finales."""
    readme_content = f"""
{'=' * 70}
CAICAT v{VERSION} - Software de Procesamiento de Cámaras Trampa
{'=' * 70}

REQUISITOS DEL SISTEMA:
- Windows 10 o superior (64-bit)
- 4 GB RAM mínimo (8 GB recomendado)
- 2 GB de espacio en disco

INSTALACIÓN:
1. Extraer este ZIP a cualquier carpeta
2. Ejecutar {exe_path.name}
3. ¡No se requiere instalación adicional!

PRIMEROS PASOS:
1. Ejecutar {exe_path.name}
2. Configurar el proyecto en la pantalla inicial
3. Seleccionar carpeta de videos/fotos
4. Completar datos del deployment
5. Iniciar procesamiento

CARACTERÍSTICAS PRINCIPALES:
- Procesamiento automático de videos y fotos
- Extracción inteligente de frames
- Etiquetado multi-especie con comportamientos
- Sistema de configuración jerárquico (País → Región → Config)
- Exportación a Excel, CSV, Camtrap DP e INABIO
- Integración con GBIF para taxonomía
- Modos Científico y Estándar
- Modo Legacy para PCs lentas
- Modo Batch para procesamiento masivo
- Manual de usuario integrado (botón "?")

PAÍSES Y REGIONES INCLUIDOS:
🇪🇨 ECUADOR:
  - Parque Nacional Llanganates
  - Parque Nacional Atillo
  - Parque Nacional Cubilán
  - Parque Nacional Culebrillas
  - Parque Nacional TU-Buerán

🇦🇷 ARGENTINA:
  - Base
  - Patagonia Norte

SOPORTE:
Para reportar errores o solicitar funcionalidades, usar el sistema
de reportes integrado en la aplicación.

CRÉDITOS:
Desarrollado para investigación en biodiversidad y conservación.
Versión {VERSION} - {datetime.now().strftime('%B %Y')}

{'=' * 70}
"""
    
    # Crear LEEME.txt en la misma carpeta que el ejecutable
    readme_path = exe_path.parent / "LEEME.txt"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content.strip())
    
    print_status("LEEME.txt creado", "OK")

def create_zip(exe_path):
    """Crea el ZIP final con máxima compresión."""
    # Determinar la carpeta base según dónde está el ejecutable
    if exe_path.parent.name == "main.dist":
        base_path = exe_path.parent  # Empaquetar solo main.dist
        arcname_base = DIST_FOLDER   # En el ZIP, main.dist se llama caicat.v.2.22
    else:
        base_path = exe_path.parent  # Empaquetar caicat.v.2.22 completo
        arcname_base = DIST_FOLDER
    
    print_status(f"\nCreando paquete ZIP: {ZIP_NAME}", "INFO")
    print_status("Usando máxima compresión (esto puede tardar)...", "INFO")
    
    with zipfile.ZipFile(ZIP_NAME, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        total_size = 0
        file_count = 0
        
        for root, dirs, files in os.walk(base_path):
            # Excluir main.build si existe (archivos temporales de compilación)
            if "main.build" in root:
                continue
            
            for file in files:
                file_path = Path(root) / file
                
                # Calcular arcname (ruta dentro del ZIP)
                if exe_path.parent.name == "main.dist":
                    # Si el ejecutable está en main.dist, empaquetar solo main.dist
                    # pero renombrarlo a caicat.v.2.22 en el ZIP
                    arcname = Path(arcname_base) / file_path.relative_to(base_path)
                else:
                    # Si el ejecutable está en la raíz, empaquetar todo caicat.v.2.22
                    arcname = file_path.relative_to(base_path.parent)
                
                # Agregar al ZIP
                zipf.write(file_path, arcname)
                total_size += file_path.stat().st_size
                file_count += 1
        
        # Calcular tamaño del ZIP
        zip_size = os.path.getsize(ZIP_NAME)
        print_status(f"  Archivos empaquetados: {file_count}", "OK")
        print_status(f"  Tamaño original: {total_size / (1024*1024):.1f} MB", "OK")
        print_status(f"  Tamaño comprimido: {zip_size / (1024*1024):.1f} MB", "OK")
        
        if total_size > 0:
            ratio = (1 - zip_size / total_size) * 100
            print_status(f"  Reducción: {ratio:.1f}%", "OK")
    
    return ZIP_NAME

def main():
    print("=" * 70)
    print(f"CAICAT v{VERSION} - Empaquetado para Distribución")
    print("=" * 70)
    
    # Cambiar al directorio del script
    os.chdir(Path(__file__).parent)
    
    # Paso 1: Verificar build
    print_status("\nPaso 1: Verificando build de Nuitka...", "INFO")
    build_ok, exe_path = verify_build()
    if not build_ok:
        return 1
    
    # Paso 2: Verificar FFmpeg
    print_status("\nPaso 2: Verificando FFmpeg...", "INFO")
    if not verify_ffmpeg(exe_path):
        print_status("FFmpeg no encontrado. Agregar ffmpeg.exe y ffprobe.exe a:", "ERROR")
        print_status(f"  {exe_path.parent}/resources/ffmpeg/", "ERROR")
        return 1
    
    # Paso 3: Verificar manual.pdf (opcional)
    print_status("\nPaso 3: Verificando manual.pdf...", "INFO")
    verify_manual(exe_path)
    
    # Paso 4: Crear LEEME.txt
    print_status("\nPaso 4: Creando documentación...", "INFO")
    create_readme(exe_path)
    
    # Paso 5: Crear ZIP
    print_status("\nPaso 5: Creando paquete ZIP...", "INFO")
    zip_file = create_zip(exe_path)
    
    # Resumen final
    print("\n" + "=" * 70)
    print_status("✅ PAQUETE DE DISTRIBUCIÓN CREADO EXITOSAMENTE", "OK")
    print("=" * 70)
    print(f"\nArchivo ZIP: {os.path.abspath(zip_file)}")
    print(f"Tamaño: {os.path.getsize(zip_file) / (1024*1024):.1f} MB")
    print("\nEste archivo está listo para distribuir a los usuarios.")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())