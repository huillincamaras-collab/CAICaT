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

def get_tagger_configs_dir():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "tagger_configs")

def get_species_csv_path():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "species_list.csv")

# ---------------------------
# Generar PC ID
# ---------------------------
def generate_pc_id():
    try:
        mac_num = uuid.getnode()
        if (mac_num >> 40) & 1 == 0:
            return f"{mac_num:012X}"[-12:]
        else:
            return f"{mac_num:012X}"[-12:]
    except Exception:
        host = socket.gethostname().replace('-', '').replace('_', '').replace('.', '').upper()
        return (host + "000000000000")[:12]

# ---------------------------
# Generar Session ID
# ---------------------------
def generate_session_id(config=None):
    if config is None:
        pc_id = generate_pc_id()
    else:
        pc_id = config.get("General", {}).get("pc_id", generate_pc_id())
    short_pc_id = pc_id[:6]
    timestamp_date = datetime.now().strftime("%y%m%d")
    timestamp_time = datetime.now().strftime("%H%M%S")
    return f"{timestamp_date}_{timestamp_time}_{short_pc_id}"

# ---------------------------
# Metadata base
# ---------------------------
def get_default_metadata_model():
    return {
        "media_id": "",
        "event_id": "",
        "deployment_id": "",
        "file": {
            "video_path": "",
            "video_hash": "",
            "frames_folder": "",
            "promedio": None,
            "tops": [],
            "mask": None
        },
        "processing": {
            "status": "pending",
            "frames": None,
            "time_sec": None
        },
        "classification": {
            "species": [],
            "counts": {},
            "behaviors": []
        },
        "metadata": {
            "site": "",
            "subsite": "",
            "camera": "",
            "operator": "",
            "recorded_at": "",
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
            "camtrap_db_session": False
        }
    }

def normalize_video_meta(video_meta):
    from copy import deepcopy
    base = get_default_metadata_model()
    new_meta = deepcopy(base)

    new_meta["media_id"] = video_meta.get("video_hash", "")
    new_meta["event_id"] = video_meta.get("video_hash", "")
    new_meta["deployment_id"] = video_meta.get("camera", "")

    new_meta["file"]["video_path"] = video_meta.get("video_path", "")
    new_meta["file"]["video_hash"] = video_meta.get("video_hash", "")
    new_meta["file"]["frames_folder"] = video_meta.get("frames_folder", "")
    new_meta["file"]["promedio"] = video_meta.get("promedio")
    new_meta["file"]["tops"] = video_meta.get("tops", [])
    new_meta["file"]["mask"] = video_meta.get("mask")

    new_meta["processing"]["status"] = video_meta.get("status", "pending")
    new_meta["processing"]["frames"] = video_meta.get("frames")
    new_meta["processing"]["time_sec"] = video_meta.get("time_sec")

    new_meta["classification"]["species"] = video_meta.get("tags", [])
    new_meta["classification"]["counts"] = video_meta.get("species_counts", {})
    new_meta["classification"]["behaviors"] = video_meta.get("behaviors", [])

    new_meta["metadata"]["site"] = video_meta.get("site", "")
    new_meta["metadata"]["subsite"] = video_meta.get("subsite", "")
    new_meta["metadata"]["camera"] = video_meta.get("camera", "")
    new_meta["metadata"]["operator"] = video_meta.get("operator", "")
    new_meta["metadata"]["recorded_at"] = video_meta.get("recorded_at", "")
    new_meta["metadata"]["notes"] = video_meta.get("notes", "")

    new_meta["ui"]["is_favorite"] = video_meta.get("is_favorite", False)
    new_meta["ui"]["is_excluded"] = video_meta.get("is_excluded", False)
    new_meta["ui"]["embed_metadata"] = video_meta.get("embed_metadata", False)
    new_meta["ui"]["xlsx"] = video_meta.get("xlsx", False)

    new_meta["session"]["session_id"] = video_meta.get("session_id", "")
    new_meta["session"]["camtrap_db_session"] = video_meta.get("camtrap_db_session", False)

    new_meta["tags"] = new_meta["classification"]["species"]
    new_meta["species_counts"] = new_meta["classification"]["counts"]
    new_meta["behaviors"] = new_meta["classification"]["behaviors"]

    new_meta["site"] = new_meta["metadata"]["site"]
    new_meta["subsite"] = new_meta["metadata"]["subsite"]
    new_meta["camera"] = new_meta["metadata"]["camera"]
    new_meta["operator"] = new_meta["metadata"]["operator"]
    new_meta["recorded_at"] = new_meta["metadata"]["recorded_at"]
    new_meta["notes"] = new_meta["metadata"]["notes"]

    new_meta["embed_metadata"] = new_meta["ui"]["embed_metadata"]
    new_meta["xlsx"] = new_meta["ui"]["xlsx"]
    new_meta["is_favorite"] = new_meta["ui"]["is_favorite"]
    new_meta["is_excluded"] = new_meta["ui"]["is_excluded"]

    return new_meta

