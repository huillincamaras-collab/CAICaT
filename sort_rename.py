import os
import shutil
import tkinter as tk
from tkinter import messagebox
import json
from datetime import datetime
from config_utils import load_config

class SortRenameAdvancedGUI(tk.Tk):
    def __init__(self, metadata_path):
        super().__init__()
        self.title("Sort & Rename Avanzado - Cámaras Trampa")
        self.geometry("600x700")

        self.metadata_path = metadata_path
        with open(metadata_path, "r") as f:
            self.metadata_list = json.load(f)

        # --- Sesión ---
        tk.Label(self, text="Sesión:").pack(pady=5)
        self.session_option = tk.StringVar(value="last")
        tk.Radiobutton(self, text="Última sesión", variable=self.session_option, value="last").pack(anchor="w")
        tk.Radiobutton(self, text="Todas las sesiones", variable=self.session_option, value="all").pack(anchor="w")
        tk.Radiobutton(self, text="Sesión específica", variable=self.session_option, value="specific").pack(anchor="w")
        self.session_entry = tk.Entry(self)
        self.session_entry.pack(pady=2)
        self.session_entry.insert(0, "ID de sesión")

        # --- Tags ---
        tags_set = set()
        for v in self.metadata_list:
            tags_set.update(v.get("tags", []))
        self.tags = sorted(tags_set)

        tk.Label(self, text="Seleccionar tags (especies):").pack(pady=5)
        self.tag_vars = {}
        for tag in self.tags:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=tag, variable=var).pack(anchor="w")
            self.tag_vars[tag] = var

        # --- Operadores ---
        operators_set = sorted({v.get("operator", "") for v in self.metadata_list if v.get("operator")})
        tk.Label(self, text="Seleccionar operadores:").pack(pady=5)
        self.operator_vars = {}
        for op in operators_set:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=op, variable=var).pack(anchor="w")
            self.operator_vars[op] = var

        # --- Cámaras ---
        cameras_set = sorted({v.get("camera", "") for v in self.metadata_list if v.get("camera")})
        tk.Label(self, text="Seleccionar cámaras:").pack(pady=5)
        self.camera_vars = {}
        for cam in cameras_set:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=cam, variable=var).pack(anchor="w")
            self.camera_vars[cam] = var

        # --- Sitios ---
        sites_set = sorted({v.get("site", "") for v in self.metadata_list if v.get("site")})
        tk.Label(self, text="Seleccionar sitios:").pack(pady=5)
        self.site_vars = {}
        for site in sites_set:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=site, variable=var).pack(anchor="w")
            self.site_vars[site] = var

        # --- Comportamientos ---
        behaviors_set = sorted({b for v in self.metadata_list for b in v.get("behaviors", []) if b})
        tk.Label(self, text="Seleccionar comportamientos:").pack(pady=5)
        self.behavior_vars = {}
        for b in behaviors_set:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=b, variable=var).pack(anchor="w")
            self.behavior_vars[b] = var

        # --- Botones ---
        tk.Button(self, text="Preview", command=self.preview).pack(pady=10)
        tk.Button(self, text="Mover videos", command=self.move_videos).pack(pady=10)

        # Texto de preview
        self.preview_text = tk.Text(self, height=10)
        self.preview_text.pack(fill="both", expand=True)

# filter videos
    def filter_videos(self):
        # Recopilar selecciones del usuario
        selected_tags = [t for t, var in self.tag_vars.items() if var.get()]
        selected_ops = [o for o, var in self.operator_vars.items() if var.get()]
        selected_cams = [c for c, var in self.camera_vars.items() if var.get()]
        selected_sites = [s for s, var in self.site_vars.items() if var.get()]
        selected_behaviors = [b for b, var in self.behavior_vars.items() if var.get()]

        # Determinar filtro de sesión
        session_opt = self.session_option.get()
        if session_opt == "last":
            session_filter = "last"
        elif session_opt == "specific":
            session_id = self.session_entry.get().strip()
            session_filter = f"specific:{session_id}" if session_id else "all"
        else:
            session_filter = "all"

        # Aplicar filtrado centralizado
        from filter_utils import filter_videos
        return filter_videos(
            self.metadata_list,
            session_filter=session_filter,
            tags=selected_tags or None,
            operators=selected_ops or None,
            cameras=selected_cams or None,
            sites=selected_sites or None,
            behaviors=selected_behaviors or None
        )

    def preview(self):
        filtered = self.filter_videos()
        tag_count = {}
        for v in filtered:
            for t in v.get("tags", []):
                if t not in tag_count:
                    tag_count[t] = 0
                tag_count[t] += 1
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(tk.END, f"Se van a mover {len(filtered)} videos.\n")
        for t, c in tag_count.items():
            self.preview_text.insert(tk.END, f"Tag '{t}': {c} videos\n")

    def move_videos(self):
        filtered = self.filter_videos()
        if not filtered:
            messagebox.showerror("Error", "No hay videos que cumplan los filtros seleccionados.")
            return

        confirm = messagebox.askyesno("Confirmar", f"Se van a mover {len(filtered)} videos. ¿Desea continuar?")
        if not confirm:
            return

        output_folder = load_config()['General']['output_folder']
        moved_count = 0
        for v in filtered:
            tags_list = v.get("tags", [])
            src = v.get("video_path")
            if not os.path.exists(src):
                continue

            ts = os.path.getmtime(src)
            dt = datetime.fromtimestamp(ts)
            fecha = dt.strftime("%y%m%d")
            hora = dt.strftime("%H%M%S")

            site = v.get("site", "UnknownSite")
            subsite = v.get("subsite", "UnknownSubsite")
            camera = v.get("camera", "UnknownCamera")
            base_name = f"{site}_{subsite}_{fecha}_{hora}_{camera}{os.path.splitext(src)[1]}"

            for tag in tags_list:
                dest_folder = os.path.join(output_folder, tag)
                os.makedirs(dest_folder, exist_ok=True)
                dest_path = os.path.join(dest_folder, base_name)
                counter = 1
                temp_dest_path = dest_path
                while os.path.exists(temp_dest_path):
                    temp_dest_path = os.path.join(dest_folder, f"{os.path.splitext(base_name)[0]}_{counter}{os.path.splitext(base_name)[1]}")
                    counter += 1
                shutil.copy2(src, temp_dest_path)
            moved_count += 1

        messagebox.showinfo("Éxito", f"Se procesaron {moved_count} videos.")

# -------------------------------
# Lanzador
# -------------------------------
def run_sort_rename_advanced(metadata_path=None):
    """
    Lanza la GUI de Sort & Rename.
    Si no se proporciona metadata_path, usa el archivo consolidado.
    """
    if metadata_path is None:
        from config_utils import load_config
        config = load_config()
        output_folder = config["General"]["output_folder"]
        metadata_path = os.path.join(output_folder, "consolidated", "all_sessions_metadata.json")
    
    app = SortRenameAdvancedGUI(metadata_path)
    app.mainloop()
