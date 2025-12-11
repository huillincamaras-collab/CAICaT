import os
import json
import uuid
from datetime import datetime
import threading
import socket
CONFIG_FILENAME = "config.ini"
metadata_lock = threading.Lock()

# ---------------------------
# Path de config
# ---------------------------
def get_config_path():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), CONFIG_FILENAME)

# ---------------------------
# Generar PC ID
# ---------------------------
def generate_pc_id():
    """
    Genera un ID único de PC basado en la dirección MAC de la interfaz de red.
    Retorna un string de 12 caracteres hexadecimales en mayúsculas.
    """
    try:
        mac_num = uuid.getnode()
        # Verificar que sea una MAC válida (no local/aleatoria)
        if (mac_num >> 40) & 1 == 0:  # bit de difusión no activado → dirección global
            return f"{mac_num:012X}"[-12:]
        else:
            # Si es MAC local, aún la usamos (mejor que fallback)
            return f"{mac_num:012X}"[-12:]
    except Exception:
        # Fallback: usar hostname limpio y rellenar a 12 caracteres
        host = socket.gethostname().replace('-', '').replace('_', '').replace('.', '').upper()
        return (host + "000000000000")[:12]

# ---------------------------
# Generar Session ID
# ---------------------------
def generate_session_id(config=None):
    """
    Genera un ID de sesión legible, corto y ordenable cronológicamente:
    {YYMMDD}_{HHMMSS}_{pc_id_corto}
    
    - YYMMDD: año (2 dígitos), mes, día
    - HHMMSS: hora, minuto, segundo
    - pc_id_corto: primeros 6 caracteres del ID de PC (basado en MAC)
    
    Ejemplo: 251025_143022_A1B2C3
    """
    if config is None:
        pc_id = generate_pc_id()
    else:
        pc_id = config.get("General", {}).get("pc_id", generate_pc_id())
    
    short_pc_id = pc_id[:6]  # 6 caracteres hexadecimales
    timestamp_date = datetime.now().strftime("%y%m%d")  # YYMMDD
    timestamp_time = datetime.now().strftime("%H%M%S")  # HHMMSS
    return f"{timestamp_date}_{timestamp_time}_{short_pc_id}"

# ---------------------------
# Metadata base
# ---------------------------
def get_default_metadata_model():
    return {
        "session_id": "",
        "project": "",
        "deployment": "",
        "site": "",
        "subsite": "",
        "camera": "",
        "operator": "",
        "video_path": "",
        "frames_folder": "",
        "promedio": "",
        "mask": "",
        "tops": [],
        "tags": [],
        "behaviors": [],
        "status": "",
        "frames": 0,
        "time_sec": 0.0,
        "temp": "",
        "moon": "",
        "weather": "",
        "recorded_at": ""
    }

