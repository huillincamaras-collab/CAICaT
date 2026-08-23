"""
export_utils.py - Exportación CSV/Excel + Filtros de videos
Consolida la lógica de export_utils + filter_utils.
"""
import os
import json
import csv
from config_utils import load_config


# =============================================================================
# HELPERS
# =============================================================================
def _safe_get(d, *keys, default=""):
    """Acceso seguro a dicts anidados."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d if d is not None else default


def _join_list(val):
    """Convierte lista a string separado por comas."""
    if isinstance(val, list):
        return ", ".join(map(str, val))
    return val


# =============================================================================
# FLATTEN DEL MODELO NUEVO
# =============================================================================
def flatten_metadata(entry):
    """
    Convierte el modelo unificado en un dict plano (1 fila).
    Usa los nombres de campos del modelo nuevo (sin alias legacy).
    """
    return {
        # IDs
        "media_id": entry.get("media_id", ""),
        "event_id": entry.get("event_id", ""),
        "deployment_id": entry.get("deployment_id", ""),

        # Archivo
        "video_path": _safe_get(entry, "file", "video_path"),
        "frames_folder": _safe_get(entry, "file", "frames_folder"),
        "promedio": _safe_get(entry, "file", "promedio"),
        "mask": _safe_get(entry, "file", "mask"),

        # Procesamiento
        "status": _safe_get(entry, "processing", "status"),
        "frames": _safe_get(entry, "processing", "frames"),
        "time_sec": _safe_get(entry, "processing", "time_sec"),

        # Clasificación
        "species": _join_list(_safe_get(entry, "classification", "species", default=[])),
        "counts": json.dumps(_safe_get(entry, "classification", "counts", default={})),
        "behaviors": _join_list(_safe_get(entry, "classification", "behaviors", default=[])),
        "optional_tags": _join_list(_safe_get(entry, "classification", "optional_tags", default=[])),
        # Metadata ecológica

        # Metadata ecológica
        "site": _safe_get(entry, "metadata", "site"),
        "subsite": _safe_get(entry, "metadata", "subsite"),
        "camera": _safe_get(entry, "metadata", "camera"),
        "operator": _safe_get(entry, "metadata", "operator"),
        "recorded_at": _safe_get(entry, "metadata", "recorded_at"),
        "notes": _safe_get(entry, "metadata", "notes"),

        # UI
        "is_favorite": _safe_get(entry, "ui", "is_favorite"),
        "is_excluded": _safe_get(entry, "ui", "is_excluded"),

        # Session
        "session_id": _safe_get(entry, "session", "session_id"),
        "camtrap_db_session": _safe_get(entry, "session", "camtrap_db_session"),
    }


# =============================================================================
# FILTROS DE VIDEOS (antes en filter_utils.py)
# =============================================================================
def filter_videos(
    metadata_list,
    session_filter="all",
    tags=None,
    operators=None,
    cameras=None,
    sites=None,
    behaviors=None
):
    """
    Filtra una lista de metadata según los criterios dados.
    """
    if not metadata_list:
        return []
    filtered = metadata_list[:]

    # 1. Filtrar por sesión
    if session_filter == "last":
        valid = [v for v in filtered if v.get("session", {}).get("session_id")]
        if not valid:
            return []
        last_id = max(v["session"]["session_id"] for v in valid)
        filtered = [v for v in filtered if v.get("session", {}).get("session_id") == last_id]
    elif session_filter.startswith("specific:"):
        specific_id = session_filter.split(":", 1)[1].strip()
        if specific_id:
            filtered = [v for v in filtered if v.get("session", {}).get("session_id") == specific_id]

    # 2. Filtrar por tags (especies)
    if tags:
        filtered = [
            v for v in filtered
            if any(tag in v.get("classification", {}).get("species", []) for tag in tags)
        ]

    # 3. Filtrar por operadores
    if operators:
        filtered = [
            v for v in filtered
            if v.get("metadata", {}).get("operator") in operators
        ]

    # 4. Filtrar por cámaras
    if cameras:
        filtered = [
            v for v in filtered
            if v.get("metadata", {}).get("camera") in cameras
        ]

    # 5. Filtrar por sitios
    if sites:
        filtered = [
            v for v in filtered
            if v.get("metadata", {}).get("site") in sites
        ]

    # 6. Filtrar por comportamientos
    if behaviors:
        filtered = [
            v for v in filtered
            if any(b in v.get("classification", {}).get("behaviors", []) for b in behaviors)
        ]

    return filtered


def get_unique_values(metadata_list, key):
    """Extrae valores únicos de metadata.<key>."""
    values = {str(v.get("metadata", {}).get(key, "")).strip() for v in metadata_list}
    return sorted([v for v in values if v])


def get_unique_tags(metadata_list):
    """Extrae tags únicos (especies) de la clasificación."""
    tags = set()
    for v in metadata_list:
        tags.update(v.get("classification", {}).get("species", []))
    return sorted(tags)


def get_unique_behaviors(metadata_list):
    """Extrae comportamientos únicos de la clasificación."""
    behaviors = set()
    for v in metadata_list:
        behaviors.update(v.get("classification", {}).get("behaviors", []))
    return sorted(behaviors)


# =============================================================================
# EXPORT CSV
# =============================================================================
def export_to_csv(metadata_path=None, output_path=None):
    """Exporta metadata a CSV usando el modelo nuevo."""
    config = load_config()

    if metadata_path is None:
        metadata_path = os.path.join(
            config["General"]["output_folder"],
            "consolidated",
            "all_sessions_metadata.json"
        )

    if not os.path.exists(metadata_path):
        print("❌ No existe metadata para exportar")
        return None

    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = [flatten_metadata(entry) for entry in data]
    rows = [r for r in rows if not r.get("is_excluded", False)]

    if not rows:
        print("⚠️ No hay datos")
        return None

    if output_path is None:
        output_path = os.path.join(
            config["General"]["output_folder"],
            "export.csv"
        )

    fieldnames = list(rows[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ CSV exportado en: {output_path}")
    return output_path


# =============================================================================
# EXPORT EXCEL (simple)
# =============================================================================
def export_to_excel(metadata_path=None, output_path=None):
    """Exporta metadata a Excel usando el modelo nuevo."""
    try:
        import pandas as pd
    except ImportError:
        print("❌ pandas no instalado")
        return None

    config = load_config()

    if metadata_path is None:
        metadata_path = os.path.join(
            config["General"]["output_folder"],
            "consolidated",
            "all_sessions_metadata.json"
        )

    if not os.path.exists(metadata_path):
        print("❌ No existe metadata")
        return None

    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = [flatten_metadata(entry) for entry in data]
    rows = [r for r in rows if not r.get("is_excluded", False)]

    if not rows:
        print("⚠️ No hay datos")
        return None

    df = pd.DataFrame(rows)

    if output_path is None:
        output_path = os.path.join(
            config["General"]["output_folder"],
            "export.xlsx"
        )

    df.to_excel(output_path, index=False)

    print(f"✅ Excel exportado en: {output_path}")
    return output_path