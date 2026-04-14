import os
import csv
import json
from datetime import datetime
from config_utils import load_config

def _load_sites_coords(config=None):
    """Carga coordenadas desde config/sites_list.csv."""
    if config is None:
        config = load_config()
    sites_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "sites_list.csv")
    coords = {}
    if not os.path.exists(sites_csv):
        return coords
    try:
        with open(sites_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                site_id = row.get("siteID", "").strip()
                if site_id:
                    coords[site_id] = {
                        "decimalLatitude": row.get("decimalLatitude", ""),
                        "decimalLongitude": row.get("decimalLongitude", "")
                    }
    except Exception as e:
        print(f"[export_camtrap] No se pudo leer sites_list.csv: {e}")
    return coords

def _load_species_taxon(config=None):
    """Carga taxonID desde config/species_list.csv."""
    if config is None:
        config = load_config()
    species_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "species_list.csv")
    taxon = {}
    if not os.path.exists(species_csv):
        return taxon
    try:
        with open(species_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vname = row.get("vernacularName", "").strip()
                sname = row.get("scientificName", "").strip()
                tid = row.get("taxonID", "").strip()
                if vname:
                    taxon[vname] = {"scientificName": sname, "taxonID": tid}
                if sname:
                    taxon[sname] = {"scientificName": sname, "taxonID": tid}
    except Exception as e:
        print(f"[export_camtrap] No se pudo leer species_list.csv: {e}")
    return taxon

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

def export_camtrap(metadata_path, output_dir=None, deployments_csv_provided=False, config=None):
    """
    Exporta metadata CAICAT a formato Camtrap DP.
    Genera o anexa: deployments.csv, media.csv, observations.csv
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
        # Por defecto, si no se pasa flag, asumimos que NO es provisto externamente
        # a menos que la sesión diga lo contrario.
        deployments_csv_provided = session.get("deployments_csv_provided", False)

    os.makedirs(output_dir, exist_ok=True)

    # 1. Cargar datos base (Coordenadas y Taxones)
    sites_coords = _load_sites_coords(config)
    species_taxon = _load_species_taxon(config)
    
    # 🔹 NUEVO: Superponer taxon_map de config.ini sobre el CSV.
    # Esto permite que etiquetas de botones personalizados (ej: "Puma") 
    # se resuelvan a nombres científicos/IDs definidos en la config del tagger.
    config_taxon_map = config.get("GUI_Tagger", {}).get("taxon_map", {})
    for tag, info in config_taxon_map.items():
        if info:
            species_taxon[tag] = info

    # Paths de los tres archivos maestros
    deployments_path = os.path.join(output_dir, "deployments.csv")
    media_path = os.path.join(output_dir, "media.csv")
    observations_path = os.path.join(output_dir, "observations.csv")

    # Leer existentes para anexar sin borrar datos previos
    dep_fieldnames, existing_deployments = _read_existing_csv(deployments_path)
    media_fieldnames, existing_media = _read_existing_csv(media_path)
    obs_fieldnames, existing_observations = _read_existing_csv(observations_path)

    new_deployments = {}
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

        # --- DEPLOYMENTS ---
        if not deployments_csv_provided and deployment_id not in new_deployments:
            coord = sites_coords.get(site, {})
            new_deployments[deployment_id] = {
                "deploymentID": deployment_id,
                "locationID": site,
                "locationName": "_".join(filter(None, [site, subsite])),
                "cameraID": camera,
                "operator": operator,
                "decimalLatitude": coord.get("decimalLatitude", ""),
                "decimalLongitude": coord.get("decimalLongitude", ""),
                "deploymentStart": deployment_start,
                "deploymentEnd": deployment_end
            }

        # --- MEDIA ---
        is_photo = entry.get("is_photo", False)
        new_media.append({
            "mediaID": media_id,
            "deploymentID": deployment_id,
            "captureMethod": "photographicTag" if is_photo else "video",
            "timestamp": recorded_at,
            "filePath": video_path,
            "filePublic": "true",
            "fileName": os.path.basename(video_path),
            "fileMediatype": "image/jpeg" if is_photo else "video/mp4",
            "sessionID": session_id
        })

        # --- OBSERVATIONS ---
        classif = entry.get("classification", {})
        species_list = classif.get("species", [])
        counts = classif.get("counts", {})
        behaviors = classif.get("behaviors", [])

        if not species_list:
            new_observations.append({
                "observationID": f"{event_id}_blank",
                "deploymentID": deployment_id,
                "mediaID": media_id,
                "eventID": event_id,
                "eventStart": recorded_at,
                "eventEnd": recorded_at,
                "observationType": "blank",
                "scientificName": "",
                "vernacularName": "",
                "count": "",
                "lifeStage": "",
                "behavior": ", ".join(behaviors),
                "individualID": "",
                "classificationMethod": "human",
                "classifiedBy": operator,
                "taxonID": ""
            })
        else:
            for sp in species_list:
                # 🔹 Resolver etiqueta (ej: "Puma") a datos completos usando el mapa fusionado
                taxon_info = species_taxon.get(sp, {})
                
                # Usar datos resueltos o fallback al nombre del tag
                sci_name = taxon_info.get("scientificName", sp)
                vern_name = taxon_info.get("vernacularName", sp)
                taxon_id = taxon_info.get("taxonID", "")

                new_observations.append({
                    "observationID": f"{event_id}_{sp}",
                    "deploymentID": deployment_id,
                    "mediaID": media_id,
                    "eventID": event_id,
                    "eventStart": recorded_at,
                    "eventEnd": recorded_at,
                    "observationType": "animal",
                    "scientificName": sci_name,
                    "vernacularName": vern_name,
                    "count": counts.get(sp, 1),
                    "lifeStage": "",
                    "behavior": ", ".join(behaviors),
                    "individualID": "",
                    "classificationMethod": "human",
                    "classifiedBy": operator,
                    "taxonID": taxon_id
                })

    # --- Escribir deployments (solo si no es externo) ---
    if not deployments_csv_provided and new_deployments:
        new_dep_list = list(new_deployments.values())
        fieldnames = dep_fieldnames or list(new_dep_list[0].keys())
        combined = _append_deduplicated(existing_deployments, new_dep_list, "deploymentID")
        _write_csv(deployments_path, fieldnames, combined)

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

    print(f"[export_camtrap] Exportación Camtrap DP completa en: {output_dir}")
    return output_dir