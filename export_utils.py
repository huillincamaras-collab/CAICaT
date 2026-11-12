"""
export_utils.py - Exportación CSV/Excel + Filtros de videos
Consolida la lógica de export_utils + filter_utils.

Incluye además:
  - Corrección de fecha/hora de captura (cámaras desconfiguradas) y copias con fecha corregida.
  - Exportación automática al finalizar una sesión (CSV acumulado + embed + copias corregidas).
"""
import os
import json
import csv
import posixpath
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
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


# =============================================================================
# CORRECCIÓN DE FECHA Y HORA DE CAPTURA (cámaras desconfiguradas)
# =============================================================================

# Modelo de datos por entrada de metadata.json:
#  - recorded_at (nivel superior) y metadata.recorded_at: fecha/hora vigente (corregida).
#  - time_correction (solo si hay corrección): {original_recorded_at, delta_seconds, scope, applied_at}
#  - metadata["Corrección Horaria"]: texto legible del desfase.
#  - fecha_prefix y video_hash NO se tocan. El desfase se calcula siempre contra la fecha ORIGINAL.


ISO_FMT = "%Y-%m-%dT%H:%M:%S"
EXIF_FMT = "%Y:%m:%d %H:%M:%S"

ALCANCE_ARCHIVO = "archivo"
ALCANCE_DESDE_AQUI = "desde_aqui"
ALCANCE_CARPETA = "carpeta"

_WIN_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_JPEG_EXTS = {".jpg", ".jpeg"}