# ---------------------------
# Config por defecto (para setup)
# ---------------------------
# ---------------------------
# Config por defecto (para setup)
# ---------------------------
def get_default_config():
    output_folder = os.path.join(os.path.abspath(os.path.dirname(__file__)), "output")
    default_config = { # <-- Creamos el diccionario en una variable
        "General": {
            "pc_id": str(uuid.uuid4()),
            "output_folder": output_folder,
            "json_file": os.path.join(output_folder, "videos_metadata.json")
        },
        "Labels": {
            "btn_etiquetar_videos": "Etiquetar",
            "btn_generar_excel": "Generar Excel",
            "btn_rename_sort": "Sort & Rename",
            "btn_setup": "SETUP"
        },
        "GUI_Inicial": {
            "title": "Configuración inicial - Cámaras Trampa",
            "geometry": "400x400",
            "labels": {
                "input_folder": "Carpeta de videos:",
                "site": "Sitio:",
                "subsite": "Subsitio:",
                "camera": "Cámara:",
                "operator": "Operador:"
            },
            "buttons": {
                "browse_input": "Seleccionar",
                "start": "Iniciar"
            }
        },
        "GUI_Tagger": {
            "title": "Dynamic Video Tagger",
            "geometry": "1300x750",
            "species_tags": ["Huillin", "Ave"],
            "secondary_tags": ["Otros","Personas","Setup","Zorro","Roedor","Vison","Perro","Vacio"],
            "behavior_tags": ["Duerme","Vocaliza","Acicala","Juega","Corre","Camina","Come","Mojado","Seco"],
            "other_tags_list": ["Ciervo","Gato","Murcielago","Monito","Jabali","Pudu","Oveja","Vaca","Caballo","Otro"],
            "colors": {
                "species_buttons": ["orange","green"],
                "behavior_default": "#f0f0f0",
                "behavior_active": "yellow"
            },
            "labels": {
                "count": "Cantidad:",
                "video_processing": "Procesando video...",
                "video_prefix": "Video:",
                "frame_info": "Frame",
                "species_tags": "Tags especie:",
                "behavior_tags": "Tags comportamiento:"
            },
            "buttons": {
                "prev_frame": "<< Frame",
                "next_frame": "Frame >>",
                "prev_video": "<< Video",
                "next_video": "Video >>"
            }
        },
        "Processing": {
            "FPS_EXTRACT": 1,
            "BUFFER_N": 15,
            "TOP_K": 6,
            "DOWNSAMPLE_MAX": 320,
            "JPEG_QUALITY": 85,
            "MASK_QUALITY": 70
        },
        "SummaryGlobal": {
            "total_sessions": 0,
            "total_sites": 0,
            "list_sites": [],
            "total_videos_processed": 0,
            "list_operators": [],
            "total_species_identified": 0
        },
        "LastSession": {
            "operator": "",
            "site_subsite_camera": "",
            "date": "",
            "session_id": "",
            "videos_processed": 0,
            "species_identified": []
        },
        "MetadataSettings": {
            "model": get_default_metadata_model(),
            "fields_to_embed": [
                "session_id","project","deployment","site","subsite","camera",
                "operator","tags","behaviors","status","frames","time_sec","temp","moon","weather"
            ],
            "ExcelFieldsDefault": [
                "session_id","site","subsite","camera","operator","tags","time_sec",
                "temp","moon","weather","recorded_at"
            ]
        },
        # Añadir la sección CamtrapDB vacía aquí también
        "CamtrapDB": {}
    }

    # --- AÑADIR ESTA LÍNEA DENTRO DE LA FUNCIÓN, PERO ANTES DEL RETURN ---
    # Asegurar que camtrap_mode esté en GUI_Tagger con valor por defecto False
    default_config["GUI_Tagger"]["camtrap_mode"] = False
    # --- FIN AÑADIDO ---

    return default_config # <-- Retornamos la variable

# ---------------------------
# Cargar config (crear si no existe)
# ---------------------------
def load_config():
    config_path = get_config_path()
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = get_default_config()
        os.makedirs(config["General"]["output_folder"], exist_ok=True)
        save_config(config)

    # Asegurarse de que secciones y claves por defecto existan, añadirlas si no
    default_config = get_default_config()

    # Asegurar sección General
    if "General" not in config:
        config["General"] = default_config["General"]
    # Asegurar sección GUI_Tagger
    if "GUI_Tagger" not in config:
        config["GUI_Tagger"] = default_config["GUI_Tagger"]
    else:
        # Verificar y añadir subclaves faltantes en GUI_Tagger si es necesario
        if "other_tags_list" not in config["GUI_Tagger"]:
            config["GUI_Tagger"]["other_tags_list"] = default_config["GUI_Tagger"]["other_tags_list"]
        # --- AÑADIR ESTE BLOQUE ---
        # Asegurar que camtrap_mode exista en GUI_Tagger
        if "camtrap_mode" not in config["GUI_Tagger"]:
            config["GUI_Tagger"]["camtrap_mode"] = default_config["GUI_Tagger"]["camtrap_mode"]
        # --- FIN AÑADIDO ---
    # Asegurar sección CamtrapDB (aunque esté vacía por ahora)
    if "CamtrapDB" not in config:
        config["CamtrapDB"] = default_config["CamtrapDB"]

    # Si se modificó la config (añadiendo claves faltantes), guardarla
    # Solo guardar si el archivo ya existía originalmente y lo modificamos
    if os.path.exists(config_path) and (
        "other_tags_list" not in config["GUI_Tagger"] or
        "camtrap_mode" not in config["GUI_Tagger"] or
        "CamtrapDB" not in config
    ):
        save_config(config)

    return config

# ---------------------------
# Guardar config
# ---------------------------
def save_config(config):
    config_path = get_config_path()
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

# ---------------------------
# Obtener campos para embed
# ---------------------------
def get_fields_to_embed(config=None):
    if config is None:
        config = load_config()
    return config.get("MetadataSettings", {}).get("fields_to_embed", [])

