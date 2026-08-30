# procesamiento.py
import os
import glob
import json
import time
import subprocess
import shutil
import heapq
import numpy as np
import cv2
from datetime import datetime
import threading
import hashlib
import sys
from config_utils import metadata_lock
from config_utils import load_config
import exifread

# Windows-specific flag to prevent console windows from spawning
_WIN_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

# ←←← NUEVO: Variable global para estadísticas del último escaneo
last_scan_stats = {
    "total_videos": 0,
    "total_photos": 0,
    "associated_photos": 0,
    "orphan_photos": 0,
    "orphan_bursts": 0
}

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

# --- Configuración ---
def get_processing_params():
    config = load_config()
    proc = config.get("Processing", {})
    general = config.get("General", {})

    return {
        "FPS_EXTRACT": proc.get("FPS_EXTRACT", 1),
        "BUFFER_N": proc.get("BUFFER_N", 15),
        "TOP_K": proc.get("TOP_K", 6),
        "DOWNSAMPLE_MAX": proc.get("DOWNSAMPLE_MAX", 320),
        "JPEG_QUALITY": proc.get("JPEG_QUALITY", 85),
        "MASK_QUALITY": proc.get("MASK_QUALITY", 70),
        "MASK_OFFSET": proc.get("MASK_OFFSET", 50),
        "MASK_SATURATED": proc.get("MASK_SATURATED", 0.01),
        "PHOTOS_PER_VIDEO": general.get("photos_per_video", 1)
    }

# Module-level constants for backward compatibility with GUI modules
_params = get_processing_params()
FPS_EXTRACT = _params["FPS_EXTRACT"]
BUFFER_N = _params["BUFFER_N"]
TOP_K = _params["TOP_K"]
DOWNSAMPLE_MAX = _params["DOWNSAMPLE_MAX"]
JPEG_QUALITY = _params["JPEG_QUALITY"]
MASK_QUALITY = _params["MASK_QUALITY"]



def compute_video_hash(filepath, sample_size=1024*1024, length=16):
    """Calcula un hash único basado en el contenido del video y lo trunca a 'length' caracteres."""
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
            return fecha[2:4] + fecha[5:7] + fecha[8:10] + " " + fecha[11:13] + fecha[14:16] + fecha[17:19]
    except Exception:
        pass
    ts = os.path.getmtime(video_path)
    return datetime.fromtimestamp(ts).strftime("%y%m%d %H%M%S")

def leer_frames_ffmpeg(video_path, fps=1):
    try:
        ffmpeg_path, ffprobe_path = get_ffmpeg_paths()
        
        cmd_dim = [
            ffprobe_path, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path
        ]
        try:
            result = subprocess.run(cmd_dim, capture_output=True, text=True, check=True, timeout=30, creationflags=_WIN_NO_WINDOW)
        except subprocess.TimeoutExpired:
            print(f"⚠️ FFprobe timeout para {os.path.basename(video_path)}")
            return None, 0, 0, 0
        except subprocess.CalledProcessError as e:
            print(f"⚠️ FFprobe error para {os.path.basename(video_path)}: {e}")
            return None, 0, 0, 0
            
        width, height = map(int, result.stdout.strip().split(","))
        frame_size = width * height
        
        cmd = [
            ffmpeg_path, "-i", video_path,
            "-vf", f"fps={fps},format=gray",
            "-f", "image2pipe", "-vcodec", "rawvideo", "-"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_WIN_NO_WINDOW)
        return proc, frame_size, width, height
    except Exception as e:
        print(f"Error inicializando FFmpeg para {os.path.basename(video_path)}: {e}")
        return None, 0, 0, 0

def calcular_metrica_mov(frame, avg, downsample_max=None):
    if downsample_max is None:
        downsample_max = get_processing_params()["DOWNSAMPLE_MAX"]
    if downsample_max is not None:
        h, w = frame.shape
        scale = downsample_max / max(h, w)
        if scale < 1.0:
            new_size = (int(w * scale), int(h * scale))
            frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
            avg = cv2.resize(avg, new_size, interpolation=cv2.INTER_AREA)
    diff = np.abs(frame.astype(np.float32) - avg.astype(np.float32))
    return diff.mean()