# ---------------------------
# Config por defecto
# ---------------------------
def get_default_config():
    output_folder = os.path.join(os.path.abspath(os.path.dirname(__file__)), "output")
    default_config = {
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
            },
            "camtrap_mode": False,
            "last_tagger_config": "",
            "taxon_map": {}
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
        "CamtrapDB": {}
    }
    default_config["GUI_Tagger"]["camtrap_mode"] = False
    return default_config

# ---------------------------
# Cargar config
# ---------------------------
def load_config():
    config_path = get_config_path()
    config_modified = False

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = get_default_config()
        os.makedirs(config["General"]["output_folder"], exist_ok=True)
        save_config(config)
        return config

    default_config = get_default_config()

    if "General" not in config:
        config["General"] = default_config["General"]
        config_modified = True

    if "GUI_Tagger" not in config:
        config["GUI_Tagger"] = default_config["GUI_Tagger"]
        config_modified = True
    else:
        for key in ("other_tags_list", "camtrap_mode", "last_tagger_config", "taxon_map"):
            if key not in config["GUI_Tagger"]:
                config["GUI_Tagger"][key] = default_config["GUI_Tagger"][key]
                config_modified = True

    if "CamtrapDB" not in config:
        config["CamtrapDB"] = default_config["CamtrapDB"]
        config_modified = True

    if config_modified:
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
# Tagger configs
# ---------------------------
def list_tagger_configs():
    """Retorna lista de dicts con {path, name} de cada config disponible."""
    configs_dir = get_tagger_configs_dir()
    if not os.path.exists(configs_dir):
        return []
    result = []
    for fname in sorted(os.listdir(configs_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(configs_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("_metadata", {}).get("name", fname)
            result.append({"path": fpath, "name": name, "filename": fname})
        except Exception:
            result.append({"path": fpath, "name": fname, "filename": fname})
    return result

def load_tagger_config(json_path):
    """Carga un archivo de config del tagger y retorna el dict."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tagger_config(json_path, data):
    """Guarda un archivo de config del tagger."""
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    data["_metadata"]["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def apply_tagger_config(tagger_config_data, app_config):
    """
    Aplica los valores de GUI_Tagger y Taxon_Map de tagger_config_data
    sobre app_config en memoria y actualiza last_tagger_config.
    No guarda en disco — el llamador decide cuándo llamar save_config.
    """
    gui_tagger_keys = ("species_tags", "secondary_tags", "behavior_tags", "other_tags_list")
    for key in gui_tagger_keys:
        if key in tagger_config_data.get("GUI_Tagger", {}):
            app_config["GUI_Tagger"][key] = tagger_config_data["GUI_Tagger"][key]
    app_config["GUI_Tagger"]["taxon_map"] = tagger_config_data.get("Taxon_Map", {})
    return app_config

def set_last_tagger_config(config, json_path):
    """Registra la última config de tagger usada en config.ini."""
    config["GUI_Tagger"]["last_tagger_config"] = json_path
    save_config(config)

def get_last_tagger_config(config):
    """Retorna la ruta de la última config usada, o '' si no existe."""
    return config.get("GUI_Tagger", {}).get("last_tagger_config", "")

def get_template_tagger_config():
    """Retorna la plantilla base para crear una nueva config."""
    template_path = os.path.join(get_tagger_configs_dir(), "template.json")
    if os.path.exists(template_path):
        return load_tagger_config(template_path)
    return {
        "_metadata": {
            "name": "", "version": "1.0", "region": "", "description": "",
            "created": "", "last_modified": "", "is_scientific": False  # 🔹 NUEVO
        },
        "GUI_Tagger": {"species_tags": [], "secondary_tags": [], "behavior_tags": [], "other_tags_list": []},
        "Taxon_Map": {}
    }
# ---------------------------
# Búsqueda de taxones
# ---------------------------
def _normalize_text(text):
    """Normaliza texto: minúsculas y sin acentos."""
    import unicodedata
    text = text.lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

def search_taxa_local(query, max_results=20):
    """
    Busca en species_list.csv por nombre vernáculo, científico o taxonID.
    Insensible a acentos y mayúsculas. Busca en todos los campos.
    Retorna lista de dicts con las columnas del CSV.
    """
    import csv
    csv_path = get_species_csv_path()
    if not os.path.exists(csv_path):
        return []

    q = _normalize_text(query)
    results = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                searchable = " ".join([
                    row.get("scientificName", ""),
                    row.get("vernacularName", ""),
                    row.get("taxonID", ""),
                    row.get("taxonRank", ""),
                    row.get("family", ""),
                    row.get("kingdom", "")
                ])
                if q in _normalize_text(searchable):
                    results.append(dict(row))
                    if len(results) >= max_results:
                        break
    except Exception as e:
        print(f"[search_taxa_local] Error: {e}")
    return results

def search_taxa_gbif(query, max_results=20):
    """
    Busca en la API de GBIF por nombre vernáculo o científico.
    Retorna lista de dicts normalizados con las mismas claves que el CSV local.
    """
    try:
        import requests
        url = "https://api.gbif.org/v1/species/search"
        params = {"q": query, "limit": max_results}
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("results", []):
            vernacular = ""
            if item.get("vernacularNames"):
                # Preferir español, luego cualquier idioma
                for vn in item["vernacularNames"]:
                    if vn.get("language") in ("spa", "es"):
                        vernacular = vn.get("vernacularName", "")
                        break
                if not vernacular:
                    vernacular = item["vernacularNames"][0].get("vernacularName", "")
            results.append({
                "taxonID": str(item.get("key", "")),
                "scientificName": item.get("canonicalName", item.get("scientificName", "")),
                "vernacularName": vernacular,
                "taxonRank": item.get("rank", "").lower(),
                "kingdom": item.get("kingdom", ""),
                "family": item.get("family", "")
            })
        return results
    except Exception as e:
        print(f"[search_taxa_gbif] Error: {e}")
        return []

def search_taxa(query, max_results=20):
    """
    Busca primero en local, luego ofrece resultados de GBIF si hay pocos locales.
    Retorna (local_results, gbif_results).
    """
    local = search_taxa_local(query, max_results)
    return local

# ---------------------------
# Campos para embed/excel
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

def get_processing_config(config=None):
    if config is None:
        config = load_config()
    return config.get("Processing", {})

# ---------------------------
# Reconstruir consolidado
# ---------------------------
def rebuild_consolidated_metadata(config=None):
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
                for entry in session_metadata:
                    if "session_id" not in entry or not entry["session_id"]:
                        entry["session_id"] = session_id
                all_videos.extend(session_metadata)
        except Exception as e:
            print(f"[rebuild_consolidated_metadata] Error leyendo {metadata_path}: {e}")
            continue

    seen = {}
    unique_videos = []
    for video in reversed(all_videos):
        path = video.get("video_path")
        if path and path not in seen:
            seen[path] = True
            unique_videos.append(video)
    unique_videos.reverse()

    with metadata_lock:
        with open(consolidated_path, "w", encoding="utf-8") as f:
            json.dump(unique_videos, f, indent=4, ensure_ascii=False)

    print(f"[rebuild_consolidated_metadata] Archivo consolidado reconstruido: {consolidated_path}")
    return unique_videos
