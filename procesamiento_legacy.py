# procesamiento_legacy.py
"""
Módulo de procesamiento optimizado para computadoras lentas.
Usa procesamiento SECUENCIAL y parámetros reducidos para mejor performance.
"""

import os
import json
import time
import subprocess
import shutil
import numpy as np
import cv2
from datetime import datetime
import hashlib
import sys
from config_utils import load_config

# Windows-specific flag to prevent console windows from spawning
_WIN_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

def get_ffmpeg_paths():
    """Resuelve rutas de ffmpeg/ffprobe para script y .exe compilado."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    ffmpeg_bin = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    ffprobe_bin = 'ffprobe.exe' if os.name == 'nt' else 'ffprobe'
    
    ffmpeg_path = os.path.join(base_dir, 'resources', 'ffmpeg', ffmpeg_bin)
    ffprobe_path = os.path.join(base_dir, 'resources', 'ffmpeg', ffprobe_bin)
    
    if not os.path.exists(ffmpeg_path):
        ffmpeg_path = "ffmpeg"
    if not os.path.exists(ffprobe_path):
        ffprobe_path = "ffprobe"
        
    return ffmpeg_path, ffprobe_path


def get_legacy_params():
    """Obtiene parámetros de procesamiento en modo legacy."""
    config = load_config()
    legacy = config.get("Processing", {}).get("LegacyParams", {})
    
    return {
        "FPS_EXTRACT": legacy.get("FPS_EXTRACT", 0.3),
        "BUFFER_N": legacy.get("BUFFER_N", 10),
        "TOP_K": legacy.get("TOP_K", 3),
        "MAX_FRAMES": legacy.get("MAX_FRAMES", 50),
        "OUTPUT_SIZE": tuple(legacy.get("OUTPUT_SIZE", [912, 513])),
        "JPEG_QUALITY": legacy.get("JPEG_QUALITY", 75),
        "MASK_QUALITY": legacy.get("MASK_QUALITY", 65),
        "MASK_OFFSET": legacy.get("MASK_OFFSET", 50),
        "MASK_SATURATED": legacy.get("MASK_SATURATED", 0.01),
        "TIMEOUT_SECONDS": legacy.get("TIMEOUT_SECONDS", 10),
        "SLOW_EXTRACTION_TIMEOUT": legacy.get("SLOW_EXTRACTION_TIMEOUT", 5)
    }


def compute_video_hash(filepath, sample_size=1024*1024, length=16):
    """Calcula un hash único basado en el contenido del video."""
    try:
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            return "empty_file"
        
        with open(filepath, 'rb') as f:
            start = f.read(sample_size)
            if file_size > sample_size:
                f.seek(-sample_size, os.SEEK_END)
                end = f.read(sample_size)
            else:
                end = b''
                
            hasher = hashlib.sha256()
            hasher.update(start)
            hasher.update(end)
            full_hash = hasher.hexdigest()
            return full_hash[:length]
    except Exception as e:
        print(f"Advertencia: no se pudo calcular hash para {filepath}: {e}")
        stat = os.stat(filepath)
        fallback = f"fallback_{stat.st_size}_{int(stat.st_mtime)}"
        return fallback[:length] if len(fallback) > length else fallback


def obtener_fecha_video(video_path):
    """Obtiene fecha del video desde metadata o archivo."""
    try:
        _, ffprobe_path = get_ffmpeg_paths()
        cmd = [
            ffprobe_path, "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=creation_time",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=_WIN_NO_WINDOW)
        info = json.loads(result.stdout)
        fecha = info.get("format", {}).get("tags", {}).get("creation_time", None)
        if fecha:
            return fecha[2:4] + fecha[5:7] + fecha[8:10] + "_" + fecha[11:13] + fecha[14:16] + fecha[17:19]
    except Exception:
        pass
    ts = os.path.getmtime(video_path)
    return datetime.fromtimestamp(ts).strftime("%y%m%d_%H%M%S")


def leer_frames_opencv_legacy(video_path, fps_extract=0.3, max_frames=50, output_size=(912, 513), timeout_seconds=10, slow_timeout=5):
    """
    Lee frames usando OpenCV - MÉTODO PROBADO de CAICaT 1.0.3.
    Extrae frames en COLOR (BGR), luego convierte a gris para procesamiento.
    
    TIMEOUT: Si no extrae ningún frame en timeout_seconds, aborta el video.
    SLOW_TIMEOUT: Si pasa slow_timeout sin extraer frames pero ya tiene algunos, termina con lo que tiene.
    """
    cap = None
    try:
        import signal
        
        # Función para manejar timeout
        class TimeoutException(Exception):
            pass
        
        def timeout_handler(signum, frame):
            raise TimeoutException("Timeout extrayendo frames")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[ERROR] No se pudo abrir el video: {os.path.basename(video_path)}")
            return None, 0
        
        # Obtener propiedades del video
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Validar FPS
        if video_fps == 0 or video_fps > 120:
            video_fps = 30  # fallback
        
        # Calcular intervalo entre frames (similar a CAICaT 1.0.3)
        interval = max(int(video_fps / fps_extract), 1)
        
        extracted_frames = []
        start_time = time.time()
        last_success_time = start_time
        
        # Iterar por los frames usando el método de CAICaT 1.0.3
        for i in range(0, frame_count, interval):
            # Verificar timeout: si han pasado X segundos sin extraer frames
            elapsed = time.time() - start_time
            time_since_last_success = time.time() - last_success_time
            
            if len(extracted_frames) == 0 and elapsed > timeout_seconds:
                print(f"[TIMEOUT] No se pudo extraer ningún frame en {timeout_seconds}s: {os.path.basename(video_path)}")
                cap.release()
                return None, 0
            
            # Si llevamos mucho tiempo sin éxito pero ya tenemos algunos frames, salir
            if len(extracted_frames) > 0 and time_since_last_success > slow_timeout:
                print(f"[WARNING] Extracción lenta detectada (>{slow_timeout}s sin progreso), terminando con {len(extracted_frames)} frames")
                break
            
            # Limitar número de frames extraídos
            if len(extracted_frames) >= max_frames:
                break
            
            try:
                # Posicionar en el frame específico
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                
                # Si la lectura fue exitosa Y el frame es válido
                if ret and frame is not None and frame.size > 0:
                    try:
                        # Convertir a escala de grises
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        
                        # Redimensionar
                        resized = cv2.resize(gray, output_size, interpolation=cv2.INTER_AREA)
                        
                        extracted_frames.append(resized)
                        last_success_time = time.time()  # Actualizar último éxito
                        
                    except Exception as e:
                        # Si falla la conversión/resize, continuar con el siguiente
                        continue
            except Exception as e:
                # Si falla cap.set o cap.read, continuar
                continue
        
        cap.release()
        
        # Verificar si se extrajeron frames
        if len(extracted_frames) == 0:
            print(f"[ERROR] No se pudieron extraer frames de: {os.path.basename(video_path)}")
            return None, 0
        
        print(f"[OK] Extraídos {len(extracted_frames)} frames de {os.path.basename(video_path)}")
        return extracted_frames, len(extracted_frames)
        
    except Exception as e:
        print(f"[ERROR] Excepción leyendo frames de {os.path.basename(video_path)}: {e}")
        import traceback
        traceback.print_exc()
        if cap is not None:
            cap.release()
        return None, 0


def calcular_metrica_mov_simple(frame, avg):
    """Calcula diferencia promedio simple entre frame y promedio."""
    diff = np.abs(frame.astype(np.float32) - avg.astype(np.float32))
    return diff.mean()


def mapear_mask_gris(diff, offset, saturado):
    """Crea máscara de movimiento."""
    diff = np.abs(diff)
    diff = diff - offset
    diff[diff < 0] = 0
    flat = diff.flatten()
    if len(flat) == 0:
        return diff.astype(np.uint8)
    
    umbral = np.percentile(flat, 100 * (1 - saturado))
    diff = np.clip(diff * 255 / max(umbral, 1), 0, 255)
    return diff.astype(np.uint8)


def procesar_video_legacy(video_meta, output_root):
    """
    Procesa un video en modo legacy (optimizado para PCs lentas).
    
    Diferencias con procesamiento normal:
    - Usa OpenCV en lugar de ffmpeg pipe
    - Extrae menos frames (FPS_EXTRACT = 0.3)
    - Máximo 50 frames
    - Redimensiona directamente a 912x513
    - Solo 3 tops (configurable)
    - Sin multiprocessing
    
    FIXED: Manejo robusto de errores para evitar crashes silenciosos.
    """
    video_path = video_meta.get("video_path", "unknown")
    video_name = os.path.basename(video_path)
    
    try:
        params = get_legacy_params()
        
        FPS_EXTRACT = params["FPS_EXTRACT"]
        BUFFER_N = params["BUFFER_N"]
        TOP_K = params["TOP_K"]
        MAX_FRAMES = params["MAX_FRAMES"]
        OUTPUT_SIZE = params["OUTPUT_SIZE"]
        JPEG_QUALITY = params["JPEG_QUALITY"]
        MASK_QUALITY = params["MASK_QUALITY"]
        MASK_OFFSET = params["MASK_OFFSET"]
        MASK_SATURATED = params["MASK_SATURATED"]
        
        v_hash = video_meta["video_hash"]
        fecha_prefix = video_meta["fecha_prefix"]
        
        frames_root = os.path.join(output_root, "frames")
        output_folder = os.path.join(frames_root, v_hash)
        os.makedirs(output_folder, exist_ok=True)
        
        # Asegurar que el campo original_photos exista
        if "original_photos" not in video_meta:
            video_meta["original_photos"] = []
        
        t0 = time.time()
        
        # Leer frames con OpenCV (con timeout configurable)
        TIMEOUT_SECONDS = params["TIMEOUT_SECONDS"]
        SLOW_TIMEOUT = params["SLOW_EXTRACTION_TIMEOUT"]
        
        try:
            frames, total_frames = leer_frames_opencv_legacy(
                video_path, 
                FPS_EXTRACT, 
                MAX_FRAMES, 
                OUTPUT_SIZE,
                timeout_seconds=TIMEOUT_SECONDS,
                slow_timeout=SLOW_TIMEOUT
            )
        except Exception as e:
            error_msg = f"Error leyendo video: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "frame_extraction"
            })
            return video_meta
        
        if frames is None or total_frames == 0:
            error_msg = "No se pudieron extraer frames del video"
            print(f"[ERROR] {video_name}: {error_msg}")
            
            # Limpiar carpeta de frames si existe
            if os.path.exists(output_folder):
                try:
                    shutil.rmtree(output_folder)
                    print(f"[CLEANUP] Carpeta de frames eliminada: {v_hash}")
                except Exception as e:
                    print(f"[WARNING] No se pudo eliminar carpeta: {e}")
            
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "frame_extraction"
            })
            return video_meta
        
        # Convertir lista a array numpy
        try:
            frames_array = np.array(frames, dtype=np.float32)
            if frames_array.size == 0:
                raise ValueError("Array de frames vacío")
        except Exception as e:
            error_msg = f"Error convirtiendo frames a numpy: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "array_conversion"
            })
            return video_meta
        
        # Calcular promedio global
        try:
            avg_final = np.mean(frames_array, axis=0).astype(np.uint8)
        except Exception as e:
            error_msg = f"Error calculando promedio: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "average_calculation"
            })
            return video_meta
        
        # Guardar promedio
        try:
            promedio_path = os.path.join(output_folder, f"{fecha_prefix}_promedio.jpg")
            cv2.imwrite(promedio_path, avg_final, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        except Exception as e:
            error_msg = f"Error guardando promedio: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "save_average"
            })
            return video_meta
        
        # Calcular scores de movimiento para cada frame
        try:
            scores = []
            for frame in frames_array:
                score = calcular_metrica_mov_simple(frame, avg_final)
                scores.append(score)
        except Exception as e:
            error_msg = f"Error calculando scores de movimiento: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "motion_scores"
            })
            return video_meta
        
        # Seleccionar TOP_K frames con más movimiento
        try:
            top_indices = np.argsort(scores)[-TOP_K:][::-1]
        except Exception as e:
            error_msg = f"Error seleccionando top frames: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "top_selection"
            })
            return video_meta
        
        # Guardar top frames
        try:
            top_paths = []
            for rank, idx in enumerate(top_indices, 1):
                fname = os.path.join(output_folder, f"{fecha_prefix}_top_{rank:02d}.jpg")
                cv2.imwrite(fname, frames_array[idx].astype(np.uint8), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                top_paths.append(fname)
        except Exception as e:
            error_msg = f"Error guardando top frames: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "save_tops"
            })
            return video_meta
        
        # Generar máscara usando el frame con más movimiento
        try:
            best_frame = frames_array[top_indices[0]]
            diff = best_frame - avg_final.astype(np.float32)
            mask_gray = mapear_mask_gris(diff, MASK_OFFSET, MASK_SATURATED)
            
            # Reducir tamaño de máscara
            mask_small = cv2.resize(mask_gray, (OUTPUT_SIZE[0] // 4, OUTPUT_SIZE[1] // 4), interpolation=cv2.INTER_AREA)
            mask_path = os.path.join(output_folder, f"{fecha_prefix}_mask.jpg")
            cv2.imwrite(mask_path, mask_small, [int(cv2.IMWRITE_JPEG_QUALITY), MASK_QUALITY])
        except Exception as e:
            error_msg = f"Error generando máscara: {str(e)}"
            print(f"[ERROR] {video_name}: {error_msg}")
            video_meta.update({
                "status": "error",
                "error_message": error_msg,
                "error_stage": "mask_generation"
            })
            return video_meta
        
        t1 = time.time()
        
        # Actualizar metadata
        # 🔒 FIX: Solo actualizar campos de procesamiento, preservar metadata existente
        video_meta.update({
            "promedio": promedio_path,
            "mask": mask_path,
            "tops": top_paths,
            "status": "done",
            "frames": total_frames,
            "time_sec": round(t1 - t0, 2),
        })

        # Inicializar estructura solo si no existe
        if "classification" not in video_meta:
            video_meta["classification"] = {"species": [], "counts": {}, "behaviors": [], "optional_tags": []}
        if "metadata" not in video_meta:
            video_meta["metadata"] = {"site": "", "subsite": "", "camera": "", "operator": "", "recorded_at": video_meta.get("recorded_at", ""), "notes": ""}
        if "ui" not in video_meta:
            video_meta["ui"] = {"is_favorite": False, "is_excluded": False, "embed_metadata": False, "xlsx": False}
        if "session" not in video_meta:
            video_meta["session"] = {"session_id": "", "camtrap_db_session": False}
                    
        # Limpiar claves del modelo viejo si existen
        for old_key in ("tags", "behaviors", "species_counts"):
            video_meta.pop(old_key, None)
        
        return video_meta
        
    except Exception as e:
        # Captura de cualquier error no previsto
        error_msg = f"Error inesperado: {str(e)}"
        print(f"[ERROR CRÍTICO] {video_name}: {error_msg}")
        import traceback
        traceback.print_exc()
        
        video_meta.update({
            "status": "error",
            "error_message": error_msg,
            "error_stage": "unknown"
        })
        return video_meta


def escanear_videos_legacy(input_folder, output_root):
    """
    Escanea videos en modo legacy (similar a escanear_videos pero sin multiprocessing).
    Devuelve lista de metadatos.
    """
    params = get_legacy_params()
    TOP_K = params["TOP_K"]
    
    # Formatos de video soportados
    video_exts = {'.avi', '.mp4', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', 
                  '.3gp', '.3gpp', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.vob', 
                  '.asf', '.ogv', '.ogg', '.dv', '.mxf'}
    
    # Escanear archivos
    all_files = []
    try:
        all_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) 
                     if os.path.isfile(os.path.join(input_folder, f))]
    except Exception as e:
        print(f"Error scanning folder: {e}")
    
    video_files = [f for f in all_files if os.path.splitext(f)[1].lower() in video_exts]
    video_files = sorted(video_files)
    
    frames_root = os.path.join(output_root, "frames")
    
    metadata = []
    for v in video_files:
        # Calcular hash único
        v_hash = compute_video_hash(v)
        
        # Obtener fecha
        fecha_prefix = obtener_fecha_video(v)
        
        # Timestamp ISO 8601
        try:
            recorded_dt = datetime.strptime(fecha_prefix, "%y%m%d_%H%M%S")
        except Exception:
            try:
                recorded_dt = datetime.fromtimestamp(os.path.getmtime(v))
            except Exception:
                recorded_dt = datetime.now()
        
        recorded_at = recorded_dt.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Verificar si ya fue procesado
        expected_folder = os.path.join(frames_root, v_hash)
        already_done = False
        if os.path.isdir(expected_folder):
            promedio_path = os.path.join(expected_folder, f"{fecha_prefix}_promedio.jpg")
            mask_path = os.path.join(expected_folder, f"{fecha_prefix}_mask.jpg")
            top0_path = os.path.join(expected_folder, f"{fecha_prefix}_top_01.jpg")
            if os.path.exists(promedio_path) and os.path.exists(mask_path) and os.path.exists(top0_path):
                already_done = True
        
        # Construir metadato base
        meta_entry = {
            "video_path": v,
            "video_hash": v_hash,
            "frames_folder": v_hash,
            "fecha_prefix": fecha_prefix,
            "original_photos": [],
            "promedio": None,
            "mask": None,
            "tops": [],
            "status": "done" if already_done else "pending",
            "recorded_at": recorded_at,
            "processing_mode": "legacy"
        }
        
        # Si ya está procesado, rellenar rutas
        if already_done:
            meta_entry["promedio"] = promedio_path
            meta_entry["mask"] = mask_path
            tops = []
            for i in range(1, TOP_K + 1):
                top_path = os.path.join(expected_folder, f"{fecha_prefix}_top_{i:02d}.jpg")
                if os.path.exists(top_path):
                    tops.append(top_path)
                else:
                    break
            meta_entry["tops"] = tops
        
        metadata.append(meta_entry)
    
    return metadata


def procesar_lote_legacy(metadata_list, output_root, progress_callback=None):
    """
    Procesa una lista de videos en modo legacy (SECUENCIAL).
    
    Args:
        metadata_list: Lista de metadatos de videos
        output_root: Carpeta de salida
        progress_callback: Función opcional para reportar progreso (idx, total)
    
    Returns:
        Lista de metadatos procesados
    """
    processed = []
    total = len(metadata_list)
    
    for idx, meta in enumerate(metadata_list):
        if meta["status"] == "pending":
            print(f"[Legacy] Procesando {idx+1}/{total}: {os.path.basename(meta['video_path'])}")
            result = procesar_video_legacy(meta, output_root)
            processed.append(result)
        else:
            print(f"[Legacy] Saltando {idx+1}/{total} (ya procesado)")
            processed.append(meta)
        
        # Callback de progreso
        if progress_callback:
            progress_callback(idx + 1, total)
    
    return processed
