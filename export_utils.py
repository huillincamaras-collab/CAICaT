import os
import json
import csv
from config_utils import load_config

# ---------------------------
# Helpers
# ---------------------------
def _safe_get(d, *keys, default=""):
    """Acceso seguro a dicts anidados"""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d if d is not None else default


def _join_list(val):
    if isinstance(val, list):
        return ", ".join(map(str, val))
    return val


# ---------------------------
# Flatten del modelo nuevo
# ---------------------------
def flatten_metadata(entry):
    """
    Convierte el modelo unificado en un dict plano (1 fila).
    """

    flat = {
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

    return flat


# ---------------------------
# Export CSV
# ---------------------------
def export_to_csv(metadata_path=None, output_path=None):
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


# ---------------------------
# Export Excel (simple)
# ---------------------------
def export_to_excel(metadata_path=None, output_path=None):
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