def calcular_mov_local(frame, avg, grid=(4, 4)):
    h, w = frame.shape
    gh, gw = grid
    max_local_diff = 0
    for i in range(gh):
        for j in range(gw):
            y0, y1 = i * h // gh, (i + 1) * h // gh
            x0, x1 = j * w // gw, (j + 1) * w // gw
            patch_diff = np.abs(
                frame[y0:y1, x0:x1].astype(np.float32) - avg[y0:y1, x0:x1].astype(np.float32)
            ).mean()
            if patch_diff > max_local_diff:
                max_local_diff = patch_diff
    return max_local_diff


def mapear_mask_gris(diff, offset, saturado):
    """
    Ahora recibe explícitamente el offset y el nivel de saturación.
    """
    diff = np.abs(diff)
    diff = diff - offset
    diff[diff < 0] = 0
    flat = diff.flatten()
    if len(flat) == 0:
        return diff.astype(np.uint8)
    
    # Evitar división por cero si la imagen está vacía
    umbral = np.percentile(flat, 100 * (1 - saturado))
    diff = np.clip(diff * 255 / max(umbral, 1), 0, 255)
    return diff.astype(np.uint8)


def procesar_video(video_meta, output_root):
    params = get_processing_params()

    FPS_EXTRACT = params["FPS_EXTRACT"]
    BUFFER_N = params["BUFFER_N"]
    TOP_K = params["TOP_K"]
    DOWNSAMPLE_MAX = params["DOWNSAMPLE_MAX"]
    JPEG_QUALITY = params["JPEG_QUALITY"]
    MASK_QUALITY = params["MASK_QUALITY"]
    MASK_OFFSET = params["MASK_OFFSET"]
    MASK_SATURATED = params["MASK_SATURATED"]
    video_path = video_meta["video_path"]
    v_hash = video_meta["video_hash"]
    fecha_prefix = video_meta["fecha_prefix"]
    frames_root = os.path.join(output_root, "frames")
    output_folder = os.path.join(frames_root, v_hash)
    os.makedirs(output_folder, exist_ok=True)

    # ←←← REMOVIDO: la copia de fotos ya se hizo en escanear_videos()
    # Asegurar que el campo original_photos exista (por compatibilidad)
    if "original_photos" not in video_meta:
        video_meta["original_photos"] = []
    # →→→

    t0 = time.time()
    proc, frame_size, width, height = leer_frames_ffmpeg(video_path, FPS_EXTRACT)
    if proc is None or frame_size == 0:
        video_meta.update({"status": "error"})
        return video_meta

    buffer = []
    sum_buffer = np.zeros((height, width), dtype=np.float32)
    top_heap = []
    total_frames = 0

    try:
        while True:
            raw = proc.stdout.read(frame_size)
            if len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
            total_frames += 1

            buffer.append(frame)
            sum_buffer += frame.astype(np.float32)
            if len(buffer) > BUFFER_N:
                oldest = buffer.pop(0)
                sum_buffer -= oldest.astype(np.float32)

            avg = sum_buffer / len(buffer)
            score = calcular_metrica_mov(frame, avg)
            if len(top_heap) < TOP_K:
                heapq.heappush(top_heap, (score, frame.copy()))
            else:
                if score > top_heap[0][0]:
                    heapq.heapreplace(top_heap, (score, frame.copy()))
    except Exception as e:
        print(f"Error leyendo frames de {os.path.basename(video_path)}: {e}")
        proc.stdout.close()
        proc.kill()
        video_meta.update({"status": "error"})
        return video_meta

    proc.stdout.close()
    proc.wait()

    if total_frames == 0:
        video_meta.update({"status": "error"})
        return video_meta

    avg_final = sum_buffer / len(buffer)
    promedio_path = os.path.join(output_folder, f"{fecha_prefix}_promedio.jpg")
    cv2.imwrite(promedio_path, avg_final.astype(np.uint8), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    
    # 🔒 FIX NUITKA: Ensure file is fully written and readable
    if os.path.exists(promedio_path):
        try:
            # Verify file is readable by attempting to open it
            with open(promedio_path, 'rb') as verify:
                verify.read(1)
        except Exception:
            pass  # File might still be flushing, but we've done our best

    top_frames_sorted = sorted(top_heap, key=lambda x: -x[0])
    top_paths = []
    for idx, (_, f) in enumerate(top_frames_sorted, 1):
        fname = os.path.join(output_folder, f"{fecha_prefix}_top_{idx:02d}.jpg")
        cv2.imwrite(fname, f, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        top_paths.append(fname)
        
        # 🔒 FIX NUITKA: Verify each top frame is readable
        if os.path.exists(fname):
            try:
                with open(fname, 'rb') as verify:
                    verify.read(1)
            except Exception:
                pass

    # Selección del frame con mayor movimiento local
    best_frame = top_frames_sorted[0][1].astype(np.float32)
    max_local = -1
    for _, f in top_frames_sorted:
        local_score = calcular_mov_local(f.astype(np.float32), avg_final)
        if local_score > max_local:
            max_local = local_score
            best_frame = f.astype(np.float32)

    diff = best_frame - avg_final
    mask_gray = mapear_mask_gris(diff, MASK_OFFSET, MASK_SATURATED)
    mask_small = cv2.resize(mask_gray, (width // 4, height // 4), interpolation=cv2.INTER_AREA)
    mask_path = os.path.join(output_folder, f"{fecha_prefix}_mask.jpg")
    cv2.imwrite(mask_path, mask_small, [int(cv2.IMWRITE_JPEG_QUALITY), MASK_QUALITY])
    
    # 🔒 FIX NUITKA: Verify mask is readable
    if os.path.exists(mask_path):
        try:
            with open(mask_path, 'rb') as verify:
                verify.read(1)
        except Exception:
            pass

    # 🔒 FIX NUITKA: Force filesystem sync on Windows to ensure all writes are flushed
    if os.name == 'nt':
        try:
            import ctypes
            # Flush file buffers to disk
            kernel32 = ctypes.windll.kernel32
            for path in [promedio_path, mask_path] + top_paths:
                if os.path.exists(path):
                    handle = kernel32.CreateFileW(
                        path,
                        0x80000000,  # GENERIC_READ
                        0x00000001 | 0x00000002,  # FILE_SHARE_READ | FILE_SHARE_WRITE
                        None,
                        3,  # OPEN_EXISTING
                        0x80,  # FILE_ATTRIBUTE_NORMAL
                        None
                    )
                    if handle != -1:
                        kernel32.FlushFileBuffers(handle)
                        kernel32.CloseHandle(handle)
        except Exception:
            # Fallback: just wait a bit for filesystem to catch up
            time.sleep(0.05)

    t1 = time.time()
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

def wrapper(args):
    try:
        video_meta = args[0]
        # 🔒 FIX: Si ya está procesado o es una foto (ráfaga), no procesar nuevamente
        if video_meta.get("status") == "done" or video_meta.get("is_photo"):
            return video_meta
        return procesar_video(*args)
    except Exception:
        args[0].update({"status": "error"})
        return args[0]



def escanear_videos(input_folder, output_root, photos_per_video=None, process_mode="both"):
    """
    Escanea videos e imágenes, calcula hash único por video,
    y reutiliza procesamiento previo si ya existe.
    Args:
        input_folder: Carpeta con archivos multimedia
        output_root: Carpeta de salida
        photos_per_video: Cantidad de fotos a asociar por video (None = usar config)
        process_mode: "both" (videos+huérfanas), "videos" (solo videos), "photos" (solo fotos)
    Devuelve lista de metadatos combinada (videos + ráfagas huérfanas) ordenada por timestamp.
    """
    global last_scan_stats
    params = get_processing_params()
    if photos_per_video is None:
        PHOTOS_PER_VIDEO = params["PHOTOS_PER_VIDEO"]
    else:
        PHOTOS_PER_VIDEO = photos_per_video
    TOP_K = params["TOP_K"]

    video_exts = {'.avi', '.mp4', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v',
                  '.3gp', '.3gpp', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.vob',
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

    # 🔒 FIX: get_timestamp lee EXIF para fotos, ffprobe para videos, mtime como fallback
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
                    dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
                    return dt.timestamp()
        except Exception:
            pass
        try:
            if any(path.lower().endswith(ext.lower()) for ext in img_exts):
                with open(path, 'rb') as f:
                    tags = exifread.process_file(f, stop_tag='DateTimeOriginal', details=False)
                    if 'EXIF DateTimeOriginal' in tags:
                        dt_str = str(tags['EXIF DateTimeOriginal'])
                        dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
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
    # ============================================================
    # 🔒 FIX: respetar process_mode == "photos" → NO procesar videos
    if process_mode in ("both", "videos"):
        # Si el modo es solo videos, no asociar fotos
        if process_mode == "videos":
            PHOTOS_PER_VIDEO = 0

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
                "promedio": None,
                "mask": None,
                "tops": [],
                "tags": [],
                "behaviors": [],
                "status": "done" if already_done else "pending",
                "site": "",
                "subsite": "",
                "camera": "",
                "operator": "",
                "recorded_at": recorded_at
            }

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
    # FASE 2: Detectar fotos huérfanas (SOLO si el modo lo permite)
    # 🔒 FIX: NO procesar fotos automáticamente. Devolver info para que la GUI
    #         muestre el diálogo interactivo de configuración de ráfagas.
    # ============================================================
    used_photos = set()
    for entry in metadata:
        for p in entry.get("associated_photos", []):
            used_photos.add(p)

    orphan_photos = [f for f in img_files if f not in used_photos]

    # 🔒 FIX: en modo "photos" TODAS las fotos son candidatas (no hay videos que las usen)
    if process_mode == "photos":
        orphan_photos = list(img_files)

    orphan_with_ts = []
    if orphan_photos and process_mode in ("both", "photos"):
        orphan_with_ts = [{"path": p, "ts": get_timestamp(p)} for p in orphan_photos]
        orphan_with_ts.sort(key=lambda x: x["ts"])

    # ============================================================
    # FASE 3: Actualizar estadísticas globales
    # 🔒 FIX: distinguir videos encontrados vs. procesados, y devolver
    #         la lista de fotos huérfanas con timestamp para que la GUI
    #         pueda estimar ráfagas ANTES de procesar.
    # ============================================================
    last_scan_stats = {
        "total_videos_found": len(video_files),
        "total_videos_processed": len(metadata),  # solo los que entraron en FASE 1
        "total_photos": len(img_files),
        "associated_photos": len(used_photos),
        "orphan_photos": len(orphan_photos),
        "orphan_photos_with_ts": orphan_with_ts,  # 🔒 NUEVO: para el diálogo de ráfagas
        "process_mode": process_mode
    }

    return metadata


# ===================================================================
# === FUNCIONES PARA MANEJO DE FOTOS PURAS (sin videos) ==============
# ===================================================================

def obtener_fotos_con_timestamp(input_folder):
    """
    Escanea una carpeta y devuelve una lista de dicts ordenada por timestamp:
    [{"path": "...", "ts": timestamp_float}, ...]
    """
    img_exts = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
    paths = []
    for f in os.listdir(input_folder):
        full_path = os.path.join(input_folder, f)
        if os.path.isfile(full_path) and os.path.splitext(f)[1] in img_exts:
            paths.append(full_path)

    fotos = []
    for p in paths:
        ts = obtener_timestamp_foto(p)
        fotos.append({"path": p, "ts": ts})
    
    # Ordenar por timestamp
    fotos.sort(key=lambda x: x["ts"])
    return fotos


def obtener_timestamp_foto(filepath):
    """Extrae timestamp de EXIF o usa fecha de modificación."""
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, stop_tag='DateTimeOriginal', details=False)
            if 'EXIF DateTimeOriginal' in tags:
                dt_str = str(tags['EXIF DateTimeOriginal'])
                dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                return dt.timestamp()
    except Exception:
        pass
    return os.path.getmtime(filepath)


def agrupar_en_rafagas(fotos_con_ts, umbral_seg=2.0):
    """
    Agrupa fotos en ráfagas según umbral de tiempo.
    Retorna lista de listas: [[foto1, foto2], [foto3], ...]
    Cada 'foto' es un dict {"path": "...", "ts": ...}
    """
    if not fotos_con_ts:
        return []
    
    grupos = []
    grupo_actual = [fotos_con_ts[0]]
    
    for i in range(1, len(fotos_con_ts)):
        if fotos_con_ts[i]["ts"] - fotos_con_ts[i-1]["ts"] <= umbral_seg:
            grupo_actual.append(fotos_con_ts[i])
        else:
            grupos.append(grupo_actual)
            grupo_actual = [fotos_con_ts[i]]
    
    grupos.append(grupo_actual)
    return grupos


def compute_file_hash(filepath, sample_size=1024*1024, length=16):
    """Calcula hash único para un archivo (fotos o videos)."""
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
            return hasher.hexdigest()[:length]
    except Exception:
        stat = os.stat(filepath)
        fallback = f"fallback_{stat.st_size}_{int(stat.st_mtime)}"
        return fallback[:length] if len(fallback) > length else fallback


def procesar_todas_las_rafagas(photo_groups, output_root):
    """
    Procesa todos los grupos de fotos y devuelve una lista de metadatos
    ESTRUCTURALMENTE IDÉNTICA a la de los videos.
    """
    metadata_list = []
    for grupo in photo_groups:
        meta = procesar_grupo_de_fotos(grupo, output_root)
        metadata_list.append(meta)
    return metadata_list


def procesar_grupo_de_fotos(grupo, output_root):
    """
    Procesa una ráfaga de fotos con downsampling a 1024px para optimizar rendimiento.
    Las imágenes de salida son ~1MP (suficiente para etiquetado, 10x más rápido que 12MP).
    """
    # 1. Cargar parámetros
    params = get_processing_params()
    JPEG_QUALITY = params["JPEG_QUALITY"]
    TOP_K = params["TOP_K"]
    MASK_OFFSET = params["MASK_OFFSET"]
    MASK_SATURATED = params["MASK_SATURATED"]
    MASK_QUALITY = params["MASK_QUALITY"]

    # 🔒 OPTIMIZACIÓN: Tamaño máximo para procesamiento (1024px en el lado más largo)
    MAX_SIZE = 1024

    # 2. Hash único basado en la primera foto del grupo
    grupo_hash = compute_file_hash(grupo[0]["path"])
    frames_folder = os.path.join(output_root, "frames", grupo_hash)
    os.makedirs(frames_folder, exist_ok=True)

    # 3. Cargar imágenes y redimensionar todas al mismo tamaño
    copied_paths = [foto["path"] for foto in grupo]
    imgs_gray = []
    imgs_color = []
    target_size = None  # (width, height) - se define con la primera imagen válida

    for p in copied_paths:
        img_color = cv2.imread(p)
        if img_color is not None:
            h, w = img_color.shape[:2]

            # 🔒 OPTIMIZACIÓN: Redimensionar si es más grande que MAX_SIZE
            if max(h, w) > MAX_SIZE:
                scale = MAX_SIZE / max(h, w)
                new_w = int(w * scale)
                new_h = int(h * scale)
                img_color = cv2.resize(img_color, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Guardar tamaño de referencia (el de la primera imagen redimensionada)
            if target_size is None:
                target_size = (img_color.shape[1], img_color.shape[0])  # (w, h)
            else:
                # Asegurar que todas tengan el mismo tamaño
                if (img_color.shape[1], img_color.shape[0]) != target_size:
                    img_color = cv2.resize(img_color, target_size, interpolation=cv2.INTER_AREA)

            img_gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
            imgs_gray.append(img_gray)
            imgs_color.append(img_color)
        else:
            # Fallback por si una imagen está corrupta
            if target_size is None:
                target_size = (640, 480)
            w, h = target_size
            imgs_gray.append(np.zeros((h, w), dtype=np.uint8))
            imgs_color.append(np.zeros((h, w, 3), dtype=np.uint8))

    # Si ninguna imagen se pudo cargar, abortar
    if not imgs_gray:
        print(f"⚠️ No se pudo cargar ninguna imagen del grupo: {grupo[0]['path']}")
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

    # 4. Calcular promedio (ahora sobre ~1MP en lugar de 12MP → ~10x más rápido)
    avg = np.mean(imgs_gray, axis=0).astype(np.uint8)
    fecha_prefix = datetime.fromtimestamp(grupo[0]["ts"]).strftime("%y%m%d_%H%M%S")
    promedio_path = os.path.join(frames_folder, f"{fecha_prefix}_promedio.jpg")
    cv2.imwrite(promedio_path, avg, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])

    # 5. Calcular scores y seleccionar TOP_K (mucho más rápido con imágenes pequeñas)
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

    # 6. Generar máscara
    best_idx = top_indices[0]
    diff_for_mask = imgs_gray[best_idx].astype(np.float32) - avg.astype(np.float32)
    mask_gray = mapear_mask_gris(diff_for_mask, MASK_OFFSET, MASK_SATURATED)
    mask_small = cv2.resize(mask_gray, (mask_gray.shape[1] // 4, mask_gray.shape[0] // 4))
    mask_path = os.path.join(frames_folder, f"{fecha_prefix}_mask.jpg")
    cv2.imwrite(mask_path, mask_small, [int(cv2.IMWRITE_JPEG_QUALITY), MASK_QUALITY])

    # 7. Retorno de metadatos
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