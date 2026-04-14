# --- filter_utils.py: reescrito para modelo nuevo ---
def filter_videos(
    metadata_list,
    session_filter="all",
    tags=None,
    operators=None,
    cameras=None,
    sites=None,
    behaviors=None
):
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
    """Extrae valores únicos de metadata.key"""
    values = {str(v.get("metadata", {}).get(key, "")).strip() for v in metadata_list}
    return sorted([v for v in values if v])


def get_unique_tags(metadata_list):
    tags = set()
    for v in metadata_list:
        tags.update(v.get("classification", {}).get("species", []))
    return sorted(tags)


def get_unique_behaviors(metadata_list):
    behaviors = set()
    for v in metadata_list:
        behaviors.update(v.get("classification", {}).get("behaviors", []))
    return sorted(behaviors)