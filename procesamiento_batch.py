"""
procesamiento_batch.py - Procesamiento de videos en modo batch (lotes)
Permite procesar múltiples carpetas con subcarpetas de manera recursiva.
Diseñado para procesamiento nocturno desatendido con reanudación.

🔒 ACTUALIZACIÓN v2.26:
- Procesa fotos huérfanas automáticamente (tanto en modo normal como legacy)
- Tamaño de ráfaga configurable (default: 3, aprovecha procesamiento ligero)
- Incluye flag is_lightweight en metadata
- Combina videos + fotos en orden cronológico
- Fallback para subcarpetas con archivos incompletos
- Estadísticas detalladas (videos/fotos/lightweight)

Flujo:
scan_batch_folder() → detecta estructura de carpetas
create_batch_manifest() → crea manifest con metadata por archivo
process_batch_videos() → procesa todo (videos + fotos huérfanas)
apply_metadata_to_batch() → asigna site/camera/operator por carpeta
create_batch_session_metadata() → genera metadata.json para el tagger
"""
import os
import json
import shutil
from datetime import datetime
from procesamiento import (
    escanear_videos, wrapper,
    obtener_fotos_con_timestamp, agrupar_en_rafagas, procesar_todas_las_rafagas,
    obtener_timestamp_foto
)
from procesamiento_legacy import (
    escanear_videos_legacy, procesar_lote_legacy,
    procesar_todas_las_rafagas_legacy
)

# =============================================================================
# 🔒 NUEVO: CONFIGURACIÓN DE RÁFAGAS PARA BATCH
# =============================================================================
def get_batch_burst_size():
    """Obtiene el tamaño de ráfaga para procesamiento batch desatendido.
    Default: 3 (aprovecha el procesamiento ligero sin promedio/máscara).
    Se puede sobrescribir desde config.ini: [Batch] burst_size = N
    """
    try:
        from config_utils import load_config
        config = load_config()
        batch_cfg = config.get("Batch", {})
        burst = batch_cfg.get("burst_size", 3)
        return max(1, int(burst))
    except Exception:
        return 3

# =============================================================================
# ESCANEO DE CARPETAS
# =============================================================================
def scan_batch_folder(root_folder):
    """
    Escanea recursivamente una carpeta y organiza archivos por subcarpetas.
    Detecta tanto videos como fotos.
    Salta carpetas vacías silenciosamente.
    
    Args:
        root_folder: Carpeta raíz a escanear
    
    Returns:
        Dict con estructura:
        {
            "folder_key": {
                "path": "ruta/completa",
                "videos": [lista de rutas de videos],
                "photos": [lista de rutas de fotos],
                "relative_path": "ruta/relativa",
                "video_count": N,
                "photo_count": M
            }
        }
    """
    video_exts = {'.avi', '.mp4', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v',
                  '.3gp', '.3gpp', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.vob',
                  '.asf', '.ogv', '.ogg', '.dv', '.mxf'}
    img_exts = {'.jpg', '.jpeg', '.png'}
    folder_structure = {}
    
    for dirpath, dirnames, filenames in os.walk(root_folder):
        videos_in_folder = []
        photos_in_folder = []
        for f in filenames:
            full_path = os.path.join(dirpath, f)
            ext = os.path.splitext(f)[1].lower()
            if ext in video_exts:
                videos_in_folder.append(full_path)
            elif ext in img_exts:
                photos_in_folder.append(full_path)
        
        # Saltar carpetas vacías silenciosamente
        if not videos_in_folder and not photos_in_folder:
            continue
        
        # Calcular ruta relativa desde root_folder
        rel_path = os.path.relpath(dirpath, root_folder)
        
        # Crear clave única para esta carpeta
        folder_key = rel_path.replace(os.sep, "__")
        if folder_key == ".":
            folder_key = os.path.basename(root_folder)
        
        folder_structure[folder_key] = {
            "path": dirpath,
            "videos": sorted(videos_in_folder),
            "photos": sorted(photos_in_folder),
            "relative_path": rel_path,
            "video_count": len(videos_in_folder),
            "photo_count": len(photos_in_folder)
        }
    
    return folder_structure

