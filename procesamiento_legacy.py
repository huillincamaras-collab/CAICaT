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
# 🔒 IMPORTAR funciones compartidas desde procesamiento.py (evitar duplicación)
from procesamiento import (
    get_ffmpeg_paths,
    compute_video_hash,
    obtener_fecha_video,
    mapear_mask_gris,
    compute_file_hash,
    procesar_grupo_de_fotos
)

# Windows-specific flag to prevent console windows from spawning
_WIN_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

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


def escanear_videos_legacy(input_folder, output_root, photos_per_video=None, process_mode="both"):
    """
    Escanea videos e imágenes en modo legacy (sin multiprocessing).
    Args:
        input_folder: Carpeta con archivos multimedia
        output_root: Carpeta de salida
        photos_per_video: Cantidad de fotos a asociar por video (None = usar config)
        process_mode: "both" (videos+huérfanas), "videos" (solo videos), "photos" (solo fotos)
    Devuelve lista de metadatos de videos (las fotos se procesan aparte desde la GUI).
    """
    from procesamiento import last_scan_stats  # reutilizamos la variable global del módulo normal
    import procesamiento  # para acceder a last_scan_stats como variable del módulo

    params = get_legacy_params()
    config = load_config()
    if photos_per_video is None:
        PHOTOS_PER_VIDEO = config.get("General", {}).get("photos_per_video", 1)
    else:
        PHOTOS_PER_VIDEO = photos_per_video
    TOP_K = params["TOP_K"]

    # 🔒 FIX: si el modo es solo videos, no asociar fotos
    if process_mode == "videos":
        PHOTOS_PER_VIDEO = 0

    video_exts = {'.avi', '.mp4', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v',
                  '.3gp', '.3gp', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.vob',
                  '.asf', '.ogv', '.ogg', '.dv', '.mxf'}
    img_exts = {'.jpg', '.jpeg', '.png'}

    all_files = []
    try:
        all_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder)
                     if os.path.isfile(os.path.join(input_folder, f))]
    except Exception as e:
        print(f"Error scanning folder: {e}")

    video_files = sorted([f for f in all_files if os.path.splitext(f)[1].lower() in video_exts])
    img_files = [f for f in all_files if os.path.splitext(f)[1].lower() in img_exts]

    # 🔒 FIX: get_timestamp con EXIF para fotos, ffprobe para videos, mtime fallback
    def get_timestamp(path):
        try:
            if any(path.lower().endswith(ext.lower()) for ext in video_exts):
                _, ffprobe_path = get_ffmpeg_paths()
                cmd = [
                    ffprobe_path, "-v", "quiet",
                    "-print_format", "json",
                    "-show_entries", "format_tags=creation_time",
                    path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=10, creationflags=_WIN_NO_WINDOW)
                info = json.loads(result.stdout)
                fecha = info.get("format", {}).get("tags", {}).get("creation_time")
                if fecha:
                    from datetime import datetime as _dt
                    dt = _dt.fromisoformat(fecha.replace("Z", "+00:00"))
                    return dt.timestamp()
        except Exception:
            pass
        try:
            if any(path.lower().endswith(ext.lower()) for ext in img_exts):
                import exifread
                with open(path, 'rb') as f:
                    tags = exifread.process_file(f, stop_tag='DateTimeOriginal', details=False)
                    if 'EXIF DateTimeOriginal' in tags:
                        from datetime import datetime as _dt
                        dt_str = str(tags['EXIF DateTimeOriginal'])
                        dt = _dt.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                        return dt.timestamp()
        except Exception:
            pass
        return os.path.getmtime(path)

    img_files.sort(key=get_timestamp)
    img_timestamps = [get_timestamp(f) for f in img_files]
    frames_root = os.path.join(output_root, "frames")
    metadata = []

    # ============================================================
    # FASE 1: Procesar videos (SOLO si el modo lo permite)
    # 🔒 FIX: respetar process_mode == "photos" → NO procesar videos
    # ============================================================
    if process_mode in ("both", "videos"):
        for v in video_files:
            v_hash = compute_video_hash(v)
            fecha_prefix = obtener_fecha_video(v)
            try:
                recorded_dt = datetime.strptime(fecha_prefix, "%y%m%d_%H%M%S")
            except Exception:
                try:
                    recorded_dt = datetime.fromtimestamp(os.path.getmtime(v))
                except Exception:
                    recorded_dt = datetime.now()
            recorded_at = recorded_dt.strftime("%Y-%m-%dT%H:%M:%S")

            expected_folder = os.path.join(frames_root, v_hash)
            already_done = False
            if os.path.isdir(expected_folder):
                promedio_path = os.path.join(expected_folder, f"{fecha_prefix}_promedio.jpg")
                mask_path = os.path.join(expected_folder, f"{fecha_prefix}_mask.jpg")
                top0_path = os.path.join(expected_folder, f"{fecha_prefix}_top_01.jpg")
                if os.path.exists(promedio_path) and os.path.exists(mask_path) and os.path.exists(top0_path):
                    already_done = True

            v_ts = get_timestamp(v)
            associated_photos = []
            if PHOTOS_PER_VIDEO > 0:
                for i in range(len(img_files) - 1, -1, -1):
                    if len(associated_photos) >= PHOTOS_PER_VIDEO:
                        break
                    if img_timestamps[i] <= v_ts:
                        associated_photos.append(img_files[i])
                associated_photos.reverse()

            meta_entry = {
                "video_path": v,
                "video_hash": v_hash,
                "frames_folder": v_hash,
                "fecha_prefix": fecha_prefix,
                "associated_photos": associated_photos,
                "original_photos": [],
                "promedio": None,
                "mask": None,
                "tops": [],
                "status": "done" if already_done else "pending",
                "recorded_at": recorded_at,
                "processing_mode": "legacy"
            }

            # Copiar fotos asociadas a la carpeta de frames
            copied_photo_paths = []
            if associated_photos:
                output_folder = os.path.join(frames_root, v_hash)
                os.makedirs(output_folder, exist_ok=True)
                for idx, photo_path in enumerate(associated_photos, 1):
                    if os.path.exists(photo_path):
                        ext = os.path.splitext(photo_path)[1]
                        dest_name = f"original_{idx:02d}{ext.lower()}"
                        dest_path = os.path.join(output_folder, dest_name)
                        if not os.path.exists(dest_path):
                            shutil.copy2(photo_path, dest_path)
                        copied_photo_paths.append(dest_path)
            meta_entry["original_photos"] = copied_photo_paths

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

    # ============================================================
    # FASE 2: Preparar fotos huérfanas (NO procesar aquí, la GUI lo hará
    #         después del diálogo interactivo de ráfagas)
    # ============================================================
    used_photos = set()
    for entry in metadata:
        for p in entry.get("associated_photos", []):
            used_photos.add(p)

    orphan_photos = [f for f in img_files if f not in used_photos]

    # 🔒 FIX: en modo "photos" TODAS las fotos son candidatas
    if process_mode == "photos":
        orphan_photos = list(img_files)

    orphan_with_ts = []
    if orphan_photos and process_mode in ("both", "photos"):
        orphan_with_ts = [{"path": p, "ts": get_timestamp(p)} for p in orphan_photos]
        orphan_with_ts.sort(key=lambda x: x["ts"])

    # ============================================================
    # FASE 3: Actualizar estadísticas globales (reutilizando last_scan_stats
    #         del módulo procesamiento para compatibilidad con la GUI)
    # ============================================================
    import procesamiento
    procesamiento.last_scan_stats = {
        "total_videos_found": len(video_files),
        "total_videos_processed": len(metadata),
        "total_photos": len(img_files),
        "associated_photos": len(used_photos),
        "orphan_photos": len(orphan_photos),
        "orphan_photos_with_ts": orphan_with_ts,
        "process_mode": process_mode
    }

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

