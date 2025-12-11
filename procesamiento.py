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
from utils import metadata_lock
from config_utils import load_config

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
# --- Configuración ---
config = load_config()
PHOTOS_PER_VIDEO = config.get("General", {}).get("photos_per_video", 1)  # por defecto: 1

# --- Parámetros de procesamiento ---
FPS_EXTRACT = 1
BUFFER_N = 15
TOP_K = 6
DOWNSAMPLE_MAX = 320
JPEG_QUALITY = 85
MASK_QUALITY = 70
MASK_OFFSET = 50
MASK_SATURATED = 0.01


def obtener_fecha_video(video_path):
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=creation_time",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = json.loads(result.stdout)
        fecha = info.get("format", {}).get("tags", {}).get("creation_time", None)
        if fecha:
            return fecha[2:4] + fecha[5:7] + fecha[8:10] + "_" + fecha[11:13] + fecha[14:16] + fecha[17:19]
    except Exception:
        pass
    ts = os.path.getmtime(video_path)
    return datetime.fromtimestamp(ts).strftime("%y%m%d_%H%M%S")


def leer_frames_ffmpeg(video_path, fps=1):
    try:
        cmd_dim = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path
        ]
        result = subprocess.run(cmd_dim, capture_output=True, text=True, check=True)
        width, height = map(int, result.stdout.strip().split(","))
        frame_size = width * height

        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps={fps},format=gray",
            "-f", "image2pipe", "-vcodec", "rawvideo", "-"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return proc, frame_size, width, height
    except Exception as e:
        print(f"Error inicializando FFmpeg para {os.path.basename(video_path)}: {e}")
        return None, 0, 0, 0


def calcular_metrica_mov(frame, avg, downsample_max=DOWNSAMPLE_MAX):
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


def mapear_mask_gris(diff, offset=MASK_OFFSET, saturado=MASK_SATURATED):
    diff = np.abs(diff)
    diff = diff - offset
    diff[diff < 0] = 0
    flat = diff.flatten()
    if len(flat) == 0:
        return diff.astype(np.uint8)
    umbral = np.percentile(flat, 100 * (1 - saturado))
    diff = np.clip(diff * 255 / max(umbral, 1), 0, 255)
    return diff.astype(np.uint8)