def get_excel_fields_default(config=None):
    if config is None:
        config = load_config()
    return config.get("MetadataSettings", {}).get("ExcelFieldsDefault", [])

# ---------------------------
# Actualizar resúmenes
# ---------------------------
def update_summaries_from_metadata(config=None, metadata_path=None):
    if config is None:
        config = load_config()
    if metadata_path is None:
        metadata_path = os.path.join(config["General"]["output_folder"], "consolidated", "all_sessions_metadata.json")
    if not os.path.exists(metadata_path):
        print(f"[update_summaries_from_metadata] No existe videos_metadata.json en {metadata_path}")
        return config

    with metadata_lock:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)

    sessions = {}
    total_videos = 0
    species_all = set()
    operators = set()
    sites = set()

    for entry in metadata:
        session_id = entry.get("session_id", "")
        site = entry.get("site", "")
        operator = entry.get("operator", "")
        tags = entry.get("tags", [])

        total_videos += 1
        species_all.update(tags)
        if site:
            sites.add(site)
        if operator:
            operators.add(operator)

        if session_id not in sessions:
            sessions[session_id] = {
                "session_id": session_id,
                "videos_processed": 0,
                "species_identified": set(),
                "site": site,
                "operator": operator,
                "date": entry.get("date", "")
            }
        sessions[session_id]["videos_processed"] += 1
        sessions[session_id]["species_identified"].update(tags)

    config["SummaryGlobal"] = {
        "total_sessions": len(sessions),
        "total_sites": len(sites),
        "list_sites": list(sites),
        "total_videos_processed": total_videos,
        "list_operators": list(operators),
        "total_species_identified": len(species_all)
    }

    if sessions:
        last_session_id = sorted(sessions.keys())[-1]
        s = sessions[last_session_id]
        config["LastSession"] = {
            "operator": s["operator"],
            "site_subsite_camera": s["site"],
            "date": s["date"],
            "session_id": s["session_id"],
            "videos_processed": s["videos_processed"],
            "species_identified": list(s["species_identified"])
        }

    save_config(config)
    return config
# ---------------------------
# Reconstruir archivo consolidado desde sesiones
# ---------------------------
def rebuild_consolidated_metadata(config=None):
    """
    Reconstruye output_folder/consolidated/all_sessions_metadata.json
    combinando todos los metadata.json de output_folder/sessions/.
    Útil si el archivo consolidado se corrompe o se elimina.
    """
    if config is None:
        config = load_config()
    
    output_folder = config["General"]["output_folder"]
    sessions_dir = os.path.join(output_folder, "sessions")
    consolidated_dir = os.path.join(output_folder, "consolidated")
    consolidated_path = os.path.join(consolidated_dir, "all_sessions_metadata.json")
    
    if not os.path.exists(sessions_dir):
        print(f"[rebuild_consolidated_metadata] No existe la carpeta de sesiones: {sessions_dir}")
        return []

    os.makedirs(consolidated_dir, exist_ok=True)
    
    all_videos = []
    for session_id in os.listdir(sessions_dir):
        session_path = os.path.join(sessions_dir, session_id)
        if not os.path.isdir(session_path):
            continue
        
        metadata_path = os.path.join(session_path, "metadata.json")
        if not os.path.exists(metadata_path):
            continue
        
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                session_metadata = json.load(f)
                # Asegurarse de que cada entrada tenga session_id
                for entry in session_metadata:
                    if "session_id" not in entry or not entry["session_id"]:
                        entry["session_id"] = session_id
                all_videos.extend(session_metadata)
        except Exception as e:
            print(f"[rebuild_consolidated_metadata] Error leyendo {metadata_path}: {e}")
            continue

    # Eliminar duplicados por video_path (mantener la última versión)
    seen = {}
    unique_videos = []
    for video in reversed(all_videos):  # última versión primero
        path = video.get("video_path")
        if path and path not in seen:
            seen[path] = True
            unique_videos.append(video)
    unique_videos.reverse()  # restaurar orden cronológico

    with metadata_lock:
        with open(consolidated_path, "w", encoding="utf-8") as f:
            json.dump(unique_videos, f, indent=4, ensure_ascii=False)
    
    print(f"[rebuild_consolidated_metadata] Archivo consolidado reconstruido: {consolidated_path}")
    return unique_videos