def _parse_iso(texto):
    if not texto or not isinstance(texto, str):
        return None
    t = texto.strip().replace("Z", "")
    for fmt in (ISO_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def _parse_prefix(prefijo):
    if not prefijo or not isinstance(prefijo, str):
        return None
    try:
        return datetime.strptime(prefijo.strip().replace(" ", "_"), "%y%m%d_%H%M%S")
    except ValueError:
        return None


def parse_fecha_hora(texto_fecha, texto_hora):
    """Convierte textos de fecha y hora ingresados por el usuario. Lanza ValueError si no son válidos."""
    f = (texto_fecha or "").strip()
    h = (texto_hora or "").strip()
    fecha = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            fecha = datetime.strptime(f, fmt).date()
            break
        except ValueError:
            continue
    if fecha is None:
        raise ValueError("Fecha no válida (use AAAA-MM-DD)")
    hora = None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            hora = datetime.strptime(h, fmt).time()
            break
        except ValueError:
            continue
    if hora is None:
        raise ValueError("Hora no válida (use HH:MM:SS)")
    return datetime.combine(fecha, hora)


def formatear_delta(segundos):
    """+3 d 02:15:00 / -00:05:30"""
    signo = "+" if segundos >= 0 else "-"
    s = abs(int(segundos))
    d, resto = divmod(s, 86400)
    h, resto = divmod(resto, 3600)
    m, sec = divmod(resto, 60)
    if d:
        return f"{signo}{d} d {h:02d}:{m:02d}:{sec:02d}"
    return f"{signo}{h:02d}:{m:02d}:{sec:02d}"


def get_recorded_at(entry):
    meta = entry.get("metadata")
    valor = meta.get("recorded_at") if isinstance(meta, dict) else ""
    return valor or entry.get("recorded_at") or ""


def _dt_base(entry):
    """Fecha ORIGINAL de la entrada (antes de cualquier corrección)."""
    tc = entry.get("time_correction")
    if isinstance(tc, dict):
        dt = _parse_iso(tc.get("original_recorded_at"))
        if dt:
            return dt
    dt = _parse_iso(get_recorded_at(entry))
    if dt:
        return dt
    return _parse_prefix(entry.get("fecha_prefix"))


def _set_recorded_at(entry, iso):
    entry["recorded_at"] = iso
    meta = entry.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        entry["metadata"] = meta
    meta["recorded_at"] = iso


def _ruta_principal(entry):
    if entry.get("is_photo") and entry.get("original_photos"):
        return entry["original_photos"][0]
    f = entry.get("file")
    ruta = f.get("video_path") if isinstance(f, dict) else ""
    return ruta or entry.get("video_path") or ""


def clave_carpeta(entry):
    """Carpeta de origen normalizada (las rutas del proyecto mezclan / y \\)."""
    ruta = _ruta_principal(entry).replace("\\", "/")
    return posixpath.dirname(ruta).rstrip("/").lower()


def indices_en_alcance(entries, idx, alcance):
    if alcance == ALCANCE_ARCHIVO:
        return [idx]
    clave = clave_carpeta(entries[idx])
    mismos = [i for i, e in enumerate(entries) if clave_carpeta(e) == clave]
    if alcance == ALCANCE_CARPETA:
        return mismos
    ref = _dt_base(entries[idx])
    resultado = []
    for i in mismos:
        dt = _dt_base(entries[i])
        if ref is not None and dt is not None:
            if dt >= ref:
                resultado.append(i)
        elif i >= idx:
            resultado.append(i)
    return resultado


def previsualizar(entries, idx, nueva_dt, alcance):
    """Calcula el efecto sin modificar nada. Lanza ValueError si la entrada no tiene fecha base."""
    ref = _dt_base(entries[idx])
    if ref is None:
        raise ValueError("Este archivo no tiene fecha de captura registrada.")
    delta = nueva_dt - ref
    indices = indices_en_alcance(entries, idx, alcance)
    afectadas = [i for i in indices if _dt_base(entries[i]) is not None]
    return {
        "delta_seconds": int(delta.total_seconds()),
        "afectadas": len(afectadas),
        "sin_fecha": len(indices) - len(afectadas),
        "original": ref.strftime(ISO_FMT),
        "nueva": nueva_dt.strftime(ISO_FMT),
    }


def aplicar_correccion(entries, idx, nueva_dt, alcance):
    """
    Aplica la corrección: delta = nueva_dt - fecha original de entries[idx], y se suma
    ese delta a la fecha original de cada entrada dentro del alcance.
    Un delta de 0 equivale a revertir.
    """
    info = previsualizar(entries, idx, nueva_dt, alcance)
    segundos = info["delta_seconds"]
    if segundos == 0:
        n = revertir_correccion(entries, idx, alcance)
        return {"afectadas": n, "delta_seconds": 0, "revertida": True}

    delta = timedelta(seconds=segundos)
    ahora = datetime.now().strftime(ISO_FMT)
    n = 0
    for i in indices_en_alcance(entries, idx, alcance):
        e = entries[i]
        base = _dt_base(e)
        if base is None:
            continue
        _set_recorded_at(e, (base + delta).strftime(ISO_FMT))
        e["time_correction"] = {
            "original_recorded_at": base.strftime(ISO_FMT),
            "delta_seconds": segundos,
            "scope": alcance,
            "applied_at": ahora,
        }
        e["metadata"]["Corrección Horaria"] = formatear_delta(segundos)
        n += 1
    return {"afectadas": n, "delta_seconds": segundos, "revertida": False}


def revertir_correccion(entries, idx, alcance):
    """Restaura la fecha original en las entradas corregidas dentro del alcance. Devuelve cuántas."""
    n = 0
    for i in indices_en_alcance(entries, idx, alcance):
        e = entries[i]
        tc = e.get("time_correction")
        if not isinstance(tc, dict):
            continue
        original = tc.get("original_recorded_at")
        if original:
            _set_recorded_at(e, original)
        e.pop("time_correction", None)
        if isinstance(e.get("metadata"), dict):
            e["metadata"].pop("Corrección Horaria", None)
        n += 1
    return n


def texto_previsualizacion(entries, idx, texto_fecha, texto_hora, alcance):
    """Devuelve (valido, texto) para mostrar en la ventana."""
    try:
        nueva = parse_fecha_hora(texto_fecha, texto_hora)
        info = previsualizar(entries, idx, nueva, alcance)
    except ValueError as e:
        return False, str(e)
    if info["delta_seconds"] == 0:
        return True, ("Sin desfase respecto a la fecha original.\n"
                      "Aplicar equivale a revertir la corrección del alcance elegido.")
    texto = (f"Desfase: {formatear_delta(info['delta_seconds'])}\n"
             f"Archivos afectados: {info['afectadas']}\n"
             f"Este archivo: {info['original']}  →  {info['nueva']}")
    if info["sin_fecha"]:
        texto += f"\n({info['sin_fecha']} sin fecha base: no se modificarán)"
    return True, texto


# =============================================================================
# 2. VENTANA DE CORRECCIÓN (Tk) - se invoca desde el tagger
# =============================================================================

def abrir_correccion_horaria(tagger):
    import tkinter as tk
    from tkinter import messagebox

    entries = getattr(tagger, "video_dirs", None)
    idx = getattr(tagger, "current_video_index", 0)
    if not entries or not (0 <= idx < len(entries)):
        return
    if getattr(tagger, "_time_fix_window", None) is not None:
        try:
            if tagger._time_fix_window.winfo_exists():
                tagger._time_fix_window.lift()
                return
        except Exception:
            pass

    entry = entries[idx]
    actual = _parse_iso(get_recorded_at(entry)) or _dt_base(entry) or datetime.now()
    tc = entry.get("time_correction")

    win = tk.Toplevel(tagger)
    win.title("Corregir fecha y hora de captura")
    win.transient(tagger)
    win.resizable(False, False)
    tagger._time_fix_window = win

    pad = {"padx": 10, "pady": 3}
    tk.Label(win, text=os.path.basename(_ruta_principal(entry)) or "(sin nombre)",
             font=("Arial", 10, "bold")).pack(anchor="w", **pad)
    tk.Label(win, text="Carpeta: " + (os.path.basename(clave_carpeta(entry)) or "(raíz)"),
             fg="#555").pack(anchor="w", padx=10)
    estado = f"Fecha actual: {actual.strftime(ISO_FMT)}"
    if isinstance(tc, dict):
        estado += f"\nOriginal: {tc.get('original_recorded_at', '')}  (corregida {formatear_delta(tc.get('delta_seconds', 0))})"
    tk.Label(win, text=estado, justify="left").pack(anchor="w", **pad)

    form = tk.Frame(win)
    form.pack(fill="x", **pad)
    var_fecha = tk.StringVar(value=actual.strftime("%Y-%m-%d"))
    var_hora = tk.StringVar(value=actual.strftime("%H:%M:%S"))
    tk.Label(form, text="Fecha real (AAAA-MM-DD):").grid(row=0, column=0, sticky="e", pady=2)
    tk.Entry(form, textvariable=var_fecha, width=14).grid(row=0, column=1, sticky="w", padx=5)
    tk.Label(form, text="Hora real (HH:MM:SS):").grid(row=1, column=0, sticky="e", pady=2)
    tk.Entry(form, textvariable=var_hora, width=14).grid(row=1, column=1, sticky="w", padx=5)

    marco = tk.LabelFrame(win, text="Aplicar a")
    marco.pack(fill="x", **pad)
    var_alcance = tk.StringVar(value=ALCANCE_CARPETA)
    for valor, texto in (
        (ALCANCE_ARCHIVO, "Solo este archivo"),
        (ALCANCE_DESDE_AQUI, "Este y los siguientes de la carpeta"),
        (ALCANCE_CARPETA, "Toda la carpeta"),
    ):
        tk.Radiobutton(marco, text=texto, value=valor, variable=var_alcance).pack(anchor="w", padx=8)

    lbl_prev = tk.Label(win, text="", justify="left", anchor="w", wraplength=380)
    lbl_prev.pack(fill="x", **pad)

    btns = tk.Frame(win)
    btns.pack(fill="x", padx=10, pady=8)
    btn_aplicar = tk.Button(btns, text="Aplicar", bg="#4CAF50", fg="black", width=10)
    btn_revertir = tk.Button(btns, text="Revertir", width=10)
    btn_cerrar = tk.Button(btns, text="Cerrar", width=10, command=win.destroy)
    btn_cerrar.pack(side="right", padx=3)
    btn_revertir.pack(side="right", padx=3)
    btn_aplicar.pack(side="right", padx=3)

    def refrescar(*_):
        valido, texto = texto_previsualizacion(
            entries, idx, var_fecha.get(), var_hora.get(), var_alcance.get())
        lbl_prev.config(text=texto, fg=("black" if valido else "#b00020"))
        btn_aplicar.config(state=("normal" if valido else "disabled"))

    for v in (var_fecha, var_hora, var_alcance):
        v.trace_add("write", refrescar)
    refrescar()

    def _guardar_y_refrescar():
        try:
            tagger.save_metadata()
        except Exception as e:
            print(f"⚠️ No se pudo guardar tras la corrección horaria: {e}")
        try:
            if hasattr(tagger, "_update_meta_preview"):
                tagger._update_meta_preview(entries[idx].get("metadata", {}))
        except Exception:
            pass

    def aplicar():
        try:
            nueva = parse_fecha_hora(var_fecha.get(), var_hora.get())
            info = previsualizar(entries, idx, nueva, var_alcance.get())
        except ValueError as e:
            messagebox.showerror("Corrección horaria", str(e), parent=win)
            return
        if not messagebox.askyesno(
                "Confirmar corrección",
                f"Desfase: {formatear_delta(info['delta_seconds'])}\n"
                f"Se modificará la fecha de {info['afectadas']} archivo(s).\n\n¿Continuar?",
                parent=win):
            return
        res = aplicar_correccion(entries, idx, nueva, var_alcance.get())
        _guardar_y_refrescar()
        if res.get("revertida"):
            messagebox.showinfo("Corrección horaria",
                                f"Se revirtieron {res['afectadas']} archivo(s).", parent=tagger)
        else:
            messagebox.showinfo("Corrección horaria",
                                f"Fecha corregida en {res['afectadas']} archivo(s).\n"
                                "Los archivos originales no se modifican; marque 'Copias fecha corregida' "
                                "para generar copias con la fecha y hora corregidas al finalizar la sesión.",
                                parent=tagger)
        win.destroy()

    def revertir():
        n = len([i for i in indices_en_alcance(entries, idx, var_alcance.get())
                 if isinstance(entries[i].get("time_correction"), dict)])
        if n == 0:
            messagebox.showinfo("Corrección horaria",
                                "No hay correcciones para revertir en ese alcance.", parent=win)
            return
        if not messagebox.askyesno("Revertir", f"Se restaurará la fecha original en {n} archivo(s).\n\n¿Continuar?",
                                   parent=win):
            return
        revertir_correccion(entries, idx, var_alcance.get())
        _guardar_y_refrescar()
        win.destroy()

    btn_aplicar.config(command=aplicar)
    btn_revertir.config(command=revertir)
    win.bind("<Escape>", lambda e: win.destroy())
    win.update_idletasks()
    try:
        win.grab_set()
    except Exception:
        pass


# =============================================================================
# 3. EXPORTACIÓN DE COPIAS CON FECHA CORREGIDA (los originales nunca se tocan)
# =============================================================================

def _ruta_ffmpeg():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    nombre = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    ruta = os.path.join(base, "resources", "ffmpeg", nombre)
    return ruta if os.path.exists(ruta) else "ffmpeg"


def _destino_unico(carpeta, nombre):
    destino = os.path.join(carpeta, nombre)
    if not os.path.exists(destino):
        return destino
    base, ext = os.path.splitext(nombre)
    n = 1
    while os.path.exists(os.path.join(carpeta, f"{base}_{n}{ext}")):
        n += 1
    return os.path.join(carpeta, f"{base}_{n}{ext}")


def _ajustar_exif_jpeg(ruta_copia, ruta_original, delta):
    """Suma 'delta' a las fechas EXIF de la copia, sin recomprimir la imagen."""
    try:
        import piexif
    except ImportError:
        raise RuntimeError("Falta la librería piexif (pip install piexif)")

    exif = piexif.load(ruta_copia)
    exif_ifd = exif.setdefault("Exif", {})
    ifd0 = exif.setdefault("0th", {})
    tags = (
        (exif_ifd, piexif.ExifIFD.DateTimeOriginal),
        (exif_ifd, piexif.ExifIFD.DateTimeDigitized),
        (ifd0, piexif.ImageIFD.DateTime),
    )

    def _leer(valor):
        try:
            return datetime.strptime(valor.decode("ascii").strip(), EXIF_FMT)
        except Exception:
            return None

    modificado = False
    for ifd, tag in tags:
        dt = _leer(ifd[tag]) if tag in ifd else None
        if dt is not None:
            ifd[tag] = (dt + delta).strftime(EXIF_FMT).encode("ascii")
            modificado = True

    if not modificado:
        # Sin fecha EXIF utilizable: se parte de la fecha de modificación (igual que el programa)
        base = datetime.fromtimestamp(os.path.getmtime(ruta_original)) + delta
        texto = base.strftime(EXIF_FMT).encode("ascii")
        exif_ifd[piexif.ExifIFD.DateTimeOriginal] = texto
        exif_ifd[piexif.ExifIFD.DateTimeDigitized] = texto
        ifd0[piexif.ImageIFD.DateTime] = texto

    try:
        datos = piexif.dump(exif)
    except Exception:
        # Algunas notas del fabricante no se pueden reescribir: se descarta solo esa nota
        exif_ifd.pop(piexif.ExifIFD.MakerNote, None)
        exif["thumbnail"] = None
        datos = piexif.dump(exif)
    piexif.insert(datos, ruta_copia)


def _copiar_video_con_fecha(origen, destino, nueva_fecha_iso):
    cmd = [_ruta_ffmpeg(), "-i", origen, "-c", "copy",
           "-metadata", f"creation_time={nueva_fecha_iso}.000000Z", "-y", destino]
    r = subprocess.run(cmd, capture_output=True, timeout=600, creationflags=_WIN_NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(destino):
        if os.path.exists(destino):
            os.remove(destino)
        raise RuntimeError("ffmpeg no pudo generar la copia")


def exportar_copias_corregidas(entries, output_folder, session_id, progreso=None, omitir=None):
    """
    Genera copias con fecha/hora corregida de las entradas que tienen time_correction.
    Destino: <output_folder>/corrected/<session_id>/<carpeta_origen>/<archivo>
    'omitir': conjunto de rutas de VIDEOS (os.path.normcase(os.path.abspath(ruta))) que ya
    salieron en otra copia (por ejemplo la del embed metadata, que ya lleva la fecha corregida).
    Devuelve {"copiadas": n, "errores": [...], "destino": ruta}.
    """
    destino_raiz = os.path.join(output_folder, "corrected", str(session_id))
    pendientes = [e for e in entries
                  if isinstance(e.get("time_correction"), dict)
                  and not (e.get("ui") or {}).get("is_excluded", False)]
    resultado = {"copiadas": 0, "errores": [], "destino": destino_raiz}
    if not pendientes:
        return resultado

    registro = []
    for k, e in enumerate(pendientes, 1):
        tc = e["time_correction"]
        delta = timedelta(seconds=int(tc.get("delta_seconds", 0)))
        nueva_iso = get_recorded_at(e)
        if e.get("is_photo"):
            archivos = [p for p in (e.get("original_photos") or [])]
        else:
            archivos = [_ruta_principal(e)]

        for origen in archivos:
            nombre = os.path.basename(origen.replace("\\", "/"))
            if (omitir and origen and not e.get("is_photo")
                    and os.path.normcase(os.path.abspath(origen)) in omitir):
                continue
            if not origen or not os.path.exists(origen):
                resultado["errores"].append(f"{nombre}: archivo original no encontrado")
                continue
            carpeta = os.path.join(destino_raiz, os.path.basename(clave_carpeta(e)) or "sin_carpeta")
            try:
                os.makedirs(carpeta, exist_ok=True)
                destino = _destino_unico(carpeta, nombre)
                ext = os.path.splitext(nombre)[1].lower()
                if ext in _JPEG_EXTS:
                    shutil.copy2(origen, destino)
                    try:
                        _ajustar_exif_jpeg(destino, origen, delta)
                    except Exception:
                        if os.path.exists(destino):
                            os.remove(destino)
                        raise
                elif e.get("is_photo"):
                    raise RuntimeError("formato sin EXIF editable (solo JPEG)")
                else:
                    _copiar_video_con_fecha(origen, destino, nueva_iso)
                resultado["copiadas"] += 1
                registro.append({
                    "original": origen,
                    "copia": destino,
                    "delta_seconds": int(delta.total_seconds()),
                    "recorded_at_original": tc.get("original_recorded_at", ""),
                    "recorded_at_corregido": nueva_iso,
                })
            except Exception as ex:
                resultado["errores"].append(f"{nombre}: {ex}")
        if progreso:
            try:
                progreso(k, len(pendientes))
            except Exception:
                pass

    if registro:
        try:
            with open(os.path.join(destino_raiz, "correcciones_horarias.json"), "w", encoding="utf-8") as f:
                json.dump(registro, f, indent=4, ensure_ascii=False)
        except Exception as ex:
            resultado["errores"].append(f"No se pudo escribir el registro: {ex}")
    return resultado


# =============================================================================
# EXPORTACIÓN AL FINALIZAR LA SESIÓN (CSV acumulado, embed y copias corregidas)
# =============================================================================

CSV_NOMBRE = "export_acumulado.csv"

CAMPOS_CSV_DEFECTO = [
    "session_id", "site", "subsite", "camera", "operator",
    "recorded_at", "species", "behaviors", "counts", "notes", "time_sec",
]


# =============================================================================
# Helpers
# =============================================================================

def _activo(entry):
    return not (entry.get("ui") or {}).get("is_excluded", False)


def _norm(ruta):
    return os.path.normcase(os.path.abspath(ruta)) if ruta else ""


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, (list, tuple)):
        return ", ".join(str(v) for v in valor)
    if isinstance(valor, dict):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _fila(entry, session_id=""):
    """Fila plana de una entrada (mismo aplanado que el resto de las exportaciones)."""
    flat = flatten_metadata(entry)
    # En el modelo actual 'processing' llega vacío y estos datos están en la raíz de la entrada
    for k in ("status", "frames", "time_sec"):
        if flat.get(k) in ("", None) and entry.get(k) not in ("", None):
            flat[k] = entry.get(k)
    if not flat.get("session_id"):
        flat["session_id"] = entry.get("session_id") or session_id
    f = entry.get("file") if isinstance(entry.get("file"), dict) else {}
    flat["video_hash"] = f.get("video_hash") or entry.get("video_hash") or ""
    # Si hubo corrección horaria, la fecha vigente ya está en metadata.recorded_at
    flat["recorded_at"] = get_recorded_at(entry) or flat.get("recorded_at", "")
    return flat


def _campos_config(config, clave, defecto):
    campos = (config.get("MetadataSettings") or {}).get(clave) or defecto
    return [c for c in campos if isinstance(c, str) and c]


# =============================================================================
# CSV ACUMULADO
# =============================================================================

def exportar_csv_acumulado(entries, config, session_id, output_folder):
    """
    Anexa las filas de la sesión a output/export_acumulado.csv con los campos por defecto.
    - Si la sesión ya estaba en el archivo, sus filas se reemplazan (no se duplican).
    - Si cambian los campos por defecto, se agregan las columnas nuevas al final.
    - Escritura atómica. Si el archivo está abierto en Excel, se guarda un CSV solo de esta sesión.
    Devuelve {"ruta", "filas_nuevas", "filas_total", "avisos"}.
    """
    campos = _campos_config(config, "ExcelFieldsDefault", CAMPOS_CSV_DEFECTO)
    if "session_id" not in campos:
        campos.insert(0, "session_id")  # necesario para no duplicar sesiones

    nuevas = []
    for e in entries:
        if not _activo(e):
            continue
        flat = _fila(e, session_id)
        nuevas.append({c: _texto(flat.get(c)) for c in campos})
    res = {"ruta": os.path.join(output_folder, CSV_NOMBRE),
           "filas_nuevas": len(nuevas), "filas_total": 0, "avisos": []}
    if not nuevas:
        return res

    ruta = res["ruta"]
    cabecera_previa, previas = [], []
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", newline="", encoding="utf-8-sig") as f:
                lector = csv.DictReader(f)
                cabecera_previa = list(lector.fieldnames or [])
                previas = list(lector)
        except Exception as ex:
            # Archivo ilegible: se conserva aparte y se empieza uno nuevo
            respaldo = ruta.replace(".csv", f".ilegible_{datetime.now().strftime('%y%m%d_%H%M%S')}.csv")
            try:
                os.replace(ruta, respaldo)
                res["avisos"].append(f"El CSV acumulado no se pudo leer ({ex}); se guardó como {os.path.basename(respaldo)}.")
            except Exception:
                res["avisos"].append(f"El CSV acumulado no se pudo leer ({ex}).")
            cabecera_previa, previas = [], []

    ids_nuevos = {r.get("session_id", "") for r in nuevas}
    previas = [r for r in previas if r.get("session_id", "") not in ids_nuevos]
    cabecera = cabecera_previa + [c for c in campos if c not in cabecera_previa]
    filas = previas + nuevas
    res["filas_total"] = len(filas)

    def _escribir(destino, columnas, filas_a_escribir):
        tmp = destino + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore", restval="")
            w.writeheader()
            w.writerows(filas_a_escribir)
        os.replace(tmp, destino)

    os.makedirs(output_folder, exist_ok=True)
    try:
        _escribir(ruta, cabecera, filas)
    except PermissionError:
        alterno = os.path.join(output_folder, f"export_{session_id}.csv")
        _escribir(alterno, campos, nuevas)
        res["ruta"] = alterno
        res["filas_total"] = len(nuevas)
        res["avisos"].append(
            f"{CSV_NOMBRE} está abierto en otro programa (¿Excel?). Los datos de esta sesión se "
            f"guardaron en {os.path.basename(alterno)}; ciérrelo y vuelva a finalizar para anexarlos.")
    return res


# =============================================================================
# ORQUESTADOR (lo invoca el tagger al finalizar la sesión)
# =============================================================================

def ejecutar_al_finalizar(tagger):
    import tkinter as tk
    from tkinter import messagebox
    from embed_metadata import embeber_copias  # import diferido: embed_metadata importa export_utils

    entries = tagger.video_dirs
    config = tagger.config_data
    out = tagger.output_folder
    sid = tagger.session_id

    para_embed = [e for e in entries if _activo(e) and (e.get("ui") or {}).get("embed_metadata")]
    para_csv = [e for e in entries if _activo(e) and (e.get("ui") or {}).get("xlsx")]
    var_corr = getattr(tagger, "export_corrected_var", None)
    quiere_corregidas = bool(var_corr.get()) if var_corr is not None else False
    if not (para_embed or para_csv or quiere_corregidas):
        return

    ventana, etiqueta = None, None
    try:
        ventana = tk.Toplevel(tagger)
        ventana.title("Finalizando sesión")
        ventana.transient(tagger)
        etiqueta = tk.Label(ventana, text="Preparando...", padx=30, pady=20)
        etiqueta.pack()
        ventana.update()
    except Exception:
        ventana = etiqueta = None

    def estado(texto):
        try:
            if etiqueta is not None:
                etiqueta.config(text=texto)
                ventana.update()
        except Exception:
            pass

    lineas, errores, avisos = [], [], []
    embebidos = set()

    if para_embed:
        estado("Generando copias con metadata incrustada...")
        try:
            r = embeber_copias(para_embed, config, out, sid,
                               progreso=lambda i, n: estado(f"Copias con metadata: {i}/{n}"))
            embebidos = r["embebidos"]
            linea = f"Copias con metadata: {r['copiadas']} video(s)\n   {r['destino']}"
            if r["fotos_omitidas"]:
                linea += f"\n   ({r['fotos_omitidas']} foto(s) omitidas: el embed es solo para videos)"
            lineas.append(linea)
            errores += r["errores"]
        except Exception as ex:
            errores.append(f"Embed metadata: {ex}")

    if para_csv:
        estado("Actualizando CSV acumulado...")
        try:
            r = exportar_csv_acumulado(para_csv, config, sid, out)
            lineas.append(f"CSV acumulado: {r['filas_nuevas']} fila(s) de esta sesión "
                          f"(total {r['filas_total']})\n   {r['ruta']}")
            avisos += r["avisos"]
        except Exception as ex:
            errores.append(f"CSV acumulado: {ex}")

    if quiere_corregidas:
        estado("Generando copias con fecha corregida...")
        try:
            r = exportar_copias_corregidas(entries, out, sid, omitir=embebidos)
            if r["copiadas"]:
                lineas.append(f"Copias con fecha corregida: {r['copiadas']} archivo(s)\n   {r['destino']}")
            errores += r["errores"]
        except Exception as ex:
            errores.append(f"Copias con fecha corregida: {ex}")

    try:
        if ventana is not None:
            ventana.destroy()
    except Exception:
        pass

    if not (lineas or errores or avisos):
        return
    msg = "\n\n".join(lineas) if lineas else "No se generó ningún archivo."
    if avisos:
        msg += "\n\n" + "\n".join(avisos)
    if errores:
        msg += f"\n\nNo se pudieron procesar {len(errores)}:\n" + "\n".join(errores[:10])
        if len(errores) > 10:
            msg += f"\n... y {len(errores) - 10} más"
    (messagebox.showwarning if (errores or avisos) else messagebox.showinfo)("Sesión finalizada", msg)
