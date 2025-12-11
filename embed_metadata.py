# gui_embed_metadata.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import subprocess
from config_utils import load_config
from filter_utils import (
    filter_videos,
    get_unique_tags,
    get_unique_values
)

class EmbedMetadataGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Incrustar Metadatos en Videos")
        self.geometry("700x600")

        self.config = load_config()
        self.consolidated_path = os.path.join(
            self.config["General"]["output_folder"],
            "consolidated",
            "all_sessions_metadata.json"
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

        # Campos predeterminados desde config.ini
        self.default_fields = self.config.get("MetadataSettings", {}).get(
            "fields_to_embed",
            ["session_id", "site", "camera", "operator", "tags"]
        )

        self.selected_filters = {}
        self.build_ui()

    def build_ui(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Filtros avanzados ---
        tk.Button(main_frame, text="Filtros avanzados...", 
                  command=self.open_advanced_filters).pack(anchor="w", pady=(0, 10))

        # --- Selección de campos a incrustar ---
        tk.Label(main_frame, text="Metadatos a incrustar:", 
                 font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 5))
        
        fields_frame = tk.Frame(main_frame)
        fields_frame.pack(fill="x", pady=5)
        
        self.field_vars = {}
        all_possible_fields = set()
        for entry in self.all_metadata:
            all_possible_fields.update(entry.keys())
        all_fields = sorted([f for f in all_possible_fields if f != "video_path"])

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
    # Filtros avanzados (reutiliza lógica de Excel Export)
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
        tk.Label(win, text="Sesión:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
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

        # Tags
        tags = get_unique_tags(self.all_metadata)
        if tags:
            tk.Label(win, text="Especies:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
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
            tk.Label(win, text="Operadores:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
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
    # Incrustar metadatos
    # -------------------------
    def embed_metadata(self):
        try:
            # 1. Filtrar videos
            filtered_data = filter_videos(self.all_metadata, **self.selected_filters)
            
            # 2. Aplicar filtro adicional: solo si "embed_metadata" está marcado
            if self.only_embed_marked.get():
                filtered_data = [v for v in filtered_data if v.get("embed_metadata", False)]
            
            if not filtered_
                messagebox.showwarning("Advertencia", "No hay videos que coincidan con los filtros.")
                return

            # 3. Obtener campos seleccionados
            selected_fields = [f for f, var in self.field_vars.items() if var.get()]
            if not selected_
                messagebox.showerror("Error", "Seleccione al menos un campo para incrustar.")
                return

            # 4. Procesar cada video
            success_count = 0
            for video_meta in filtered_
                video_path = video_meta.get("video_path")
                if not video_path or not os.path.exists(video_path):
                    continue

                # Construir diccionario de metadatos
                metadata_dict = {}
                for field in selected_:
                    value = video_meta.get(field, "")
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    if value:
                        metadata_dict[field] = str(value)

                if metadata_dict:
                    if self._embed_with_ffmpeg(video_path, metadata_dict):
                        success_count += 1

            messagebox.showinfo("Éxito", f"Metadatos incrustados en {success_count} videos.")
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo incrustar metadatos:\n{str(e)}")

    def _embed_with_ffmpeg(self, video_path, metadata_dict):
        """Incrusta metadatos usando ffmpeg (método no destructivo: crea copia temporal)."""
        try:
            temp_path = video_path + ".tmp.mp4"
            cmd = ["ffmpeg", "-i", video_path, "-c", "copy"]
            
            # Añadir metadatos
            for key, value in metadata_dict.items():
                cmd += ["-metadata", f"{key}={value}"]
            
            cmd.append(temp_path)
            
            # Ejecutar ffmpeg silenciosamente
            result = subprocess.run(cmd, 
                                   stdout=subprocess.DEVNULL, 
                                   stderr=subprocess.DEVNULL, 
                                   timeout=300)
            
            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, video_path)
                return True
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
                
        except Exception:
            if os.path.exists(video_path + ".tmp.mp4"):
                os.remove(video_path + ".tmp.mp4")
            return False