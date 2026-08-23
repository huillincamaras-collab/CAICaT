"""
export_camtrap.py - Exportación a Camtrap DP 1.0 estándar
Usa el sistema centralizado de taxonIDs (GBIF + iNaturalist/INABIO)
Genera 6 CSVs + datapackage.json
"""
import os
import csv
import json
import re
from datetime import datetime
from config_utils import (
    load_config,
    resolve_taxon_id,
    resolve_human_activity
)


# =============================================================================
# HELPERS
# =============================================================================
def _get_country_id(config, data):
    """
    Obtiene el country_id de la config activa o de los datos.
    Prioridad:
    1. config["GUI_Tagger"]["country_id"] (si existe)
    2. Primer entry con _metadata.country_id
    3. Default: "ecuador"
    """
    # Intentar desde config
    country_id = config.get("GUI_Tagger", {}).get("country_id", "")
    if country_id:
        return country_id
    
    # Intentar desde datos
    if data:
        for entry in data:
            meta = entry.get("_metadata", {})
            if meta.get("country_id"):
                return meta["country_id"]
    
    # Default
    return "ecuador"


def _resolve_taxon_for_export(tag, country_id):
    """
    Resuelve información taxonómica completa para exportación.
    Usa resolve_taxon_id() de config_utils que busca en:
    - species_master_{country_id}.json (especies con GBIF + iNaturalist)
    - taxon_master_global.json (niveles superiores, operacionales, Homo sapiens)
    
    Returns:
        dict con {category, rank, taxonID_GBIF, taxonID_iNaturalist, 
                  scientificName, commonName, observationType, ...}
    """
    resolved = resolve_taxon_id(tag, country_id)
    
    # Si no encuentra, retornar datos básicos
    if not resolved:
        return {
            "category": "unknown",
            "rank": "species",
            "taxonID_GBIF": "",
            "taxonID_iNaturalist": "",
            "scientificName": tag,
            "commonName": "",
            "observationType": "animal"
        }
    
    return resolved


def _read_existing_csv(path):
    """Lee un CSV existente y retorna (fieldnames, list of dicts)."""
    if not os.path.exists(path):
        return None, []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = [dict(row) for row in reader]
        return fieldnames, rows
    except Exception as e:
        print(f"[export_camtrap] Error leyendo {path}: {e}")
        return None, []