# ===================================================================
# FUNCIONES LEGACY PARA PROCESAMIENTO DE FOTOS (PCs LENTAS)
# ===================================================================

def procesar_grupo_de_fotos_legacy(grupo, output_root, progress_callback=None):
    """
    Procesa una ráfaga de fotos en modo legacy.
    🔒 OPTIMIZACIÓN: Si son ≤ 3 fotos, delega en el procesamiento ligero de procesamiento.py
    (más rápido, sin cálculo de promedio/máscara). Si son > 3, usa el procesamiento legacy completo.
    """
    # 🔹 RAMA DE PROCESAMIENTO LIGERO (≤ 3 fotos)
    if len(grupo) <= 3:
        # Delegamos en la función optimizada de procesamiento.py
        return procesar_grupo_de_fotos(grupo, output_root)

    # ========================================================================
    # 🔹 RAMA DE PROCESAMIENTO LEGACY COMPLETO (> 3 fotos)
    # ========================================================================
    MAX_SIZE = 512  # Legacy usa resolución más baja
    JPEG_QUALITY = 65
    MASK_QUALITY = 65
    MASK_OFFSET = 50
    MASK_SATURATED = 0.01
    TOP_K = len(grupo)  # En legacy, cada foto de la ráfaga es un top

    try:
        grupo_hash = compute_file_hash(grupo[0]["path"])
        frames_folder = os.path.join(output_root, "frames", grupo_hash)
        os.makedirs(frames_folder, exist_ok=True)
        
        copied_paths = [foto["path"] for foto in grupo]
        imgs_gray = []
        imgs_color = []
        target_size = None
        
        for p in copied_paths:
            img_color = cv2.imread(p)
            if img_color is not None:
                h, w = img_color.shape[:2]
                if max(h, w) > MAX_SIZE:
                    scale = MAX_SIZE / max(h, w)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    img_color = cv2.resize(img_color, (new_w, new_h), interpolation=cv2.INTER_AREA)
                
                if target_size is None:
                    target_size = (img_color.shape[1], img_color.shape[0])
                else:
                    if (img_color.shape[1], img_color.shape[0]) != target_size:
                        img_color = cv2.resize(img_color, target_size, interpolation=cv2.INTER_AREA)
                
                img_gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
                imgs_gray.append(img_gray)
                imgs_color.append(img_color)
            else:
                if target_size is None:
                    target_size = (640, 480)
                w, h = target_size
                imgs_gray.append(np.zeros((h, w), dtype=np.uint8))
                imgs_color.append(np.zeros((h, w, 3), dtype=np.uint8))

        if not imgs_gray:
            print(f"⚠️ [Legacy] No se pudo cargar ninguna imagen del grupo: {grupo[0]['path']}")
            return {
                "video_path": grupo[0]["path"],
                "video_hash": grupo_hash,
                "frames_folder": grupo_hash,
                "fecha_prefix": datetime.fromtimestamp(grupo[0]["ts"]).strftime("%y%m%d_%H%M%S"),
                "original_photos": copied_paths,
                "promedio": None, "mask": None, "tops": [],
                "status": "error",
                "is_photo": True, "is_burst": len(grupo) > 1,
                "error_message": "No valid images in group"
            }

        avg = np.mean(imgs_gray, axis=0).astype(np.uint8)
        fecha_prefix = datetime.fromtimestamp(grupo[0]["ts"]).strftime("%y%m%d_%H%M%S")
        promedio_path = os.path.join(frames_folder, f"{fecha_prefix}_promedio.jpg")
        cv2.imwrite(promedio_path, avg, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])

        scores = []
        for img in imgs_gray:
            diff_val = np.abs(img.astype(np.float32) - avg.astype(np.float32))
            scores.append(diff_val.mean())
        
        top_indices = np.argsort(scores)[-TOP_K:][::-1]
        top_paths = []
        for rank, idx in enumerate(top_indices, 1):
            fname = os.path.join(frames_folder, f"{fecha_prefix}_top_{rank:02d}.jpg")
            cv2.imwrite(fname, imgs_color[idx], [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            top_paths.append(fname)

        best_idx = top_indices[0]
        diff_for_mask = imgs_gray[best_idx].astype(np.float32) - avg.astype(np.float32)
        mask_gray = mapear_mask_gris(diff_for_mask, MASK_OFFSET, MASK_SATURATED)
        mask_small = cv2.resize(mask_gray, (mask_gray.shape[1] // 4, mask_gray.shape[0] // 4))
        mask_path = os.path.join(frames_folder, f"{fecha_prefix}_mask.jpg")
        cv2.imwrite(mask_path, mask_small, [int(cv2.IMWRITE_JPEG_QUALITY), MASK_QUALITY])

        try:
            recorded_at = datetime.fromtimestamp(grupo[0]["ts"]).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            recorded_at = ""

        return {
            "video_path": grupo[0]["path"],
            "video_hash": grupo_hash,
            "frames_folder": grupo_hash,
            "fecha_prefix": fecha_prefix,
            "original_photos": copied_paths,
            "promedio": promedio_path,
            "mask": mask_path,
            "tops": top_paths,
            "status": "done",
            "is_photo": True,
            "is_burst": len(grupo) > 1,
            "classification": {"species": [], "counts": {}, "behaviors": [], "optional_tags": []},
            "metadata": {"site": "", "subsite": "", "camera": "", "operator": "", "recorded_at": recorded_at, "notes": ""},
            "ui": {"is_favorite": False, "is_excluded": False, "embed_metadata": False, "xlsx": False},
            "session": {"session_id": "", "camtrap_db_session": False}
        }
    except Exception as e:
        print(f"❌ [Legacy] Error procesando grupo de fotos: {e}")
        import traceback
        traceback.print_exc()
        return {
            "video_path": grupo[0]["path"],
            "video_hash": compute_file_hash(grupo[0]["path"]),
            "frames_folder": "",
            "fecha_prefix": datetime.fromtimestamp(grupo[0]["ts"]).strftime("%y%m%d_%H%M%S"),
            "original_photos": [foto["path"] for foto in grupo],
            "promedio": None, "mask": None, "tops": [],
            "status": "error",
            "is_photo": True, "is_burst": len(grupo) > 1,
            "error_message": str(e)
        }


def procesar_todas_las_rafagas_legacy(photo_groups, output_root, progress_callback=None):
    """
    Procesa todos los grupos de fotos en modo legacy (SECUENCIAL).
    
    Args:
        photo_groups: Lista de listas de fotos [{"path": "...", "ts": ...}, ...]
        output_root: Carpeta de salida
        progress_callback: Función opcional (current, total) para reportar progreso
    
    Returns:
        Lista de metadatos de ráfagas procesadas
    """
    metadata_list = []
    total = len(photo_groups)
    
    for idx, grupo in enumerate(photo_groups):
        print(f"[Legacy] Procesando ráfaga {idx+1}/{total}: {len(grupo)} fotos")
        
        try:
            meta = procesar_grupo_de_fotos_legacy(grupo, output_root)
            metadata_list.append(meta)
        except Exception as e:
            print(f"❌ [Legacy] Error en ráfaga {idx+1}: {e}")
            # Crear metadata de error
            meta = {
                "video_path": grupo[0]["path"],
                "video_hash": compute_file_hash(grupo[0]["path"]),
                "frames_folder": "",
                "fecha_prefix": datetime.fromtimestamp(grupo[0]["ts"]).strftime("%y%m%d_%H%M%S"),
                "original_photos": [foto["path"] for foto in grupo],
                "promedio": None, "mask": None, "tops": [],
                "status": "error",
                "is_photo": True, "is_burst": len(grupo) > 1,
                "error_message": str(e)
            }
            metadata_list.append(meta)
        
        # Callback de progreso
        if progress_callback:
            progress_callback(idx + 1, total)
    
    return metadata_list