# =============================================================================
# MANIFIESTO DEL BATCH
# =============================================================================
def create_batch_manifest(batch_id, folder_structure, output_folder, use_legacy=False, root_folder=""):
    """
    Crea un archivo batch_manifest.json con la estructura del lote.
    Incluye metadata POR ARCHIVO (video_path, hash, recorded_at, etc.)
    
    Args:
        batch_id: ID único del lote
        folder_structure: Dict retornado por scan_batch_folder()
        output_folder: Carpeta de salida base
        use_legacy: Si usa modo legacy
        root_folder: Carpeta raíz original (para referencia)
    
    Returns:
        Ruta al archivo manifest creado
    """
    batch_folder = os.path.join(output_folder, "batch")
    os.makedirs(batch_folder, exist_ok=True)
    
    manifest = {
        "batch_id": batch_id,
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "pending_processing",
        "use_legacy": use_legacy,
        "root_folder": root_folder,
        "burst_size": get_batch_burst_size(),
        "folders": {}
    }
    
    for folder_key, folder_data in folder_structure.items():
        manifest["folders"][folder_key] = {
            "original_path": folder_data["path"],
            "relative_path": folder_data["relative_path"],
            "video_count": folder_data["video_count"],
            "photo_count": folder_data["photo_count"],
            "status": "pending",
            "metadata": {
                "site": "",
                "subsite": "",
                "camera": "",
                "operator": ""
            },
            "files": [],
            "error_files": []
        }
    
    manifest_path = os.path.join(batch_folder, "batch_manifest.json")
    _save_manifest(manifest, manifest_path)
    return manifest_path

def _save_manifest(manifest, manifest_path):
    """Guarda el manifest de forma atómica."""
    temp_path = manifest_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)
    
    # Reemplazo atómico
    if os.path.exists(manifest_path):
        os.remove(manifest_path)
    os.rename(temp_path, manifest_path)

