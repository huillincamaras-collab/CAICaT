import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import subprocess
from config_utils import load_config
from export_utils import (
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
    # Helper: Extraer valor del modelo unificado
    # -------------------------
    def _extract_field_value(self, entry, field):
        """Navega la estructura anidada y retorna el valor como string."""
        mapping = {
            "session_id": entry.get("session", {}).get("session_id", entry.get("session_id", "")),
            "site": entry.get("metadata", {}).get("site", ""),
            "subsite": entry.get("metadata", {}).get("subsite", ""),
            "camera": entry.get("metadata", {}).get("camera", ""),
            "operator": entry.get("metadata", {}).get("operator", ""),
            "recorded_at": entry.get("metadata", {}).get("recorded_at", ""),
            "notes": entry.get("metadata", {}).get("notes", ""),
            "species": ", ".join(entry.get("classification", {}).get("species", [])),
            "behaviors": ", ".join(entry.get("classification", {}).get("behaviors", [])),
            "status": entry.get("processing", {}).get("status", ""),
            "time_sec": entry.get("processing", {}).get("time_sec", ""),
        }
        return str(mapping.get(field, entry.get(field, "")))

    # -------------------------
    # Incrustar metadatos
    # -------------------------
    def embed_metadata(self):
        try:
            # 1. Filtrar videos
            filtered_data = filter_videos(self.all_metadata, **self.selected_filters)
            
            # 2. Aplicar filtro adicional: solo si "embed_metadata" está marcado en UI
            if self.only_embed_marked.get():
                # 🔹 CORREGIDO para modelo nuevo
                filtered_data = [v for v in filtered_data if v.get("ui", {}).get("embed_metadata", False)]
            
            if not filtered_data:
                messagebox.showwarning("Advertencia", "No hay videos que coincidan con los filtros.")
                return

            # 3. Obtener campos seleccionados
            selected_fields = [f for f, var in self.field_vars.items() if var.get()]
            if not selected_fields:
                messagebox.showerror("Error", "Seleccione al menos un campo para incrustar.")
                return

            # 4. Procesar cada video
            success_count = 0
            for video_meta in filtered_data:
                video_path = video_meta.get("file", {}).get("video_path") or video_meta.get("video_path")
                if not video_path or not os.path.exists(video_path):
                    continue

                # Construir diccionario de metadatos
                metadata_dict = {}
                for field in selected_fields:
                    value = self._extract_field_value(video_meta, field)
                    if value and value != "":
                        metadata_dict[field] = value

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
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 🔒 FIX BUG-004: Cross-platform binary name
            ffmpeg_bin = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
            ffmpeg_path = os.path.join(base_dir, 'resources', 'ffmpeg', ffmpeg_bin)

            if not os.path.exists(ffmpeg_path):
                ffmpeg_path = "ffmpeg"

            cmd = [ffmpeg_path, "-i", video_path, "-c", "copy"]            
            
            # Añadir metadatos
            for key, value in metadata_dict.items():
                cmd += ["-metadata", f"{key}={value}"]
            
            cmd.extend(["-y", temp_path])
            
            # 🔒 FIX BUG-003: Proper timeout handling with graceful error recovery
            try:
                result = subprocess.run(cmd, 
                                       stdout=subprocess.DEVNULL, 
                                       stderr=subprocess.DEVNULL, 
                                       timeout=300,
                                       check=False)
            except subprocess.TimeoutExpired:
                print(f"⚠️ FFmpeg timeout (>5min) para {os.path.basename(video_path)}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
            
            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, video_path)
                return True
            else:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
                
        except Exception as e:
            print(f"⚠️ Error incrustando metadatos en {os.path.basename(video_path)}: {e}")
            if os.path.exists(video_path + ".tmp.mp4"):
                os.remove(video_path + ".tmp.mp4")
            return False

if __name__ == "__main__":
    app = EmbedMetadataGUI()
    app.mainloop()