import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import subprocess
from datetime import datetime
from config_utils import load_config
from export_utils import (
    filter_videos,
    get_unique_tags,
    get_unique_values,
    _WIN_NO_WINDOW,
    _campos_config,
    _destino_unico,
    _fila,
    _norm,
    _ruta_ffmpeg,
    _ruta_principal,
    _texto,
    clave_carpeta,
    get_recorded_at,
)

class EmbedMetadataGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Incrustar Metadatos en Videos")
        self.geometry("700x600")
        
        self.config = load_config()
        self.consolidated_path = os.path.join(
            self.config["General"]["output_folder"],
            "consolidated", "all_sessions_metadata.json"
        )
        
        if not os.path.exists(self.consolidated_path):
            messagebox.showerror(
                "Error",
                "No se encontró el archivo consolidado.\n"
                "Complete al menos una sesión de etiquetado primero."
            )
            self.destroy()
            return

        with open(self.consolidated_path, "r", encoding="utf-8") as f:
            self.all_metadata = json.load(f)

        # Campos predeterminados optimizados para el modelo nuevo
        self.default_fields = self.config.get("MetadataSettings", {}).get(
            "fields_to_embed",
            ["session_id", "site", "camera", "operator", "species", "recorded_at"]
        )

        self.selected_filters = {}
        self.build_ui()

    def build_ui(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Filtros avanzados ---
        tk.Button(main_frame, text="Filtros avanzados... ", 
                  command=self.open_advanced_filters).pack(anchor="w", pady=(0, 10))

        # --- Selección de campos a incrustar ---
        tk.Label(main_frame, text="Metadatos a incrustar: ", 
                 font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 5))
        
        fields_frame = tk.Frame(main_frame)
        fields_frame.pack(fill="x", pady=5)
        
        self.field_vars = {}
        # Lista curada y compatible con el modelo anidado
        all_fields = [
            "session_id", "site", "subsite", "camera", "operator",
            "recorded_at", "species", "behaviors", "status", "time_sec", "notes"
        ]

        for i, field in enumerate(all_fields):
            var = tk.BooleanVar(value=(field in self.default_fields))
            cb = tk.Checkbutton(fields_frame, text=field, variable=var)
            cb.grid(row=i//3, column=i%3, sticky="w", padx=5, pady=2)
            self.field_vars[field] = var

        # --- Opción: solo videos marcados con "Embed metadata" ---
        self.only_embed_marked = tk.BooleanVar(value=True)
        tk.Checkbutton(
            main_frame,
            text="Solo videos con 'Embed metadata' marcado",
            variable=self.only_embed_marked,
            font=("Arial", 10)
        ).pack(anchor="w", pady=5)

        # --- Botones ---
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="Cancelar", 
                  command=self.destroy, width=12).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Incrustar Metadatos", 
                  command=self.embed_metadata, bg="#607d8b", fg="white", width=18).pack(side="left", padx=5)

    # -------------------------
    # Filtros avanzados
    # -------------------------
    def open_advanced_filters(self):
        if hasattr(self, '_filter_window') and tk.Toplevel.winfo_exists(self._filter_window):
            self._filter_window.lift()
            return

        win = tk.Toplevel(self)
        win.title("Filtros avanzados")
        win.geometry("500x450")
        self._filter_window = win

        # Sesión
        tk.Label(win, text="Sesión: ", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        session_frame = tk.Frame(win)
        session_frame.pack(fill="x", padx=10, pady=2)
        self.session_var = tk.StringVar(value=self.selected_filters.get("session_filter", "all"))
        tk.Radiobutton(session_frame, text="Todas", variable=self.session_var, value="all").pack(side="left")
        tk.Radiobutton(session_frame, text="Última", variable=self.session_var, value="last").pack(side="left", padx=5)
        self.session_entry = tk.Entry(session_frame, width=15)
        self.session_entry.pack(side="left", padx=5)
        if self.selected_filters.get("session_filter", "").startswith("specific:"):
            spec_id = self.selected_filters["session_filter"].split(":", 1)[1]
            self.session_entry.insert(0, spec_id)
            self.session_var.set("specific")

        # Tags / Especies
        tags = get_unique_tags(self.all_metadata)
        if tags:
            tk.Label(win, text="Especies: ", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            tag_frame = tk.Frame(win)
            tag_frame.pack(fill="x", padx=10, pady=2)
            self.tag_vars = {}
            for i, tag in enumerate(tags):
                var = tk.BooleanVar(value=tag in self.selected_filters.get("tags", []))
                cb = tk.Checkbutton(tag_frame, text=tag, variable=var)
                cb.grid(row=i//3, column=i%3, sticky="w", padx=5)
                self.tag_vars[tag] = var

        # Operadores
        operators = get_unique_values(self.all_metadata, "operator")
        if operators:
            tk.Label(win, text="Operadores: ", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            op_frame = tk.Frame(win)
            op_frame.pack(fill="x", padx=10, pady=2)
            self.op_vars = {}
            for i, op in enumerate(operators):
                var = tk.BooleanVar(value=op in self.selected_filters.get("operators", []))
                cb = tk.Checkbutton(op_frame, text=op, variable=var)
                cb.grid(row=i//3, column=i%3, sticky="w", padx=5)
                self.op_vars[op] = var

        # Botones
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Aplicar", 
                  command=lambda: [self._apply_filters(), win.destroy()]).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="left", padx=5)

    def _apply_filters(self):
        filters = {}
        session_opt = self.session_var.get()
        if session_opt == "last":
            filters["session_filter"] = "last"
        elif session_opt == "specific":
            spec_id = self.session_entry.get().strip()
            filters["session_filter"] = f"specific:{spec_id}" if spec_id else "all"
        else:
            filters["session_filter"] = "all"

        if hasattr(self, 'tag_vars'):
            selected_tags = [t for t, var in self.tag_vars.items() if var.get()]
            if selected_tags:
                filters["tags"] = selected_tags

        if hasattr(self, 'op_vars'):
            selected_ops = [o for o, var in self.op_vars.items() if var.get()]
            if selected_ops:
                filters["operators"] = selected_ops

        self.selected_filters = filters

    # -------------------------
    # Incrustar metadatos (genera COPIAS; los originales nunca se modifican)
    # -------------------------
    def embed_metadata(self):
        try:
            # 1. Filtrar videos
            filtered_data = filter_videos(self.all_metadata, **self.selected_filters)

            # 2. Aplicar filtro adicional: solo si "embed_metadata" está marcado en UI
            if self.only_embed_marked.get():
                filtered_data = [v for v in filtered_data if v.get("ui", {}).get("embed_metadata", False)]

            if not filtered_data:
                messagebox.showwarning("Advertencia", "No hay videos que coincidan con los filtros.")
                return

            # 3. Obtener campos seleccionados
            selected_fields = [f for f, var in self.field_vars.items() if var.get()]
            if not selected_fields:
                messagebox.showerror("Error", "Seleccione al menos un campo para incrustar.")
                return

            # 4. Mismo procedimiento que al finalizar una sesión en el tagger (copias en
            #    output/embedded/<id>/<carpeta>/), pero con los campos elegidos aquí
            id_lote = "manual_" + datetime.now().strftime("%y%m%d_%H%M%S")
            res = embeber_copias(
                filtered_data, self.config,
                self.config["General"]["output_folder"], id_lote,
                campos=selected_fields)

            msg = f"Copias con metadata incrustada: {res['copiadas']} video(s)\n{res['destino']}"
            if res["fotos_omitidas"]:
                msg += f"\n({res['fotos_omitidas']} foto(s) omitidas: el embed es solo para videos)"
            msg += "\n\nLos archivos originales no fueron modificados."
            if res["errores"]:
                msg += f"\n\nNo se pudieron procesar {len(res['errores'])}:\n" + "\n".join(res["errores"][:10])
                if len(res["errores"]) > 10:
                    msg += f"\n... y {len(res['errores']) - 10} más"
                messagebox.showwarning("Incrustación finalizada", msg)
            else:
                messagebox.showinfo("Éxito", msg)
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo incrustar metadatos:\n{str(e)}")


# =============================================================================
# EMBED POR SESIÓN: copias con metadata incrustada (se invoca al finalizar el tagging)
# Los archivos originales NUNCA se modifican.
# =============================================================================

CAMPOS_EMBED_DEFECTO = [
    "session_id", "site", "subsite", "camera", "operator",
    "species", "behaviors", "status", "frames", "time_sec",
    "recorded_at", "notes",
]
_EXT_MOV = {".mp4", ".m4v", ".mov", ".3gp", ".3g2"}


def _copiar_video_con_metadata(origen, destino, meta, creation_iso=None):
    """
    Copia el video con las etiquetas incrustadas (-c copy, sin recodificar).
    - MP4/MOV: etiquetas personalizadas con -movflags use_metadata_tags.
    - MKV: etiquetas personalizadas directas.
    - AVI: solo admite campos estándar; todo queda resumido en 'comment'.
    En todos los casos se agrega 'comment' con un resumen clave=valor legible.
    """
    ext = os.path.splitext(origen)[1].lower()
    cmd = [_ruta_ffmpeg(), "-i", origen, "-c", "copy"]
    if ext in _EXT_MOV:
        cmd += ["-movflags", "use_metadata_tags"]
    for k, v in meta.items():
        cmd += ["-metadata", f"{k}={v}"]
    if "comment" not in meta and meta:
        resumen = "; ".join(f"{k}={v}" for k, v in meta.items())
        cmd += ["-metadata", f"comment={resumen}"]
    if creation_iso:
        cmd += ["-metadata", f"creation_time={creation_iso}.000000Z"]
    cmd += ["-y", destino]
    r = subprocess.run(cmd, capture_output=True, timeout=600, creationflags=_WIN_NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(destino):
        if os.path.exists(destino):
            os.remove(destino)
        raise RuntimeError("ffmpeg no pudo generar la copia")


def embeber_copias(entries, config, output_folder, session_id, progreso=None, campos=None):
    """
    Genera copias de los videos con las etiquetas incrustadas.
    Devuelve {"copiadas", "errores", "fotos_omitidas", "destino", "embebidos"}.
    'embebidos' = rutas de origen (normalizadas) ya copiadas, para no duplicar copias.
    'campos': lista de campos a incrustar; si es None se usan los de la configuración
    (fields_to_embed) o los predeterminados. Es el mismo procedimiento para el tagger y la herramienta manual.
    """
    if not campos:
        campos = _campos_config(config, "fields_to_embed", CAMPOS_EMBED_DEFECTO)
    destino_raiz = os.path.join(output_folder, "embedded", str(session_id))
    res = {"copiadas": 0, "errores": [], "fotos_omitidas": 0,
           "destino": destino_raiz, "embebidos": set()}

    for k, e in enumerate(entries, 1):
        if e.get("is_photo"):
            res["fotos_omitidas"] += 1
            continue
        origen = _ruta_principal(e)
        nombre = os.path.basename(origen.replace("\\", "/")) or "(sin nombre)"
        if not origen or not os.path.exists(origen):
            res["errores"].append(f"{nombre}: archivo original no encontrado")
            continue
        try:
            flat = _fila(e, session_id)
            meta = {c: _texto(flat.get(c)) for c in campos if _texto(flat.get(c)) != ""}
            creation = get_recorded_at(e) if isinstance(e.get("time_correction"), dict) else None
            carpeta = os.path.join(destino_raiz, os.path.basename(clave_carpeta(e)) or "sin_carpeta")
            os.makedirs(carpeta, exist_ok=True)
            destino = _destino_unico(carpeta, nombre)
            _copiar_video_con_metadata(origen, destino, meta, creation)
            res["copiadas"] += 1
            res["embebidos"].add(_norm(origen))
        except Exception as ex:
            res["errores"].append(f"{nombre}: {ex}")
        if progreso:
            try:
                progreso(k, len(entries))
            except Exception:
                pass
    return res


if __name__ == "__main__":
    app = EmbedMetadataGUI()
    app.mainloop()