def _write_csv(path, fieldnames, rows):
    """Escribe un CSV con los fieldnames y rows dados."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[export_camtrap] {os.path.basename(path)}: {len(rows)} filas → {path}")


def _append_deduplicated(existing_rows, new_rows, key_field):
    """
    Anexa new_rows a existing_rows, deduplicando por key_field.
    Las nuevas filas con key ya existente son ignoradas.
    Retorna la lista combinada.
    """
    existing_keys = {row.get(key_field) for row in existing_rows}
    added = 0
    for row in new_rows:
        if row.get(key_field) not in existing_keys:
            existing_rows.append(row)
            existing_keys.add(row.get(key_field))
            added += 1
    print(f"[export_camtrap] {key_field}: {added} filas nuevas anexadas, {len(new_rows) - added} duplicados ignorados.")
    return existing_rows


def _ensure_iso8601(timestamp_str):
    """
    Asegura que el timestamp sea ISO 8601 compliant.
    Convierte varios formatos a YYYY-MM-DDTHH:MM:SS[Z|±HH:MM]
    """
    if not timestamp_str or not isinstance(timestamp_str, str):
        return ""
    
    # Already ISO 8601 with timezone
    if re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[Z\+\-]', timestamp_str):
        return timestamp_str
    
    # Space separator instead of T: "2024-03-15 14:30:00"
    if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', timestamp_str):
        return timestamp_str.replace(' ', 'T') + 'Z'
    
    # Other formats: try to parse and convert
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return timestamp_str


def _generate_datapackage(output_dir):
    """
    Genera datapackage.json para validación Frictionless Data.
    Incluye projects.csv para jerarquía nacional de proyectos.
    """
    datapackage = {
        "profile": "tabular-data-package",
        "name": "caicat-camtrap-dp-export",
        "title": "CAICAT Camera Trap Data Package",
        "description": "Camera trap data exported from CAICAT in Camtrap DP 1.0 format",
        "version": "2.1.0",
        "created": datetime.now().isoformat(),
        "contributors": [
            {
                "title": "CAICAT Project",
                "role": "author"
            }
        ],
        "licenses": [
            {
                "name": "CC-BY-4.0",
                "title": "Creative Commons Attribution 4.0",
                "path": "https://creativecommons.org/licenses/by/4.0/"
            }
        ],
        "resources": [
            {"name": "projects", "path": "projects.csv", "profile": "tabular-data-resource"},
            {"name": "deployments", "path": "deployments.csv", "profile": "tabular-data-resource"},
            {"name": "locations", "path": "locations.csv", "profile": "tabular-data-resource"},
            {"name": "taxa", "path": "taxa.csv", "profile": "tabular-data-resource"},
            {"name": "media", "path": "media.csv", "profile": "tabular-data-resource"},
            {"name": "observations", "path": "observations.csv", "profile": "tabular-data-resource"}
        ],
        "foreignKeys": [
            {
                "fields": ["projectID"],
                "reference": {"resource": "projects", "fields": ["projectID"]},
                "description": "Link deployment to parent project"
            },
            {
                "fields": ["locationID"],
                "reference": {"resource": "locations", "fields": ["locationID"]},
                "description": "Link deployment to location"
            },
            {
                "fields": ["deploymentID"],
                "reference": {"resource": "deployments", "fields": ["deploymentID"]},
                "description": "Link media/observations to deployment"
            },
            {
                "fields": ["taxonID"],
                "reference": {"resource": "taxa", "fields": ["taxonID"]},
                "description": "Link observation to taxon"
            }
        ]
    }
    
    datapackage_path = os.path.join(output_dir, "datapackage.json")
    with open(datapackage_path, "w", encoding="utf-8") as f:
        json.dump(datapackage, f, indent=2, ensure_ascii=False)
    print(f"[export_camtrap] datapackage.json created: {datapackage_path}")
    return datapackage_path


# =============================================================================
# EXPORT PRINCIPAL
# =============================================================================
def export_camtrap(metadata_path, output_dir=None, deployments_csv_provided=False, config=None):
    """
    Exporta metadata CAICAT a formato Camtrap DP 1.0 COMPLIANT.
    Usa el sistema centralizado de taxonIDs (GBIF + iNaturalist/INABIO).
    Genera o anexa: projects.csv, deployments.csv, locations.csv, taxa.csv, 
                    media.csv, observations.csv, datapackage.json
    """
    if config is None:
        config = load_config()
    
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"No existe: {metadata_path}")
    
    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not data:
        print("[export_camtrap] Sin datos para exportar.")
        return None
    
    # Determinar output_dir desde el primer entry si no se pasó explícitamente
    if output_dir is None:
        session = data[0].get("session", {})
        output_dir = session.get("camtrap_output_dir") or os.path.join(
            config["General"]["output_folder"], "camtrap_dp"
        )
        deployments_csv_provided = session.get("deployments_csv_provided", False)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 🆕 Obtener country_id para resolver taxonIDs
    country_id = _get_country_id(config, data)
    print(f"[export_camtrap] Country ID: {country_id}")
    
    # 🔒 Paths de los SEIS archivos Camtrap DP
    projects_path = os.path.join(output_dir, "projects.csv")
    deployments_path = os.path.join(output_dir, "deployments.csv")
    locations_path = os.path.join(output_dir, "locations.csv")
    taxa_path = os.path.join(output_dir, "taxa.csv")
    media_path = os.path.join(output_dir, "media.csv")
    observations_path = os.path.join(output_dir, "observations.csv")
    
    # Leer existentes para anexar sin borrar datos previos
    proj_fieldnames, existing_projects = _read_existing_csv(projects_path)
    dep_fieldnames, existing_deployments = _read_existing_csv(deployments_path)
    loc_fieldnames, existing_locations = _read_existing_csv(locations_path)
    taxa_fieldnames, existing_taxa = _read_existing_csv(taxa_path)
    media_fieldnames, existing_media = _read_existing_csv(media_path)
    obs_fieldnames, existing_observations = _read_existing_csv(observations_path)
    
    new_projects = {}
    new_deployments = {}
    new_locations = {}
    new_taxa = {}
    new_media = []
    new_observations = []
    
    for entry in data:
        if entry.get("ui", {}).get("is_excluded", False):
            continue
        
        video_hash = entry.get("video_hash", "")
        file_info = entry.get("file", {})
        video_path = file_info.get("video_path", "") or entry.get("video_path", "")
        media_id = video_hash or video_path
        event_id = media_id
        
        meta = entry.get("metadata", {})
        site = meta.get("site", "")
        subsite = meta.get("subsite", "")
        camera = meta.get("camera", "")
        operator = meta.get("operator", "")
        recorded_at = meta.get("recorded_at", "")
        
        session = entry.get("session", {})
        session_id = session.get("session_id", "")
        deployment_id = session.get("deployment_id", "") or "_".join(filter(None, [site, subsite, camera])) or session_id
        deployment_start = session.get("deployment_start", "")
        deployment_end = session.get("deployment_end", "")
        
        # Project support para jerarquía nacional
        project_id = session.get("project_id", "") or config.get("General", {}).get("default_project_id", "CAICAT_Ecuador")
        project_name = session.get("project_name", "") or config.get("General", {}).get("default_project_name", "CAICAT Ecuador National Parks")
        
        # Ensure ISO 8601 timestamps
        recorded_at_iso = _ensure_iso8601(recorded_at)
        deployment_start_iso = _ensure_iso8601(deployment_start)
        deployment_end_iso = _ensure_iso8601(deployment_end)
        
        # --- PROJECTS ---
        if project_id and project_id not in new_projects:
            new_projects[project_id] = {
                "projectID": project_id,
                "name": project_name,
                "description": session.get("project_description", ""),
                "license": session.get("project_license", "CC-BY-4.0"),
                "contactName": session.get("project_contact_name", ""),
                "contactEmail": session.get("project_contact_email", "")
            }
        
        # --- LOCATIONS ---
        location_id = site
        if location_id and location_id not in new_locations:
            # Coordenadas de deployment (modo científico) o vacías (modo base)
            deployment = entry.get("deployment", {})
            latitude = deployment.get("latitude", "")
            longitude = deployment.get("longitude", "")
            
            new_locations[location_id] = {
                "locationID": location_id,
                "locationName": "_".join(filter(None, [site, subsite])) or site,
                "latitude": latitude,
                "longitude": longitude,
                "coordinateUncertainty": "",
                "habitat": ""
            }
        
        # --- DEPLOYMENTS ---
        if not deployments_csv_provided and deployment_id not in new_deployments:
            deployment = entry.get("deployment", {})
            
            new_deployments[deployment_id] = {
                "deploymentID": deployment_id,
                "projectID": project_id,
                "locationID": location_id,
                "cameraID": camera,
                "deploymentStart": deployment_start_iso,
                "deploymentEnd": deployment_end_iso,
                # Campos opcionales de deployment (vacíos en modo base)
                "setupBy": deployment.get("setupBy", ""),
                "retrievedBy": deployment.get("retrievedBy", ""),
                "cameraHeight": deployment.get("cameraHeight", ""),
                "cameraTilt": deployment.get("cameraTilt", ""),
                "detectionDistance": deployment.get("detectionDistance", ""),
                "timestampIssues": str(deployment.get("timestampIssues", False)).lower(),
                "baitUse": str(deployment.get("baitUse", False)).lower()
            }
        
        # --- MEDIA ---
        is_photo = entry.get("is_photo", False)
        capture_method = "activityDetection"
        if is_photo and entry.get("is_burst", False):
            capture_method = "timeLapse"
        
        new_media.append({
            "mediaID": media_id,
            "deploymentID": deployment_id,
            "captureMethod": capture_method,
            "timestamp": recorded_at_iso,
            "filePath": video_path,
            "filePublic": "true",
            "fileName": os.path.basename(video_path),
            "fileMediatype": "image/jpeg" if is_photo else "video/mp4",
            "sequenceID": entry.get("sequence_id", "")
        })
        
        # --- OBSERVATIONS (🆕 CON RESOLUCIÓN DE TAXONIDs) ---
        classif = entry.get("classification", {})
        species_list = classif.get("species", [])
        counts = classif.get("counts", {})
        behaviors = classif.get("behaviors", [])
        
        if not species_list:
            # Blank observation (no detection)
            new_observations.append({
                "observationID": f"{event_id}_blank",
                "deploymentID": deployment_id,
                "mediaID": media_id,
                "observationType": "blank",
                "scientificName": "",
                "vernacularName": "",
                "count": "",
                "lifeStage": "",
                "sex": "",
                "age": "",
                "individualID": "",
                "classificationMethod": "human",
                "classifiedBy": operator,
                "taxonID": "",
                "taxonRank": "",
                "humanActivity": "",
                "observationComments": ", ".join(behaviors) if behaviors else ""
            })
        else:
            for sp in species_list:
                # 🆕 Resolver taxón usando sistema centralizado
                resolved = _resolve_taxon_for_export(sp, country_id)
                
                observation_type = resolved.get("observationType", "animal")
                taxon_id = resolved.get("taxonID_GBIF", "")
                taxon_rank = resolved.get("rank", "species")
                scientific_name = resolved.get("scientificName", sp)
                vernacular_name = resolved.get("commonName", "")
                
                # 🆕 Si es humano, agregar humanActivity
                human_activity = ""
                if observation_type == "human":
                    human_activity = resolve_human_activity(sp)
                
                # Add to taxa table if not already present
                if taxon_id and taxon_id not in new_taxa:
                    new_taxa[taxon_id] = {
                        "taxonID": taxon_id,
                        "scientificName": scientific_name,
                        "vernacularName": vernacular_name,
                        "taxonRank": taxon_rank,
                        "kingdom": resolved.get("kingdom", "Animalia"),
                        "phylum": resolved.get("phylum", ""),
                        "class": resolved.get("class", ""),
                        "order": resolved.get("order", ""),
                        "family": resolved.get("family", ""),
                        "genus": resolved.get("genus", "")
                    }
                
                # Compliant observation entry
                new_observations.append({
                    "observationID": f"{event_id}_{sp}",
                    "deploymentID": deployment_id,
                    "mediaID": media_id,
                    "observationType": observation_type,
                    "scientificName": scientific_name,
                    "vernacularName": vernacular_name,
                    "count": counts.get(sp, 1),
                    "lifeStage": "",
                    "sex": "",
                    "age": "",
                    "individualID": "",
                    "classificationMethod": "human",
                    "classifiedBy": operator,
                    "taxonID": taxon_id,
                    "taxonRank": taxon_rank,
                    "humanActivity": human_activity,
                    "observationComments": ", ".join(behaviors) if behaviors else ""
                })
    
    # --- Escribir projects ---
    if new_projects:
        new_proj_list = list(new_projects.values())
        fieldnames = proj_fieldnames or list(new_proj_list[0].keys())
        combined = _append_deduplicated(existing_projects, new_proj_list, "projectID")
        _write_csv(projects_path, fieldnames, combined)
    
    # --- Escribir deployments ---
    if not deployments_csv_provided and new_deployments:
        new_dep_list = list(new_deployments.values())
        fieldnames = dep_fieldnames or list(new_dep_list[0].keys())
        combined = _append_deduplicated(existing_deployments, new_dep_list, "deploymentID")
        _write_csv(deployments_path, fieldnames, combined)
    
    # --- Escribir locations ---
    if new_locations:
        new_loc_list = list(new_locations.values())
        fieldnames = loc_fieldnames or list(new_loc_list[0].keys())
        combined = _append_deduplicated(existing_locations, new_loc_list, "locationID")
        _write_csv(locations_path, fieldnames, combined)
    
    # --- Escribir taxa ---
    if new_taxa:
        new_taxa_list = list(new_taxa.values())
        fieldnames = taxa_fieldnames or list(new_taxa_list[0].keys())
        combined = _append_deduplicated(existing_taxa, new_taxa_list, "taxonID")
        _write_csv(taxa_path, fieldnames, combined)
    
    # --- Escribir media ---
    if new_media:
        fieldnames = media_fieldnames or list(new_media[0].keys())
        combined = _append_deduplicated(existing_media, new_media, "mediaID")
        _write_csv(media_path, fieldnames, combined)
    
    # --- Escribir observations ---
    if new_observations:
        fieldnames = obs_fieldnames or list(new_observations[0].keys())
        combined = _append_deduplicated(existing_observations, new_observations, "observationID")
        _write_csv(observations_path, fieldnames, combined)
    
    # --- Generar datapackage.json ---
    _generate_datapackage(output_dir)
    
    print(f"[export_camtrap] Exportación Camtrap DP completa en: {output_dir}")
    print(f"[export_camtrap] ✅ COMPLIANT with Camtrap DP 1.0 standard")
    print(f"[export_camtrap] ✅ Uses centralized taxonID system (GBIF + iNaturalist)")
    print(f"[export_camtrap] ✅ Includes humanActivity for human observations")
    return output_dir