def load_manifest(manifest_path):
    """Carga el manifest desde disco."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)

# =============================================================================
# 🔒 NUEVO: PROCESAMIENTO DE FOTOS HUÉRFANAS EN BATCH
# =============================================================================
def procesar_fotos_huerfanas_batch(orphan_with_ts, output_root, use_legacy=False, progress_callback=None):
    """
    Procesa fotos huérfanas en modo batch con tamaño de ráfaga configurable.
    
    Args:
        orphan_with_ts: Lista de dicts [{"path": "...", "ts": float}, ...]
        output_root: Carpeta de salida
        use_legacy: Si usa modo legacy
        progress_callback: Función opcional (current, total)
    
    Returns:
        Lista de metadatos de ráfagas procesadas
    """
    if not orphan_with_ts:
        return []
    
    burst_size = get_batch_burst_size()
    
    # Agrupar en ráfagas de tamaño fijo
    photo_groups = []
    for i in range(0, len(orphan_with_ts), burst_size):
        photo_groups.append(orphan_with_ts[i:i + burst_size])
    
    print(f"[Batch] 📷 Procesando {len(orphan_with_ts)} fotos huérfanas en {len(photo_groups)} ráfagas (tamaño={burst_size})")
    
    if use_legacy:
        metadata_fotos = procesar_todas_las_rafagas_legacy(
            photo_groups, output_root, progress_callback
        )
    else:
        metadata_fotos = procesar_todas_las_rafagas(photo_groups, output_root)
        # Reportar progreso manualmente si hay callback
        if progress_callback:
            for idx, _ in enumerate(metadata_fotos, 1):
                progress_callback(idx, len(metadata_fotos))
    
    return metadata_fotos

# =============================================================================
# PROCESAMIENTO DEL BATCH
# =============================================================================
def process_batch_videos(folder_structure, output_folder, manifest_path,
                         use_legacy=False, progress_callback=None):
    """
    Procesa todos los videos Y fotos huérfanas del batch.
    
    🔒 ACTUALIZACIÓN v2.26:
    - Procesa videos (con wrapper o legacy)
    - Detecta y procesa fotos huérfanas automáticamente (ambos modos)
    - Combina videos + fotos en orden cronológico
    - Usa procesamiento ligero para ráfagas ≤ 3 fotos
    - Fallback para subcarpetas con archivos incompletos
    
    Args:
        folder_structure: Dict retornado por scan_batch_folder()
        output_folder: Carpeta de salida
        manifest_path: Ruta al batch_manifest.json
        use_legacy: Si usa procesamiento legacy
        progress_callback: Función opcional(folder_key, current, total, phase)
    
    Returns:
        Manifest actualizado
    """
    manifest = load_manifest(manifest_path)
    manifest["status"] = "processing"
    
    batch_folder = os.path.join(output_folder, "batch")
    frames_batch = os.path.join(batch_folder, "frames")
    os.makedirs(frames_batch, exist_ok=True)
    
    total_folders = len(folder_structure)
    
    for folder_idx, (folder_key, folder_data) in enumerate(folder_structure.items(), 1):
        print(f"\n[Batch] [{folder_idx}/{total_folders}] Procesando carpeta: {folder_key}")
        print(f"[Batch]   Videos: {folder_data['video_count']}, Fotos: {folder_data['photo_count']}")
        
        if progress_callback:
            progress_callback(folder_key, 0, 1, "starting")
        
        try:
            # Crear carpeta temporal para esta subcarpeta
            temp_output = os.path.join(output_folder, "batch_temp", folder_key)
            os.makedirs(temp_output, exist_ok=True)
            
            # ============================================================
            # FASE 1: Escanear videos (y asociar fotos si corresponde)
            # ============================================================
            if use_legacy:
                metadata_list = escanear_videos_legacy(
                    folder_data["path"], temp_output,
                    process_mode="both"
                )
                processed = procesar_lote_legacy(
                    metadata_list, temp_output,
                    progress_callback=lambda idx, total: (
                        progress_callback(folder_key, idx, total, "processing")
                        if progress_callback else None
                    )
                )
            else:
                metadata_list = escanear_videos(
                    folder_data["path"], temp_output,
                    process_mode="both"
                )
                processed = []
                for idx, meta in enumerate(metadata_list):
                    if progress_callback:
                        progress_callback(folder_key, idx + 1, len(metadata_list), "processing")
                    if meta.get("status") == "pending":
                        result = wrapper((meta, temp_output))
                        processed.append(result)
                    else:
                        processed.append(meta)
            
            # ============================================================
            # 🔒 FASE 2: NUEVO - Detectar y procesar fotos huérfanas
            # ============================================================
            try:
                import procesamiento
                orphan_with_ts = procesamiento.last_scan_stats.get("orphan_photos_with_ts", [])
            except Exception:
                orphan_with_ts = []
            
            fotos_metadata = []
            if orphan_with_ts:
                print(f"[Batch]   📷 Detectadas {len(orphan_with_ts)} fotos huérfanas, procesando...")
                fotos_metadata = procesar_fotos_huerfanas_batch(
                    orphan_with_ts, temp_output,
                    use_legacy=use_legacy
                )
                print(f"[Batch]   ✅ {len(fotos_metadata)} ráfagas procesadas")
            
            # 🔒 NUEVO: Fallback - Si la carpeta solo tenía fotos (sin videos)
            if not processed and folder_data["photo_count"] > 0 and not fotos_metadata:
                print(f"[Batch]   📷 Carpeta solo-fotos: procesando {folder_data['photo_count']} fotos")
                all_photos_with_ts = [
                    {"path": p, "ts": obtener_timestamp_foto(p)}
                    for p in folder_data["photos"]
                ]
                all_photos_with_ts.sort(key=lambda x: x["ts"])
                fotos_metadata = procesar_fotos_huerfanas_batch(
                    all_photos_with_ts, temp_output,
                    use_legacy=use_legacy
                )
            
            # 🔒 NUEVO: Combinar videos + fotos y ordenar cronológicamente
            all_processed = processed + fotos_metadata
            all_processed.sort(key=lambda x: x.get("recorded_at", ""))
            
            # ============================================================
            # FASE 3: Mover carpetas de frames y registrar en manifest
            # ============================================================
            files_info = []
            error_files = []
            frames_temp = os.path.join(temp_output, "frames")
            
            for meta in all_processed:
                video_hash = meta.get("video_hash", "")
                if not video_hash:
                    continue
                
                old_folder = os.path.join(frames_temp, video_hash)
                
                # 🔒 NUEVO: Nombre de carpeta distingue videos de fotos
                if meta.get("is_photo"):
                    fecha = meta.get("fecha_prefix", video_hash[:8])
                    new_folder_name = f"{folder_key}__photo_{fecha}__{video_hash}"
                else:
                    video_name = os.path.splitext(os.path.basename(meta.get("video_path", "")))[0]
                    new_folder_name = f"{folder_key}__{video_name}__{video_hash}"
                
                new_folder = os.path.join(frames_batch, new_folder_name)
                
                # Mover carpeta de frames
                if os.path.exists(old_folder) and not os.path.exists(new_folder):
                    shutil.move(old_folder, new_folder)
                
                # Actualizar rutas en metadata
                if meta.get("promedio"):
                    meta["promedio"] = meta["promedio"].replace(old_folder, new_folder)
                if meta.get("mask"):
                    meta["mask"] = meta["mask"].replace(old_folder, new_folder)
                if meta.get("tops"):
                    meta["tops"] = [t.replace(old_folder, new_folder) for t in meta["tops"]]
                
                # Trackear errores
                file_status = meta.get("status", "done")
                if file_status == "error":
                    error_files.append({
                        "video_path": meta.get("video_path", ""),
                        "video_hash": video_hash,
                        "error_message": meta.get("error_message", "Unknown error"),
                        "error_stage": meta.get("error_stage", "unknown")
                    })
                
                # 🔒 ACTUALIZADO: Registrar info completa incluyendo is_lightweight
                file_info = {
                    "video_path": meta.get("video_path", ""),
                    "video_hash": video_hash,
                    "fecha_prefix": meta.get("fecha_prefix", ""),
                    "recorded_at": meta.get("recorded_at", ""),
                    "is_photo": meta.get("is_photo", False),
                    "is_burst": meta.get("is_burst", False),
                    "is_lightweight": meta.get("is_lightweight", False),
                    "status": file_status,
                    "frames_folder": new_folder_name,
                    "promedio": meta.get("promedio"),
                    "mask": meta.get("mask"),
                    "tops": meta.get("tops", []),
                    "original_photos": meta.get("original_photos", []),
                    "associated_photos": meta.get("associated_photos", [])
                }
                files_info.append(file_info)
            
            # Actualizar manifest
            manifest["folders"][folder_key]["files"] = files_info
            manifest["folders"][folder_key]["error_files"] = error_files
            manifest["folders"][folder_key]["status"] = "completed" if not error_files else "completed_with_errors"
            manifest["folders"][folder_key]["videos_processed"] = sum(
                1 for f in files_info if not f["is_photo"]
            )
            manifest["folders"][folder_key]["photos_processed"] = sum(
                1 for f in files_info if f["is_photo"]
            )
            manifest["folders"][folder_key]["lightweight_photos"] = sum(
                1 for f in files_info if f.get("is_lightweight", False)
            )
            
            _save_manifest(manifest, manifest_path)
            
            if error_files:
                print(f"[Batch]   ⚠️ Carpeta completada con {len(error_files)} errores")
            else:
                print(f"[Batch]   ✅ Carpeta completada: {len(files_info)} archivos "
                      f"({manifest['folders'][folder_key]['videos_processed']} videos, "
                      f"{manifest['folders'][folder_key]['photos_processed']} fotos)")
            
            if progress_callback:
                progress_callback(folder_key, len(files_info), len(files_info), "completed")
        
        except Exception as e:
            print(f"[Batch]   ❌ Error procesando carpeta {folder_key}: {e}")
            manifest["folders"][folder_key]["status"] = "error"
            manifest["folders"][folder_key]["error_message"] = str(e)
            _save_manifest(manifest, manifest_path)
    
    # Verificar estado final
    all_completed = all(
        f["status"] in ("completed", "completed_with_errors") for f in manifest["folders"].values()
    )
    manifest["status"] = "pending_metadata_assignment" if all_completed else "completed_with_errors"
    _save_manifest(manifest, manifest_path)
    print(f"\n[Batch] ✅ Procesamiento completado. Estado: {manifest['status']}")
    return manifest

def resume_batch_processing(manifest_path, output_folder, progress_callback=None):
    """
    Reanuda un batch interrumpido.
    Salta carpetas ya procesadas y continúa desde la última incompleta.
    """
    manifest = load_manifest(manifest_path)
    use_legacy = manifest.get("use_legacy", False)
    
    # Reconstruir folder_structure para carpetas pendientes
    folder_structure = {}
    for folder_key, folder_data in manifest["folders"].items():
        if folder_data["status"] in ("pending", "error"):
            folder_structure[folder_key] = {
                "path": folder_data["original_path"],
                "videos": [],
                "photos": [],
                "relative_path": folder_data.get("relative_path", ""),
                "video_count": folder_data.get("video_count", 0),
                "photo_count": folder_data.get("photo_count", 0)
            }
    
    if not folder_structure:
        print("[Batch] No hay carpetas pendientes para procesar")
        return manifest
    
    print(f"[Batch] Reanudando procesamiento de {len(folder_structure)} carpetas pendientes")
    return process_batch_videos(
        folder_structure, output_folder, manifest_path,
        use_legacy=use_legacy, progress_callback=progress_callback
    )

# =============================================================================
# ASIGNACIÓN DE METADATA
# =============================================================================
def apply_metadata_to_batch(manifest_path, folder_metadata_dict):
    """
    Aplica metadata (site, camera, operator) a todas las carpetas del batch.
    """
    manifest = load_manifest(manifest_path)
    for folder_key, metadata in folder_metadata_dict.items():
        if folder_key in manifest["folders"]:
            manifest["folders"][folder_key]["metadata"] = metadata
    manifest["status"] = "ready_for_tagging"
    _save_manifest(manifest, manifest_path)
    return manifest

# =============================================================================
# CARGA DE METADATA DEL BATCH
# =============================================================================
def load_batch_metadata(batch_folder):
    """
    Carga todos los metadatos de un batch procesado desde el manifest.
    🔒 ACTUALIZADO: Incluye is_lightweight para compatibilidad con tagger.
    """
    manifest_path = os.path.join(batch_folder, "batch_manifest.json")
    if not os.path.exists(manifest_path):
        return []
    
    manifest = load_manifest(manifest_path)
    all_metadata = []
    
    for folder_key, folder_info in manifest["folders"].items():
        folder_metadata = folder_info.get("metadata", {})
        
        for file_info in folder_info.get("files", []):
            video_meta = {
                "video_path": file_info.get("video_path", ""),
                "video_hash": file_info.get("video_hash", ""),
                "frames_folder": file_info.get("frames_folder", ""),
                "fecha_prefix": file_info.get("fecha_prefix", ""),
                "original_photos": file_info.get("original_photos", []),
                "promedio": file_info.get("promedio"),
                "mask": file_info.get("mask"),
                "tops": file_info.get("tops", []),
                "status": file_info.get("status", "done"),
                "is_photo": file_info.get("is_photo", False),
                "is_burst": file_info.get("is_burst", False),
                "is_lightweight": file_info.get("is_lightweight", False),
                "classification": {
                    "species": [],
                    "counts": {},
                    "behaviors": [],
                    "optional_tags": []
                },
                "metadata": {
                    "site": folder_metadata.get("site", ""),
                    "subsite": folder_metadata.get("subsite", ""),
                    "camera": folder_metadata.get("camera", ""),
                    "operator": folder_metadata.get("operator", ""),
                    "recorded_at": file_info.get("recorded_at", ""),
                    "notes": ""
                },
                "ui": {
                    "is_favorite": False,
                    "is_excluded": False,
                    "embed_metadata": False,
                    "xlsx": False
                },
                "session": {
                    "session_id": "",
                    "camtrap_db_session": False,
                    "deployment_id": ""
                }
            }
            
            video_meta["file"] = {
                "video_path": video_meta["video_path"],
                "video_hash": video_meta["video_hash"],
                "frames_folder": video_meta["frames_folder"],
                "promedio": video_meta["promedio"],
                "tops": video_meta["tops"],
                "mask": video_meta["mask"]
            }
            
            all_metadata.append(video_meta)
    
    return all_metadata

# =============================================================================
# CREACIÓN DE SESIÓN PARA EL TAGGER
# =============================================================================
def create_batch_session_metadata(manifest_path, output_folder, session_id):
    """
    Crea un archivo metadata.json unificado para el batch, listo para el tagger.
    🔒 ACTUALIZADO: Incluye is_lightweight.
    """
    manifest = load_manifest(manifest_path)
    all_videos = []
    
    for folder_key, folder_info in manifest["folders"].items():
        folder_metadata = folder_info.get("metadata", {})
        site = folder_metadata.get("site", "")
        subsite = folder_metadata.get("subsite", "")
        camera = folder_metadata.get("camera", "")
        
        # Generar deployment_id
        parts = [p for p in [site, subsite, camera] if p]
        deployment_id = "_".join(parts) if parts else folder_key
        
        for file_info in folder_info.get("files", []):
            video_meta = {
                "video_path": file_info.get("video_path", ""),
                "video_hash": file_info.get("video_hash", ""),
                "frames_folder": file_info.get("frames_folder", ""),
                "fecha_prefix": file_info.get("fecha_prefix", ""),
                "original_photos": file_info.get("original_photos", []),
                "promedio": file_info.get("promedio"),
                "mask": file_info.get("mask"),
                "tops": file_info.get("tops", []),
                "status": file_info.get("status", "done"),
                "is_photo": file_info.get("is_photo", False),
                "is_burst": file_info.get("is_burst", False),
                "is_lightweight": file_info.get("is_lightweight", False),
                "classification": {
                    "species": [],
                    "counts": {},
                    "behaviors": [],
                    "optional_tags": []
                },
                "metadata": {
                    "site": site,
                    "subsite": subsite,
                    "camera": camera,
                    "operator": folder_metadata.get("operator", ""),
                    "recorded_at": file_info.get("recorded_at", ""),
                    "notes": ""
                },
                "ui": {
                    "is_favorite": False,
                    "is_excluded": False,
                    "embed_metadata": False,
                    "xlsx": False
                },
                "session": {
                    "session_id": session_id,
                    "camtrap_db_session": False,
                    "deployment_id": deployment_id
                }
            }
            
            video_meta["file"] = {
                "video_path": video_meta["video_path"],
                "video_hash": video_meta["video_hash"],
                "frames_folder": video_meta["frames_folder"],
                "promedio": video_meta["promedio"],
                "tops": video_meta["tops"],
                "mask": video_meta["mask"]
            }
            
            all_videos.append(video_meta)
    
    # Ordenar por recorded_at
    all_videos.sort(key=lambda x: x.get("metadata", {}).get("recorded_at", ""))
    
    # Crear carpeta de sesión
    session_folder = os.path.join(output_folder, "sessions", session_id)
    os.makedirs(session_folder, exist_ok=True)
    metadata_path = os.path.join(session_folder, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=4, ensure_ascii=False)
    
    manifest["session_id"] = session_id
    manifest["status"] = "ready_for_tagging"
    _save_manifest(manifest, manifest_path)
    
    print(f"[Batch] ✅ Sesión creada: {metadata_path}")
    print(f"[Batch]    {len(all_videos)} archivos listos para etiquetar "
          f"({sum(1 for v in all_videos if v.get('is_photo'))} fotos, "
          f"{sum(1 for v in all_videos if not v.get('is_photo'))} videos)")
    return metadata_path

# =============================================================================
# UTILIDADES
# =============================================================================
def get_batch_status(manifest_path):
    """
    Obtiene el estado actual de un batch.
    🔒 ACTUALIZADO: Incluye estadísticas de videos/fotos/lightweight.
    """
    if not os.path.exists(manifest_path):
        return None
    
    manifest = load_manifest(manifest_path)
    total_folders = len(manifest["folders"])
    completed = sum(1 for f in manifest["folders"].values() if f["status"] in ("completed", "completed_with_errors"))
    pending = sum(1 for f in manifest["folders"].values() if f["status"] == "pending")
    errors = sum(1 for f in manifest["folders"].values() if f["status"] == "error")
    
    total_files = 0
    processed_files = 0
    total_videos = 0
    total_photos = 0
    lightweight_photos = 0
    
    for folder_info in manifest["folders"].values():
        files = folder_info.get("files", [])
        total_files += folder_info.get("video_count", 0) + folder_info.get("photo_count", 0)
        processed_files += len(files)
        total_videos += folder_info.get("videos_processed", 0)
        total_photos += folder_info.get("photos_processed", 0)
        lightweight_photos += folder_info.get("lightweight_photos", 0)
    
    return {
        "status": manifest["status"],
        "batch_id": manifest.get("batch_id", ""),
        "created_at": manifest.get("created_at", ""),
        "burst_size": manifest.get("burst_size", 3),
        "total_folders": total_folders,
        "completed_folders": completed,
        "pending_folders": pending,
        "error_folders": errors,
        "total_files": total_files,
        "processed_files": processed_files,
        "total_videos": total_videos,
        "total_photos": total_photos,
        "lightweight_photos": lightweight_photos
    }

def cleanup_batch_temp(output_folder):
    """Limpia la carpeta temporal de batch después de procesar."""
    temp_folder = os.path.join(output_folder, "batch_temp")
    if os.path.exists(temp_folder):
        try:
            shutil.rmtree(temp_folder)
            print(f"[Batch] 🧹 Carpeta temporal eliminada: {temp_folder}")
        except Exception as e:
            print(f"[Batch] ⚠️ No se pudo eliminar carpeta temporal: {e}")

def discard_batch(output_folder):
    """Descarta completamente un batch."""
    batch_folder = os.path.join(output_folder, "batch")
    manifest_path = os.path.join(batch_folder, "batch_manifest.json")
    if not os.path.exists(manifest_path):
        return False
    
    try:
        manifest = load_manifest(manifest_path)
        session_id = manifest.get("session_id", "")
        
        if session_id:
            session_folder = os.path.join(output_folder, "sessions", session_id)
            if os.path.exists(session_folder):
                shutil.rmtree(session_folder)
                print(f"[Batch] 🗑️ Sesión eliminada: {session_id}")
        
        shutil.rmtree(batch_folder)
        print(f"[Batch] 🗑️ Lote descartado: {batch_folder}")
        
        temp_folder = os.path.join(output_folder, "batch_temp")
        if os.path.exists(temp_folder):
            shutil.rmtree(temp_folder)
        
        return True
    except Exception as e:
        print(f"[Batch] ❌ Error descartando lote: {e}")
        return False