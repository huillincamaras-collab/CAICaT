# filter_utils.py
"""
Módulo centralizado de filtrado para el sistema de cámaras trampa.
Proporciona una interfaz unificada para filtrar videos según múltiples criterios.
Usado por: sort_rename.py, gui_excel_export.py, embed_metadata.py, AnalysisGUI, etc.
"""

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
    Filtra una lista de metadatos de videos según criterios especificados.
    
    Parámetros:
    - metadata_list (list): Lista de diccionarios con metadatos de videos.
    - session_filter (str): 
        - "all": sin filtrar por sesión.
        - "last": solo la sesión más reciente (usa orden cronológico de session_id).
        - "specific:ID": solo la sesión con ID exacto (ej: "specific:251025_143022_A1B2C3").
    - tags (list or None): Lista de tags de especie a incluir (OR lógico).
    - operators (list or None): Lista de operadores a incluir.
    - cameras (list or None): Lista de cámaras a incluir.
    - sites (list or None): Lista de sitios a incluir.
    - behaviors (list or None): Lista de comportamientos a incluir (OR lógico).
    
    Devuelve:
    - list: Nueva lista con las entradas que coinciden con todos los filtros.
    
    Notas:
    - Los filtros son acumulativos (AND entre categorías).
    - Dentro de "tags" y "behaviors", se aplica OR (basta con que coincida uno).
    - Si una lista de filtros está vacía o es None, se ignora esa categoría.
    """
    if not metadata_list:
        return []

    filtered = metadata_list[:]

    # --- 1. Filtrar por sesión ---
    if session_filter == "last":
        # Ordenar por session_id (asume formato YYMMDD_HHMMSS_MAC → orden cronológico)
        valid_sessions = [v for v in filtered if v.get("session_id")]
        if not valid_sessions:
            return []
        last_session_id = max(v["session_id"] for v in valid_sessions)
        filtered = [v for v in filtered if v.get("session_id") == last_session_id]
    
    elif session_filter.startswith("specific:"):
        specific_id = session_filter.split(":", 1)[1].strip()
        if specific_id:
            filtered = [v for v in filtered if v.get("session_id") == specific_id]

    # --- 2. Filtrar por tags (especies) ---
    if tags:
        filtered = [
            v for v in filtered 
            if v.get("tags") and any(tag in v["tags"] for tag in tags)
        ]

    # --- 3. Filtrar por operadores ---
    if operators:
        filtered = [
            v for v in filtered 
            if v.get("operator") in operators
        ]

    # --- 4. Filtrar por cámaras ---
    if cameras:
        filtered = [
            v for v in filtered 
            if v.get("camera") in cameras
        ]

    # --- 5. Filtrar por sitios ---
    if sites:
        filtered = [
            v for v in filtered 
            if v.get("site") in sites
        ]

    # --- 6. Filtrar por comportamientos ---
    if behaviors:
        filtered = [
            v for v in filtered 
            if v.get("behaviors") and any(b in v["behaviors"] for b in behaviors)
        ]

    return filtered


# ---------------------------
# Funciones auxiliares útiles
# ---------------------------

def get_unique_values(metadata_list, key):
    """
    Extrae valores únicos y no vacíos de un campo en la lista de metadatos.
    Útil para llenar checkboxes en GUIs.
    
    Ejemplo:
        operators = get_unique_values(metadata_list, "operator")
    """
    values = {str(v.get(key, "")).strip() for v in metadata_list if v.get(key)}
    return sorted([v for v in values if v])


def get_unique_tags(metadata_list):
    """Extrae todos los tags de especie únicos."""
    tags = set()
    for v in metadata_list:
        tags.update(v.get("tags", []))
    return sorted(tags)


def get_unique_behaviors(metadata_list):
    """Extrae todos los comportamientos únicos."""
    behaviors = set()
    for v in metadata_list:
        behaviors.update(v.get("behaviors", []))
    return sorted(behaviors)