import os
import json
import uuid
from datetime import datetime
import threading
import socket
import requests  # type: ignore
CONFIG_FILENAME = "config.ini"
metadata_lock = threading.RLock()  # 🔒 FIX BUG-002: Use RLock for nested locking

# ---------------------------
# Path de config
# ---------------------------
def get_config_path():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), CONFIG_FILENAME)

def get_tagger_configs_dir():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "tagger_configs")

def get_species_csv_path():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "species_list.csv")

def get_regions_dir():
    """Get the path to the regions directory"""
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "regions")

def get_master_species_path():
    """Get the path to the master species list"""
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "species_master_ecuador.json")

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

        "classification ": {
        "species ": [],
        "counts ": {},
        "behaviors ": [],
        "optional_tags ": []
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
    new_meta["classification"]["optional_tags"] = video_meta.get("optional_tags", []) or video_meta.get("custom_tags", [])

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
                "input_folder": "Carpeta de videos: ",
                "site": "Sitio: ",
                "subsite": "Subsitio: ",
                "camera": "Cámara: ",
                "operator": "Operador: "
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
            "secondary_tags": ["Otros", "Personas", "Setup", "Zorro", "Roedor", "Vison", "Perro", "Vacio"],
            "behavior_tags": ["Duerme", "Vocaliza", "Acicala", "Juega", "Corre", "Camina", "Come", "Mojado", "Seco"],
            "other_tags_list ": [ "Ciervo ",  "Gato ",  "Murcielago ",  "Monito ",  "Jabali ",  "Pudu ",  "Oveja ",  "Vaca ",  "Caballo ",  "Otro "],
            "optional_tags ": [],
            "colors ": {
                "species_buttons": ["orange", "green"],
                "behavior_default": "#f0f0f0",
                "behavior_active": "yellow"
            },
            "labels": {
                "count": "Cantidad: ",
                "video_processing": "Procesando video...",
                "video_prefix": "Video: ",
                "frame_info": "Frame ",
                "species_tags": "Tags especie: ",
                "behavior_tags": "Tags comportamiento: "
            },
            "buttons": {
                "prev_frame": "<< Frame",
                "next_frame": "Frame >>",
                "prev_video": "<< Video",
                "next_video": "Video >>"
            },
            "camtrap_mode": False,
            "taxon_map": {}
        },
        "Processing": {
            "FPS_EXTRACT": 1,
            "BUFFER_N": 15,
            "TOP_K": 6,
            "DOWNSAMPLE_MAX": 320,
            "JPEG_QUALITY": 85,
            "MASK_QUALITY": 70,
            "LegacyParams": {
                "FPS_EXTRACT": 0.3,
                "BUFFER_N": 10,
                "TOP_K": 3,
                "MAX_FRAMES": 50,
                "OUTPUT_SIZE": [912, 513],
                "JPEG_QUALITY": 75,
                "MASK_QUALITY": 65,
                "MASK_OFFSET": 50,
                "MASK_SATURATED": 0.01,
                "TIMEOUT_SECONDS": 10,
                "SLOW_EXTRACTION_TIMEOUT": 5
            }
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
                "session_id", "site", "subsite", "camera", "operator",
                "species", "behaviors", "status", "frames", "time_sec",
                "recorded_at", "notes"
            ],
            "ExcelFieldsDefault": [
                "session_id", "site", "subsite", "camera", "operator",
                "recorded_at", "species", "behaviors", "counts", "notes", "time_sec"
            ]
        },
        "INABIO": {
            "institutionCode": "INABIOEC",
            "collectionCode": "CAMTRAP",
            "ownerInstitutionCode": "INABIO",
            "country": "Ecuador",
            "basisOfRecord": "HumanObservation",
            "language": "es",
            "rights": "CC-BY-4.0",
            "rightsHolder": "CAICAT Project",
            "accessRights": "https://creativecommons.org/licenses/by/4.0/"
        },
        "CamtrapDB": {},
        "Auditor": {"is_enabled": False}
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

        # ✅ FIX: Migración automática de config.ini viejo con keys con espacios
        # Detecta claves como "General ", "Auditor  ", etc. y las normaliza
        sections_to_migrate = [
            "General", "Labels", "GUI_Inicial", "GUI_Tagger", "Processing",
            "SummaryGlobal", "LastSession", "MetadataSettings", "INABIO",
            "CamtrapDB", "Auditor"
        ]
        
        # Migrar claves de sección (ej: "General " → "General")
        for section in sections_to_migrate:
            # Buscar variantes con espacios
            for variant in [f"{section} ", f"{section}  ", f" {section}", f"  {section}"]:
                if variant in config:
                    if section not in config:
                        config[section] = config.pop(variant)
                    else:
                        config.pop(variant)
                    config_modified = True

        # Migrar claves internas con espacios (ej: "pc_id " → "pc_id")
        for section in sections_to_migrate:
            if section not in config or not isinstance(config[section], dict):
                continue
            new_section = {}
            section_modified = False
            for k, v in config[section].items():
                clean_k = k.rstrip()
                if clean_k != k:
                    section_modified = True
                new_section[clean_k] = v
            if section_modified:
                config[section] = new_section
                config_modified = True
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
        for key in ("other_tags_list", "camtrap_mode", "taxon_map"):
            if key not in config["GUI_Tagger"]:
                config["GUI_Tagger"][key] = default_config["GUI_Tagger"][key]
                config_modified = True
    if "CamtrapDB" not in config:
        config["CamtrapDB"] = default_config["CamtrapDB"]
        config_modified = True
    if "Auditor" not in config:
        config["Auditor"] = {"is_enabled": False}
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
    sobre app_config en memoria.
    No guarda en disco — el llamador decide cuándo llamar save_config.
    """
    gui_tagger_keys = ( "species_tags ",  "secondary_tags ",  "behavior_tags ",  "other_tags_list ",  "optional_tags ")
    for key in gui_tagger_keys:
        if key in tagger_config_data.get("GUI_Tagger", {}):
            app_config["GUI_Tagger"][key] = tagger_config_data["GUI_Tagger"][key]
    app_config["GUI_Tagger"]["taxon_map"] = tagger_config_data.get("Taxon_Map", {})
    return app_config

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
# Region management functions
# ---------------------------
def get_available_regions():
    """
    Scans config/regions/ and returns a list of available regions.
    Returns: List of dicts with {id, name, code, species_count}
    """
    regions_dir = get_regions_dir()
    if not os.path.exists(regions_dir):
        return []
    
    regions = []
    for filename in sorted(os.listdir(regions_dir)):
        if not filename.endswith('.json'):
            continue
        
        filepath = os.path.join(regions_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = data.get('metadata', {})
            regions.append({
                'id': metadata.get('region_id', filename.replace('.json', '')),
                'name': metadata.get('region_name', filename),
                'code': metadata.get('region_code', ''),
                'species_count': metadata.get('species_count', 0),
                'filepath': filepath
            })
        except Exception as e:
            print(f"[get_available_regions] Error reading {filename}: {e}")
            continue
    
    return regions

def load_region_species(region_id):
    """
    Loads the species list for a specific region.
    Args:
        region_id: Region identifier (e.g., 'llanganates', 'atillo', 'master')
    Returns:
        List of species dicts, or empty list if region not found
    """
    if region_id == 'master' or region_id == 'all':
        # Load master species list
        master_path = get_master_species_path()
        if os.path.exists(master_path):
            try:
                with open(master_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('species', [])
            except Exception as e:
                print(f"[load_region_species] Error loading master list: {e}")
                return []
    else:
        # Load specific region
        region_file = os.path.join(get_regions_dir(), f"{region_id}.json")
        if os.path.exists(region_file):
            try:
                with open(region_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('species', [])
            except Exception as e:
                print(f"[load_region_species] Error loading region {region_id}: {e}")
                return []
    
    return []

def get_default_region_id(config=None):
    """Get the default region ID from config"""
    if config is None:
        config = load_config()
    return config.get("GUI_Tagger", {}).get("default_region_id", "master")

def set_default_region_id(config, region_id):
    """Set the default region ID in config"""
    config.setdefault("GUI_Tagger", {})
    config["GUI_Tagger"]["default_region_id"] = region_id
    save_config(config)

# ---------------------------
# Country/Region/Config Hierarchy Functions
# ---------------------------
def get_available_countries():
    """
    Scans config/paises/*.json files to get available countries.
    Returns: List of dicts with {country_id, name, species_count, master_path}
    """
    paises_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "paises")
    if not os.path.exists(paises_dir):
        return []
    
    countries = []
    
    for filename in os.listdir(paises_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(paises_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                metadata = data.get('metadata', {})
                countries.append({
                    'country_id': metadata.get('country_id', ''),
                    'name': metadata.get('country_name', filename.replace('species_master_', '').replace('.json', '').title()),
                    'species_count': metadata.get('total_species', len(data.get('species', []))),
                    'master_path': filepath
                })
            except Exception as e:
                print(f"[get_available_countries] Error reading {filename}: {e}")
                continue
    
    return sorted(countries, key=lambda x: x['name'])

def get_country_master_path(country_id):
    """
    Returns the path to species master in config/paises/
    """
    paises_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "paises")
    return os.path.join(paises_dir, f"species_master_{country_id}.json")

def load_country_species(country_id):
    """
    Loads the complete species list for a country (master).
    Args:
        country_id: Country identifier (e.g., 'ecuador', 'argentina')
    Returns:
        List of species dicts, or empty list if country not found
    """
    master_path = get_country_master_path(country_id)
    if os.path.exists(master_path):
        try:
            with open(master_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('species', [])
        except Exception as e:
            print(f"[load_country_species] Error loading {country_id}: {e}")
            return []
    return []

def get_regions_by_country(country_id):
    """
    Filters regions by country_id from config/regions/*.json
    Returns: List of dicts with {region_id, name, code, species_count, country_id, filepath}
    """
    regions_dir = get_regions_dir()
    if not os.path.exists(regions_dir):
        return []
    
    regions = []
    for filename in sorted(os.listdir(regions_dir)):
        if not filename.endswith('.json'):
            continue
        
        filepath = os.path.join(regions_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = data.get('metadata', {})
            region_country = metadata.get('country_id', '')
            
            # Filter by country
            if region_country == country_id:
                regions.append({
                    'region_id': metadata.get('region_id', filename.replace('.json', '')),
                    'name': metadata.get('region_name', filename),
                    'code': metadata.get('region_code', ''),
                    'species_count': metadata.get('species_count', 0),
                    'country_id': region_country,
                    'filepath': filepath
                })
        except Exception as e:
            print(f"[get_regions_by_country] Error reading {filename}: {e}")
            continue
    
    return regions

def get_configs_by_country_and_region(country_id, region_id):
    """
    Filters tagger configs by country_id and linked_region_id.
    Args:
        country_id: Country identifier
        region_id: Region identifier or "master" for all regions
    Returns: List of dicts with {path, name, country_id, linked_region_id, is_scientific}
    """
    configs_dir = get_tagger_configs_dir()
    if not os.path.exists(configs_dir):
        return []
    
    configs = []
    # 🔹 Búsqueda recursiva en subdirectorios
    for root, dirs, files in os.walk(configs_dir):
        for filename in sorted(files):
            if not filename.endswith('.json'):
                continue
            
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                metadata = data.get('_metadata', {})
                config_country = metadata.get('country_id', '')
                config_region = metadata.get('linked_region_id', '')
                
                # 🔹 Soporte para "Todos"
                country_match = (country_id == "todos" or config_country == country_id)
                region_match = (region_id == "todos" or config_region == region_id)
                
                # Filter by country and region
                if country_match and region_match:
                    configs.append({
                        'path': filepath,
                        'name': metadata.get('name', filename.replace('.json', '')),
                        'country_id': config_country,
                        'linked_region_id': config_region,
                        'is_scientific': metadata.get('is_scientific', False),
                        'description': metadata.get('description', '')
                    })
            except Exception as e:
                print(f"[get_configs_by_country_and_region] Error reading {filename}: {e}")
                continue
    
    return configs

def validate_species_duplicate(country_id, scientific_name, taxon_id=None):
    """
    Checks if a species already exists in the country master by scientific name or taxonID.
    Args:
        country_id: Country identifier
        scientific_name: Scientific name to check
        taxon_id: Optional taxonID to check
    Returns:
        None if species doesn't exist, dict with species info if it exists
    """
    species_list = load_country_species(country_id)
    
    for species in species_list:
        # Check by scientific name (case-insensitive)
        if species.get('scientificName', '').lower() == scientific_name.lower():
            return species
        
        # Check by taxonID if provided
        if taxon_id and species.get('taxonID', ''):
            # Extract numeric ID from URLs like "https://www.gbif.org/species/2433273"
            existing_id = species.get('taxonID', '').split('/')[-1]
            check_id = taxon_id.split('/')[-1] if '/' in taxon_id else taxon_id
            if existing_id == check_id:
                return species
    
    return None

def add_species_to_master_and_region(country_id, region_id, species_dict):
    """
    Adds a species to both the country master and the specified region.
    Validates for duplicates before adding.
    Args:
         country_id: Country identifier
         region_id: Region identifier (or "master" to add only to master)
         species_dict: Dict with species info (scientificName, commonName, family, order, class, taxonID)
     Returns:
         dict with {success: bool, message: str, duplicate: dict or None}
     """
    # Validate required fields
    if not species_dict.get('scientificName'):
        return {"success": False, "message": "scientificName is required", "duplicate": None}

    scientific_name = species_dict['scientificName']
    taxon_id = species_dict.get('taxonID', '')

    # Check for duplicates
    duplicate = validate_species_duplicate(country_id, scientific_name, taxon_id)
    if duplicate:
        return {
            "success": False,
            "message": f"Species already exists: {duplicate.get('scientificName', '')}",
            "duplicate": duplicate
        }

    # Add to master
    master_path = get_country_master_path(country_id)
    if not os.path.exists(master_path):
        return {"success": False, "message": f"Master file not found for country: {country_id}", "duplicate": None}

    try:
        with open(master_path, 'r', encoding='utf-8') as f:
            master_data = json.load(f)

        # Add species to master
        master_data['species'].append(species_dict)

        # Update species count
        master_data['metadata']['total_species'] = len(master_data['species'])
        master_data['metadata']['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Save master
        with open(master_path, 'w', encoding='utf-8') as f:
            json.dump(master_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Added {scientific_name} to master ({country_id})")

        # Add to region if not "master"
        if region_id != "master":
            # ✅ CAMBIO: usar {region_id}.json (decisión tomada en el proyecto)
            region_file = os.path.join(get_regions_dir(), f"{region_id}.json")
            if os.path.exists(region_file):
                with open(region_file, 'r', encoding='utf-8') as f:
                    region_data = json.load(f)

                # Add species to region (without taxonID if not needed)
                region_species = {
                    'scientificName': species_dict['scientificName'],
                    'family': species_dict.get('family', ''),
                    'order': species_dict.get('order', ''),
                    'class': species_dict.get('class', '')
                }
                region_data['species'].append(region_species)

                # Update species count
                region_data['metadata']['species_count'] = len(region_data['species'])
                region_data['metadata']['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Save region
                with open(region_file, 'w', encoding='utf-8') as f:
                    json.dump(region_data, f, indent=2, ensure_ascii=False)

                print(f"✓ Added {scientific_name} to region ({region_id})")

        return {
            "success": True,
            "message": f"Species added successfully: {scientific_name}",
            "duplicate": None
        }

    except Exception as e:
        return {"success": False, "message": f"Error adding species: {str(e)}", "duplicate": None}

def update_recent_configs(config_data, config_path, max_recent=5):
    """
    Updates the list of recently used configs in config_data.
    Maintains the last max_recent configs (most recent first).
    
    Args:
        config_data: The main config dict
        config_path: Path to the config that was just used
        max_recent: Maximum number of recent configs to keep
    """
    config_data.setdefault("General", {})
    recent = config_data["General"].get("last_used_configs", [])
    
    # Remove if already in list
    if config_path in recent:
        recent.remove(config_path)
    
    # Add to beginning
    recent.insert(0, config_path)
    
    # Keep only max_recent items
    config_data["General"]["last_used_configs"] = recent[:max_recent]
    
    save_config(config_data)

def get_recent_configs(config_data, max_recent=5):
    """
    Returns list of recent configs with metadata.
    If no recent configs exist, initializes with Ecuador and Argentina defaults.
    
    Returns:
        List of dicts with {path, name, country, country_id, region, region_id}
    """
    recent_paths = config_data.get("General", {}).get("last_used_configs", [])
    
    # 🔄 Initialize with default configs if empty
    if not recent_paths:
        configs_dir = get_tagger_configs_dir()
        default_configs = []
        
        # Try to find ecuador_master and argentina_master configs
        for fname in os.listdir(configs_dir):
            if not fname.endswith('.json'):
                continue
            if 'ecuador_master' in fname.lower() or 'argentina_master' in fname.lower():
                default_configs.append(os.path.join(configs_dir, fname))
        
        if default_configs:
            config_data.setdefault("General", {})["last_used_configs"] = default_configs[:max_recent]
            save_config(config_data)
            recent_paths = default_configs[:max_recent]
    
    recent_configs = []
    
    for path in recent_paths[:max_recent]:
        if not os.path.exists(path):
            continue
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = data.get('_metadata', {})
            country_id = metadata.get('country_id', '')
            region_id = metadata.get('linked_region_id', '')
            
            # Get country name
            country_name = country_id.title()
            countries = get_available_countries()
            for c in countries:
                if c['country_id'] == country_id:
                    country_name = c['name']
                    break
            
            # Get region name
            region_name = region_id.title()
            if region_id == "master":
                region_name = "Todas las Regiones"
            else:
                regions = get_regions_by_country(country_id)
                for r in regions:
                    if r['region_id'] == region_id:
                        region_name = r['name']
                        break
            
            recent_configs.append({
                'path': path,
                'name': metadata.get('name', os.path.basename(path)),
                'country': country_name,
                'country_id': country_id,
                'region': region_name,
                'region_id': region_id
            })
        except Exception as e:
            print(f"[get_recent_configs] Error loading {path}: {e}")
            continue
    
    return recent_configs

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
        # Skip excluded videos
        if entry.get("ui", {}).get("is_excluded", False):
            continue
        
        session_id = entry.get("session", {}).get("session_id", "")
        site = entry.get("metadata", {}).get("site", "")
        operator = entry.get("metadata", {}).get("operator", "")
        tags = entry.get("classification", {}).get("species", [])

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
                "date": entry.get("metadata", {}).get("recorded_at", "")
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
                    entry.setdefault("session", {}).setdefault("session_id", session_id)
                    entry.setdefault("classification", {})
                    entry.setdefault("metadata", {})
                    entry.setdefault("ui", {})
                all_videos.extend(session_metadata)
        except Exception as e:
            print(f"[rebuild_consolidated_metadata] Error leyendo {metadata_path}: {e}")
            continue

    # ✅ FIX: Deduplicar por file.video_path (modelo nuevo) con fallback a video_path (legacy)
    seen = {}
    unique_videos = []
    for video in reversed(all_videos):
        # Prioridad: modelo nuevo (file.video_path)
        path = video.get("file", {}).get("video_path")
        # Fallback: modelo legacy (video_path en raíz)
        if not path:
            path = video.get("video_path")
        if path and path not in seen:
            seen[path] = True
            unique_videos.append(video)

    unique_videos.reverse()

    with metadata_lock:
        with open(consolidated_path, "w", encoding="utf-8") as f:
            json.dump(unique_videos, f, indent=4, ensure_ascii=False)

    print(f"[rebuild_consolidated_metadata] Archivo consolidado reconstruido: {consolidated_path} ({len(unique_videos)} videos únicos)")
    return unique_videos

# =============================================================================
# RESOLUCIÓN CENTRALIZADA DE TAXONIDs (Multi-sistema: GBIF + iNaturalist/INABIO)
# =============================================================================
# Single Source of Truth:
#   - config/paises/species_master_{country_id}.json  (especies del país, con ambos IDs)
#   - config/taxon_master_global.json                 (niveles superiores, Homo sapiens, operacionales)
# =============================================================================

def get_global_master_path():
    """Retorna la ruta al taxon_master_global.json."""
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "config", "taxon_master_global.json")


def load_global_master():
    """
    Carga el taxon_master_global.
    Retorna dict con higher_taxa, humans, operational_tags o {} si no existe.
    """
    path = get_global_master_path()
    if not os.path.exists(path):
        print(f"⚠️ No existe taxon_master_global: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error cargando taxon_master_global: {e}")
        return {}


def _search_in_country_master(query, country_id):
    """
    Busca en species_master del país por scientificName o commonName.
    Retorna dict con taxonID_GBIF y taxonID_iNaturalist, o {} si no encuentra.
    Usa load_country_species() existente para evitar duplicación.
    """
    species_list = load_country_species(country_id)
    query_lower = query.lower().strip()

    for sp in species_list:
        sci = sp.get("scientificName", "").lower().strip()
        common = sp.get("commonName", sp.get("vernacularName", "")).lower().strip()

        if sci == query_lower or common == query_lower:
            return {
                "category": sp.get("category", "species"),
                "rank": sp.get("rank", "species"),
                "taxonID_GBIF": sp.get("taxonID_GBIF", sp.get("taxonID", "")),
                "taxonID_iNaturalist": sp.get("taxonID_iNaturalist", ""),
                "scientificName": sp.get("scientificName", ""),
                "commonName": sp.get("commonName", sp.get("vernacularName", "")),
                "family": sp.get("family", ""),
                "order": sp.get("order", ""),
                "class": sp.get("class", ""),
                "observationType": "animal"
            }
    return {}


def _search_in_global_master(query):
    """
    Busca en taxon_master_global por scientificName, commonName o tag operativo.
    Retorna solo taxonID_GBIF para niveles superiores (no hay iNaturalist para clases/órdenes).
    """
    global_data = load_global_master()
    if not global_data:
        return {}

    query_lower = query.lower().strip()

    # 1. Buscar en higher_taxa (clases, órdenes, familias)
    for taxon in global_data.get("higher_taxa", []):
        sci = taxon.get("scientificName", "").lower().strip()
        common = taxon.get("commonName", "").lower().strip()
        if sci == query_lower or common == query_lower:
            return {
                "category": "higher_taxon",
                "rank": taxon.get("rank", ""),
                "taxonID_GBIF": taxon.get("taxonID", ""),
                "taxonID_iNaturalist": "",
                "scientificName": taxon.get("scientificName", ""),
                "commonName": taxon.get("commonName", ""),
                "observationType": "animal"
            }

    # 2. Buscar en humans (Homo sapiens)
    for human in global_data.get("humans", []):
        sci = human.get("scientificName", "").lower().strip()
        common = human.get("commonName", "").lower().strip()
        if sci == query_lower or common == query_lower:
            return {
                "category": "species",
                "rank": "species",
                "taxonID_GBIF": human.get("taxonID", ""),
                "taxonID_iNaturalist": "",
                "scientificName": human.get("scientificName", ""),
                "commonName": human.get("commonName", ""),
                "observationType": "human"
            }

    # 3. Buscar en operational_tags (No identificado, Disparo en falso, etc.)
    for op_tag in global_data.get("operational_tags", []):
        tag = op_tag.get("tag", "").lower().strip()
        if tag == query_lower:
            return {
                "category": op_tag.get("category", "operational"),
                "rank": "",
                "taxonID_GBIF": "",
                "taxonID_iNaturalist": "",
                "scientificName": "",
                "commonName": "",
                "observationType": op_tag.get("observationType", ""),
                "description": op_tag.get("description", "")
            }

    return {}


def resolve_taxon_id(tag_or_name, country_id):
    """
    Resuelve taxonIDs buscando primero en master del país, luego en global.
    Acepta scientificName (ej: "Lontra longicaudis"), commonName (ej: "Huillín")
    o tag operativo (ej: "No identificado").

    Args:
        tag_or_name: Nombre científico, commonName, o tag operativo
        country_id: ID del país (ej: "ecuador")

    Returns:
        dict con {category, rank, taxonID_GBIF, taxonID_iNaturalist, scientificName,
                  commonName, observationType, ...} o {} si no encuentra
    """
    if not tag_or_name:
        return {}

    # 1. Buscar en master del país (especies con múltiples IDs)
    country_result = _search_in_country_master(tag_or_name, country_id)
    if country_result:
        return country_result

    # 2. Buscar en master global (niveles superiores + operacionales + Homo sapiens)
    global_result = _search_in_global_master(tag_or_name)
    if global_result:
        return global_result

    return {}


def resolve_all_taxon_ids(taxon_map, country_id):
    """
    Resuelve todos los taxonIDs de un Taxon_Map dado de forma eficiente.
    Carga masters una sola vez y usa índices para búsqueda rápida.

    Args:
        taxon_map: Dict {tag: {"scientificName": "..."}} o similar
        country_id: ID del país

    Returns:
        Dict {tag: {category, rank, taxonID_GBIF, taxonID_iNaturalist, scientificName,
                    commonName, observationType, ...}}
    """
    resolved = {}

    # Cargar masters una sola vez
    country_species = load_country_species(country_id)
    global_data = load_global_master()

    # Índices para búsqueda O(1)
    country_index = {}
    for sp in country_species:
        sci = sp.get("scientificName", "").lower().strip()
        common = sp.get("commonName", sp.get("vernacularName", "")).lower().strip()
        if sci:
            country_index[sci] = sp
        if common:
            country_index[common] = sp

    global_index = {}
    for taxon in global_data.get("higher_taxa", []) + global_data.get("humans", []):
        sci = taxon.get("scientificName", "").lower().strip()
        common = taxon.get("commonName", "").lower().strip()
        if sci:
            global_index[sci] = taxon
        if common:
            global_index[common] = taxon

    op_index = {}
    for op_tag in global_data.get("operational_tags", []):
        tag = op_tag.get("tag", "").lower().strip()
        if tag:
            op_index[tag] = op_tag

    # Resolver cada entrada del taxon_map
    for tag, info in taxon_map.items():
        if not isinstance(info, dict):
            continue

        sci_name = info.get("scientificName", "").strip()
        common_name = info.get("commonName", "").strip()

        # Intentar resolver por scientificName
        if sci_name:
            sci_lower = sci_name.lower()
            if sci_lower in country_index:
                sp = country_index[sci_lower]
                resolved[tag] = {
                    "category": sp.get("category", "species"),
                    "rank": sp.get("rank", "species"),
                    "taxonID_GBIF": sp.get("taxonID_GBIF", sp.get("taxonID", "")),
                    "taxonID_iNaturalist": sp.get("taxonID_iNaturalist", ""),
                    "scientificName": sp.get("scientificName", ""),
                    "commonName": sp.get("commonName", sp.get("vernacularName", "")),
                    "family": sp.get("family", ""),
                    "order": sp.get("order", ""),
                    "class": sp.get("class", ""),
                    "observationType": "animal"
                }
                continue
            if sci_lower in global_index:
                taxon = global_index[sci_lower]
                resolved[tag] = {
                    "category": taxon.get("category", "higher_taxon"),
                    "rank": taxon.get("rank", ""),
                    "taxonID_GBIF": taxon.get("taxonID", ""),
                    "taxonID_iNaturalist": "",
                    "scientificName": taxon.get("scientificName", ""),
                    "commonName": taxon.get("commonName", ""),
                    "observationType": taxon.get("observationType", "animal")
                }
                continue

        # Intentar resolver por commonName
        if common_name:
            common_lower = common_name.lower()
            if common_lower in country_index:
                sp = country_index[common_lower]
                resolved[tag] = {
                    "category": sp.get("category", "species"),
                    "rank": sp.get("rank", "species"),
                    "taxonID_GBIF": sp.get("taxonID_GBIF", sp.get("taxonID", "")),
                    "taxonID_iNaturalist": sp.get("taxonID_iNaturalist", ""),
                    "scientificName": sp.get("scientificName", ""),
                    "commonName": sp.get("commonName", sp.get("vernacularName", "")),
                    "family": sp.get("family", ""),
                    "order": sp.get("order", ""),
                    "class": sp.get("class", ""),
                    "observationType": "animal"
                }
                continue
            if common_lower in global_index:
                taxon = global_index[common_lower]
                resolved[tag] = {
                    "category": taxon.get("category", "higher_taxon"),
                    "rank": taxon.get("rank", ""),
                    "taxonID_GBIF": taxon.get("taxonID", ""),
                    "taxonID_iNaturalist": "",
                    "scientificName": taxon.get("scientificName", ""),
                    "commonName": taxon.get("commonName", ""),
                    "observationType": taxon.get("observationType", "animal")
                }
                continue

        # Intentar resolver por tag (operacionales)
        tag_lower = tag.lower()
        if tag_lower in op_index:
            op = op_index[tag_lower]
            resolved[tag] = {
                "category": op.get("category", "operational"),
                "rank": "",
                "taxonID_GBIF": "",
                "taxonID_iNaturalist": "",
                "scientificName": "",
                "commonName": "",
                "observationType": op.get("observationType", ""),
                "description": op.get("description", "")
            }
            continue

        # Si no encuentra, mantener datos básicos
        resolved[tag] = {
            "category": "unknown",
            "rank": "",
            "taxonID_GBIF": info.get("taxonID_GBIF", info.get("taxonID", "")),
            "taxonID_iNaturalist": info.get("taxonID_iNaturalist", ""),
            "scientificName": sci_name,
            "commonName": common_name,
            "observationType": "animal"
        }

    return resolved


def resolve_human_activity(tag):
    """
    Resuelve humanActivity basado en el nombre del tag (Camtrap DP estándar).
    Permite diferenciar Setup (research) de Persona (unknown) sin guardar en JSON.

    Args:
        tag: Nombre del tag (ej: "Setup", "Persona", "Cazador")

    Returns:
        str con el valor de humanActivity o "unknown"
    """
    tag_lower = tag.lower().strip()

    # Actividad de investigación
    if tag_lower in ["setup", "configuración", "configuracion", "config cámara", "config camara"]:
        return "research"

    # Humanos espontáneos
    if tag_lower in ["persona", "personas", "humano", "humanos"]:
        return "unknown"

    # Otros tipos de actividad
    if "cazador" in tag_lower or "caza" in tag_lower:
        return "hunting"
    if "turista" in tag_lower or "turismo" in tag_lower:
        return "tourism"
    if "pesca" in tag_lower or "pescador" in tag_lower:
        return "fishing"
    if "agricultura" in tag_lower or "trabajador" in tag_lower:
        return "agriculture"

    return "unknown"


def add_species_to_master(country_id, species_data):
    """
    Agrega una especie al species_master del país si no existe.
    species_data debe incluir scientificName, taxonID_GBIF y opcionalmente taxonID_iNaturalist.

    NOTA: Esta función es diferente de add_species_to_master_and_region().
    - add_species_to_master() → solo agrega al master del país (formato multi-ID)
    - add_species_to_master_and_region() → agrega a master Y región (formato antiguo)

    Args:
        country_id: ID del país
        species_data: Dict con scientificName, taxonID_GBIF, taxonID_iNaturalist, commonName, etc.

    Returns:
        True si se agregó, False si ya existía
    """
    path = get_country_master_path(country_id)

    # Cargar datos existentes
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"metadata": {"country_id": country_id}, "species": []}
    else:
        data = {"metadata": {"country_id": country_id}, "species": []}

    species_list = data.get("species", [])

    # Verificar si ya existe (por scientificName o taxonID_GBIF)
    sci = species_data.get("scientificName", "").lower().strip()
    tid_gbif = species_data.get("taxonID_GBIF", "").strip()

    for sp in species_list:
        if sp.get("scientificName", "").lower().strip() == sci:
            return False
        if tid_gbif and sp.get("taxonID_GBIF", sp.get("taxonID", "")).strip() == tid_gbif:
            return False

    # Agregar nueva especie
    species_list.append(species_data)
    data["species"] = species_list

    # Actualizar metadata
    data.setdefault("metadata", {})["total_species"] = len(species_list)
    data["metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")

    # Guardar
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error guardando species_master: {e}")
        return False