def procesar_video(video_meta, output_root):
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

    top_frames_sorted = sorted(top_heap, key=lambda x: -x[0])
    top_paths = []
    for idx, (_, f) in enumerate(top_frames_sorted, 1):
        fname = os.path.join(output_folder, f"{fecha_prefix}_top_{idx:02d}.jpg")
        cv2.imwrite(fname, f, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        top_paths.append(fname)

    # Selección del frame con mayor movimiento local
    best_frame = top_frames_sorted[0][1].astype(np.float32)
    max_local = -1
    for _, f in top_frames_sorted:
        local_score = calcular_mov_local(f.astype(np.float32), avg_final)
        if local_score > max_local:
            max_local = local_score
            best_frame = f.astype(np.float32)

    diff = best_frame - avg_final
    mask_gray = mapear_mask_gris(diff)
    mask_small = cv2.resize(mask_gray, (width // 4, height // 4), interpolation=cv2.INTER_AREA)
    mask_path = os.path.join(output_folder, f"{fecha_prefix}_mask.jpg")
    cv2.imwrite(mask_path, mask_small, [int(cv2.IMWRITE_JPEG_QUALITY), MASK_QUALITY])

    t1 = time.time()
    video_meta.update({
        "promedio": promedio_path,
        "mask": mask_path,
        "tops": top_paths,
        "status": "done",
        "frames": total_frames,
        "time_sec": round(t1 - t0, 2),
        "tags": [],
        "behaviors": []
    })
    return video_meta

def wrapper(args):
    try:
        return procesar_video(*args)
    except Exception:
        args[0].update({"status": "error"})
        return args[0]


# ←←← NUEVA FUNCIÓN: escanea videos e imágenes y los asocia por timestamp
def escanear_videos(input_folder, output_root):
    """
    Escanea videos e imágenes, calcula hash único por video,
    y reutiliza procesamiento previo si ya existe.
    Devuelve solo la lista de metadatos (sin guardar archivo temporal).
    """
    video_exts = ("*.AVI", "*.avi", "*.MP4", "*.mp4", "*.MOV", "*.mov", "*.MKV", "*.mkv")
    img_exts = ("*.JPG", "*.jpg", "*.JPEG", "*.jpeg", "*.PNG", "*.png")

    video_files = []
    for ext in video_exts:
        video_files.extend(glob.glob(os.path.join(input_folder, ext)))
    video_files = sorted(list(set(video_files)))  # orden y sin duplicados

    img_files = []
    for ext in img_exts:
        img_files.extend(glob.glob(os.path.join(input_folder, ext)))
    img_files = list(set(img_files))

    def get_timestamp(path):
        try:
            if any(path.lower().endswith(ext.lower()) for ext in video_exts):
                cmd = [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_entries", "format_tags=creation_time",
                    path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                info = json.loads(result.stdout)
                fecha = info.get("format", {}).get("tags", {}).get("creation_time")
                if fecha:
                    dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
                    return dt.timestamp()
        except Exception:
            pass
        return os.path.getmtime(path)

    # Ordenar imágenes por timestamp
    img_files.sort(key=get_timestamp)
    img_timestamps = [get_timestamp(f) for f in img_files]

    # Carpeta base de frames
    frames_root = os.path.join(output_root, "frames")

    metadata = []
    for v in video_files:
        # 1. Calcular hash único
        v_hash = compute_video_hash(v)
        
        # 2. Obtener fecha para nombres de archivo (solo para legibilidad interna)
        fecha_prefix = obtener_fecha_video(v)
        try:
            recorded_dt = datetime.strptime(fecha_prefix, "%y%m%d_%H%M%S")
            recorded_at = recorded_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            recorded_at = ""

        # 3. Verificar si ya fue procesado
        expected_folder = os.path.join(frames_root, v_hash)
        already_done = False
        if os.path.isdir(expected_folder):
            # Verificar presencia de archivos clave
            promedio_path = os.path.join(expected_folder, f"{fecha_prefix}_promedio.jpg")
            mask_path = os.path.join(expected_folder, f"{fecha_prefix}_mask.jpg")
            top0_path = os.path.join(expected_folder, f"{fecha_prefix}_top_01.jpg")
            if os.path.exists(promedio_path) and os.path.exists(mask_path) and os.path.exists(top0_path):
                already_done = True

        # 4. Asociar fotos (solo si es necesario, aunque ya esté procesado)
        v_ts = get_timestamp(v)
        associated_photos = []
        if PHOTOS_PER_VIDEO > 0:
            # Buscar las últimas N fotos antes del video
            for i in range(len(img_files) - 1, -1, -1):
                if len(associated_photos) >= PHOTOS_PER_VIDEO:
                    break
                if img_timestamps[i] <= v_ts:
                    associated_photos.append(img_files[i])
            associated_photos.reverse()  # más antigua primero

        # 5. Construir metadato base
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

        # ←←← NUEVO: copiar fotos originales INMEDIATAMENTE y guardar rutas
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
        # →→→ FIN NUEVO

        # 6. Si ya está procesado, rellenar rutas de frames/máscara
        if already_done:
            meta_entry["promedio"] = promedio_path
            meta_entry["mask"] = mask_path
            # Buscar todos los tops
            tops = []
            for i in range(1, TOP_K + 1):
                top_path = os.path.join(expected_folder, f"{fecha_prefix}_top_{i:02d}.jpg")
                if os.path.exists(top_path):
                    tops.append(top_path)
                else:
                    break
            meta_entry["tops"] = tops

        metadata.append(meta_entry)

    return metadata  # ←←← solo devuelve la lista

# ===================================================================
# === FUNCIONES PARA MANEJO DE FOTOS PURAS (sin videos) ==============
# ===================================================================

import exifread
from datetime import datetime
import shutil
import numpy as np
import cv2
import os
import hashlib


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
    Procesa una ráfaga de fotos (1 o más) como si fuera un video.
    Genera: promedio.jpg, mask.jpg, top_01.jpg, ..., original_01.jpg, etc.
    """
    # 1. Hash único basado en la primera foto del grupo
    grupo_hash = compute_file_hash(grupo[0]["path"])
    frames_folder = os.path.join(output_root, "frames", grupo_hash)
    os.makedirs(frames_folder, exist_ok=True)
    

    # 2. Usar rutas originales directamente (sin copiar)
    copied_paths = [foto["path"] for foto in grupo]

    
    # 3. Cargar imágenes en escala de grises (solo una vez)
    imgs_gray = []
    imgs_color = []  # para guardar tops a color
    for p in copied_paths:
        img_color = cv2.imread(p)
        if img_color is not None:
            img_gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
            imgs_gray.append(img_gray)
            imgs_color.append(img_color)
        else:
            # Imagen de respaldo si falla la lectura
            if imgs_gray:
                h, w = imgs_gray[-1].shape
            else:
                h, w = 480, 640
            imgs_gray.append(np.zeros((h, w), dtype=np.uint8))
            imgs_color.append(np.zeros((h, w, 3), dtype=np.uint8))
    
    # 4. Calcular promedio
    avg = np.mean(imgs_gray, axis=0).astype(np.uint8)
    fecha_prefix = datetime.fromtimestamp(grupo[0]["ts"]).strftime("%y%m%d_%H%M%S")
    promedio_path = os.path.join(frames_folder, f"{fecha_prefix}_promedio.jpg")
    cv2.imwrite(promedio_path, avg, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    
    # 5. Calcular scores de movimiento
    scores = []
    for img in imgs_gray:
        diff = np.abs(img.astype(np.float32) - avg.astype(np.float32))
        scores.append(diff.mean())
    
    # 6. Seleccionar TOP_K
    top_indices = np.argsort(scores)[-TOP_K:][::-1]
    top_paths = []
    for rank, idx in enumerate(top_indices, 1):
        fname = os.path.join(frames_folder, f"{fecha_prefix}_top_{rank:02d}.jpg")
        cv2.imwrite(fname, imgs_color[idx], [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        top_paths.append(fname)
    
    # 7. Generar máscara (usando la mejor imagen)
    best_idx = top_indices[0]
    best_img = imgs_gray[best_idx].astype(np.float32)
    diff = np.abs(best_img - avg.astype(np.float32))
    diff = diff - MASK_OFFSET
    diff[diff < 0] = 0
    if diff.size > 0:
        umbral = np.percentile(diff.flatten(), 100 * (1 - MASK_SATURATED))
        diff = np.clip(diff * 255 / max(umbral, 1), 0, 255)
    mask_gray = diff.astype(np.uint8)
    mask_small = cv2.resize(mask_gray, (mask_gray.shape[1] // 4, mask_gray.shape[0] // 4))
    mask_path = os.path.join(frames_folder, f"{fecha_prefix}_mask.jpg")
    cv2.imwrite(mask_path, mask_small, [int(cv2.IMWRITE_JPEG_QUALITY), MASK_QUALITY])
    
    # 8. Metadatos (misma estructura que videos)
    try:
        recorded_at = datetime.fromtimestamp(grupo[0]["ts"]).strftime("%Y-%m-%d %H:%M:%S")
    except:
        recorded_at = ""
    
    return {
        "video_path": grupo[0]["path"],      # identificador único
        "video_hash": grupo_hash,
        "frames_folder": grupo_hash,
        "fecha_prefix": fecha_prefix,
        "original_photos": copied_paths,     # igual que en modo híbrido
        "promedio": promedio_path,
        "mask": mask_path,
        "tops": top_paths,
        "status": "done",
        "tags": [],
        "behaviors": [],
        "notes": "",
        "recorded_at": recorded_at,
        "site": "",
        "subsite": "",
        "camera": "",
        "operator": "",
        "session_id": "",
        "is_photo": True,                    # campo adicional (opcional para Tagger)
        "is_burst": len(grupo) > 1
    }
# →→→ FIN NUEVA FUNCIÓN