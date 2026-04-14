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
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                self.metadata_list = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar el archivo JSON:\n{e}")
            self.destroy()
            return

        # --- Sesión ---
        tk.Label(self, text="Sesión: ").pack(pady=5)
        self.session_option = tk.StringVar(value="last")
        tk.Radiobutton(self, text="Última sesión", variable=self.session_option, value="last").pack(anchor="w")
        tk.Radiobutton(self, text="Todas las sesiones", variable=self.session_option, value="all").pack(anchor="w")
        tk.Radiobutton(self, text="Sesión específica", variable=self.session_option, value="specific").pack(anchor="w")
        self.session_entry = tk.Entry(self)
        self.session_entry.pack(pady=2)
        self.session_entry.insert(0, "ID de sesión")

        # --- Extracción de filtros (Compatible con modelo nuevo) ---
        # Tags (Species)
        tags_set = set()
        for v in self.metadata_list:
            # Busca en 'tags' (legacy) o 'classification/species' (nuevo)
            species = v.get("classification", {}).get("species", []) or v.get("tags", [])
            tags_set.update(species)
        self.tags = sorted(list(tags_set))

        tk.Label(self, text="Seleccionar tags (especies): ").pack(pady=5)
        self.tag_vars = {}
        for tag in self.tags:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=tag, variable=var).pack(anchor="w")
            self.tag_vars[tag] = var

        # Operadores
        operators_set = set()
        for v in self.metadata_list:
            op = v.get("metadata", {}).get("operator", "") or v.get("operator", "")
            if op: operators_set.add(op)
        operators_list = sorted(list(operators_set))
        
        tk.Label(self, text="Seleccionar operadores: ").pack(pady=5)
        self.operator_vars = {}
        for op in operators_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=op, variable=var).pack(anchor="w")
            self.operator_vars[op] = var

        # Cámaras
        cameras_set = set()
        for v in self.metadata_list:
            cam = v.get("metadata", {}).get("camera", "") or v.get("camera", "")
            if cam: cameras_set.add(cam)
        cameras_list = sorted(list(cameras_set))

        tk.Label(self, text="Seleccionar cámaras: ").pack(pady=5)
        self.camera_vars = {}
        for cam in cameras_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=cam, variable=var).pack(anchor="w")
            self.camera_vars[cam] = var

        # Sitios
        sites_set = set()
        for v in self.metadata_list:
            site = v.get("metadata", {}).get("site", "") or v.get("site", "")
            if site: sites_set.add(site)
        sites_list = sorted(list(sites_set))

        tk.Label(self, text="Seleccionar sitios: ").pack(pady=5)
        self.site_vars = {}
        for site in sites_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=site, variable=var).pack(anchor="w")
            self.site_vars[site] = var

        # Comportamientos
        behaviors_set = set()
        for v in self.metadata_list:
            behs = v.get("classification", {}).get("behaviors", []) or v.get("behaviors", [])
            behaviors_set.update(behs)
        behaviors_list = sorted(list(behaviors_set))

        tk.Label(self, text="Seleccionar comportamientos: ").pack(pady=5)
        self.behavior_vars = {}
        for b in behaviors_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=b, variable=var).pack(anchor="w")
            self.behavior_vars[b] = var

        # --- Botones ---
        tk.Button(self, text="Preview", command=self.preview).pack(pady=10)
        tk.Button(self, text="Mover videos", command=self.move_videos).pack(pady=10)

        # Texto de preview
        self.preview_text = tk.Text(self, height=10)
        self.preview_text.pack(fill="both", expand=True)

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
            species = v.get("classification", {}).get("species", []) or v.get("tags", [])
            for t in species:
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
            # Leer tags (compatibilidad nueva y vieja)
            tags_list = v.get("classification", {}).get("species", []) or v.get("tags", [])
            
            # Leer ruta de origen (compatibilidad)
            src = v.get("video_path") or v.get("file", {}).get("video_path")
            if not src or not os.path.exists(src):
                continue

            # Extraer fecha del archivo (o usar recorded_at si está disponible)
            try:
                recorded = v.get("metadata", {}).get("recorded_at", "")
                if recorded:
                    dt = datetime.strptime(recorded, "%Y-%m-%d %H:%M:%S")
                    fecha = dt.strftime("%y%m%d")
                    hora = dt.strftime("%H%M%S")
                else:
                    ts = os.path.getmtime(src)
                    dt = datetime.fromtimestamp(ts)
                    fecha = dt.strftime("%y%m%d")
                    hora = dt.strftime("%H%M%S")
            except Exception:
                # Fallback por fecha de modificación
                ts = os.path.getmtime(src)
                dt = datetime.fromtimestamp(ts)
                fecha = dt.strftime("%y%m%d")
                hora = dt.strftime("%H%M%S")

            # Extraer metadatos (compatibilidad nueva y vieja)
            site = v.get("metadata", {}).get("site", "") or v.get("site", "UnknownSite")
            subsite = v.get("metadata", {}).get("subsite", "") or v.get("subsite", "UnknownSubsite")
            camera = v.get("metadata", {}).get("camera", "") or v.get("camera", "UnknownCamera")

            base_name = f"{site}_{subsite}_{fecha}_{hora}_{camera}{os.path.splitext(src)[1]}"

            if not tags_list:
                # Si no tiene tags, lo movemos a una carpeta "Sin_Especie"
                dest_folder = os.path.join(output_folder, "Sin_Especie")
                os.makedirs(dest_folder, exist_ok=True)
                dest_path = os.path.join(dest_folder, base_name)
                counter = 1
                while os.path.exists(dest_path):
                    base_no_ext = os.path.splitext(base_name)[0]
                    ext = os.path.splitext(base_name)[1]
                    dest_path = os.path.join(dest_folder, f"{base_no_ext}_{counter}{ext}")
                    counter += 1
                try:
                    shutil.copy2(src, dest_path)
                    moved_count += 1
                except Exception as e:
                    print(f"Error moviendo {src}: {e}")
            else:
                # Copiar a una carpeta por cada especie detectada
                for tag in tags_list:
                    dest_folder = os.path.join(output_folder, tag)
                    os.makedirs(dest_folder, exist_ok=True)
                    dest_path = os.path.join(dest_folder, base_name)
                    
                    # Manejo de nombres duplicados
                    if os.path.exists(dest_path):
                        base_no_ext = os.path.splitext(base_name)[0]
                        ext = os.path.splitext(base_name)[1]
                        counter = 1
                        while os.path.exists(dest_path):
                            dest_path = os.path.join(dest_folder, f"{base_no_ext}_{counter}{ext}")
                            counter += 1
                    
                    try:
                        shutil.copy2(src, dest_path)
                    except Exception as e:
                        print(f"Error moviendo {src} a {dest_folder}: {e}")
                
                moved_count += 1

        messagebox.showinfo("Éxito", f"Se procesaron/copiaron {moved_count} videos a las carpetas correspondientes.")

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
        # Intenta cargar el consolidado
        consolidated_path = os.path.join(output_folder, "consolidated", "all_sessions_metadata.json")
        if os.path.exists(consolidated_path):
            metadata_path = consolidated_path
        else:
            messagebox.showerror("Error", "No se encontró el archivo consolidado ni se especificó un archivo de metadatos.")
            return

    app = SortRenameAdvancedGUI(metadata_path)
    app.mainloop()