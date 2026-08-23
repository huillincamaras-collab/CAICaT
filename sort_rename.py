import os
import shutil
import tkinter as tk
from tkinter import messagebox, ttk
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
        
        # --- Extraer sesiones únicas y crear mapeo legible ---
        self.sessions_map = {}  # {session_id_readable: session_id_raw}
        sessions_set = set()
        
        for v in self.metadata_list:
            session_id = v.get("session", {}).get("session_id", "")
            if session_id and session_id not in sessions_set:
                sessions_set.add(session_id)
                # Crear versión legible
                readable = self._format_session_id_readable(session_id)
                self.sessions_map[readable] = session_id
        
        # Ordenar sesiones por fecha (más reciente primero)
        sorted_sessions = sorted(
            self.sessions_map.keys(),
            key=lambda x: self.sessions_map[x],
            reverse=True
        )
        
        # --- Sesión ---
        tk.Label(self, text="Sesión: ").pack(pady=5)
        self.session_option = tk.StringVar(value="last")
        tk.Radiobutton(self, text="Última sesión", variable=self.session_option, 
                      value="last", command=self._on_session_change).pack(anchor="w")
        tk.Radiobutton(self, text="Todas las sesiones", variable=self.session_option, 
                      value="all", command=self._on_session_change).pack(anchor="w")
        tk.Radiobutton(self, text="Sesión específica", variable=self.session_option, 
                      value="specific", command=self._on_session_change).pack(anchor="w")
        
        # Combobox para seleccionar sesión específica
        self.session_combo = ttk.Combobox(self, state="disabled", width=40)
        self.session_combo['values'] = sorted_sessions
        if sorted_sessions:
            self.session_combo.set(sorted_sessions[0])  # Seleccionar la más reciente
        self.session_combo.pack(pady=2)
        self.session_combo.bind("<<ComboboxSelected>>", lambda e: self._update_preview())
        
        # --- Extracción de filtros (Compatible con modelo nuevo) ---
        # Tags (Species)
        tags_set = set()
        for v in self.metadata_list:
            species = v.get("classification", {}).get("species", []) or v.get("tags", [])
            tags_set.update(species)
        self.tags = sorted(list(tags_set))
        
        tag_header = tk.Frame(self)
        tag_header.pack(fill="x", pady=5)
        tk.Label(tag_header, text="Seleccionar tags (especies): ").pack(side="left")
        btn_frame = tk.Frame(tag_header)
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="✓ Todo", command=lambda: self._select_all(self.tag_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✗ Nada", command=lambda: self._deselect_all(self.tag_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        
        self.tag_vars = {}
        for tag in self.tags:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=tag, variable=var, command=self._update_preview).pack(anchor="w")
            self.tag_vars[tag] = var
        
        # Operadores
        operators_set = set()
        for v in self.metadata_list:
            op = v.get("metadata", {}).get("operator", "") or v.get("operator", "")
            if op: operators_set.add(op)
        operators_list = sorted(list(operators_set))
        
        op_header = tk.Frame(self)
        op_header.pack(fill="x", pady=5)
        tk.Label(op_header, text="Seleccionar operadores: ").pack(side="left")
        btn_frame = tk.Frame(op_header)
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="✓ Todo", command=lambda: self._select_all(self.operator_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✗ Nada", command=lambda: self._deselect_all(self.operator_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        
        self.operator_vars = {}
        for op in operators_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=op, variable=var, command=self._update_preview).pack(anchor="w")
            self.operator_vars[op] = var
        
        # Cámaras
        cameras_set = set()
        for v in self.metadata_list:
            cam = v.get("metadata", {}).get("camera", "") or v.get("camera", "")
            if cam: cameras_set.add(cam)
        cameras_list = sorted(list(cameras_set))
        
        cam_header = tk.Frame(self)
        cam_header.pack(fill="x", pady=5)
        tk.Label(cam_header, text="Seleccionar cámaras: ").pack(side="left")
        btn_frame = tk.Frame(cam_header)
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="✓ Todo", command=lambda: self._select_all(self.camera_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✗ Nada", command=lambda: self._deselect_all(self.camera_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        
        self.camera_vars = {}
        for cam in cameras_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=cam, variable=var, command=self._update_preview).pack(anchor="w")
            self.camera_vars[cam] = var
        
        # Sitios
        sites_set = set()
        for v in self.metadata_list:
            site = v.get("metadata", {}).get("site", "") or v.get("site", "")
            if site: sites_set.add(site)
        sites_list = sorted(list(sites_set))
        
        site_header = tk.Frame(self)
        site_header.pack(fill="x", pady=5)
        tk.Label(site_header, text="Seleccionar sitios: ").pack(side="left")
        btn_frame = tk.Frame(site_header)
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="✓ Todo", command=lambda: self._select_all(self.site_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✗ Nada", command=lambda: self._deselect_all(self.site_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        
        self.site_vars = {}
        for site in sites_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=site, variable=var, command=self._update_preview).pack(anchor="w")
            self.site_vars[site] = var
        
        # Comportamientos
        behaviors_set = set()
        for v in self.metadata_list:
            behs = v.get("classification", {}).get("behaviors", []) or v.get("behaviors", [])
            behaviors_set.update(behs)
        behaviors_list = sorted(list(behaviors_set))
        
        beh_header = tk.Frame(self)
        beh_header.pack(fill="x", pady=5)
        tk.Label(beh_header, text="Seleccionar comportamientos: ").pack(side="left")
        btn_frame = tk.Frame(beh_header)
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="✓ Todo", command=lambda: self._select_all(self.behavior_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✗ Nada", command=lambda: self._deselect_all(self.behavior_vars), 
                 width=6, font=("Arial", 8)).pack(side="left", padx=2)
        
        self.behavior_vars = {}
        for b in behaviors_list:
            var = tk.BooleanVar()
            tk.Checkbutton(self, text=b, variable=var, command=self._update_preview).pack(anchor="w")
            self.behavior_vars[b] = var
        
        # --- Botón Mover videos ---
        tk.Button(self, text="Mover videos", command=self.move_videos).pack(pady=10)
        
        # Texto de preview (ahora se actualiza automáticamente)
        self.preview_text = tk.Text(self, height=10)
        self.preview_text.pack(fill="both", expand=True)
        
        # Inicializar estado del combobox y preview
        self._on_session_change()
        self._update_preview()
    
    def _format_session_id_readable(self, session_id):
        """
        Convierte session_id técnico a formato legible.
        Ejemplo: '260821143022ABCDEF' -> '2026-08-21 14:30:22 (PC: ABCDEF)'
        """
        if not session_id or len(session_id) < 18:
            return session_id  # No se puede parsear
        
        try:
            # Extraer componentes: YYMMDD (6) + HHMMSS (6) + PC_ID (6)
            date_part = session_id[:6]   # YYMMDD
            time_part = session_id[6:12] # HHMMSS
            pc_id = session_id[12:18]    # Primeros 6 chars del PC ID
            
            # Parsear fecha
            year = "20" + date_part[:2]  # Asumimos siglo 2000
            month = date_part[2:4]
            day = date_part[4:6]
            
            # Parsear hora
            hour = time_part[:2]
            minute = time_part[2:4]
            second = time_part[4:6]
            
            return f"{year}-{month}-{day} {hour}:{minute}:{second} (PC: {pc_id})"
        except Exception:
            return session_id  # Fallback al ID original si hay error
    
    def _on_session_change(self):
        """Habilita/deshabilita el combobox según la opción seleccionada y actualiza preview."""
        if self.session_option.get() == "specific":
            self.session_combo.config(state="readonly")
        else:
            self.session_combo.config(state="disabled")
        self._update_preview()
    
    def _select_all(self, var_dict):
        """Selecciona todos los checkboxes del diccionario proporcionado."""
        for var in var_dict.values():
            var.set(True)
        self._update_preview()
    
    def _deselect_all(self, var_dict):
        """Deselecciona todos los checkboxes del diccionario proporcionado."""
        for var in var_dict.values():
            var.set(False)
        self._update_preview()
    
    def _update_preview(self):
        """Actualiza automáticamente el resumen de videos a mover."""
        try:
            filtered = self.filter_videos()
            tag_count = {}
            for v in filtered:
                species = v.get("classification", {}).get("species", []) or v.get("tags", [])
                for t in species:
                    if t not in tag_count:
                        tag_count[t] = 0
                    tag_count[t] += 1
            
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, f"📊 Resumen actual:\n")
            self.preview_text.insert(tk.END, f"Se van a mover {len(filtered)} videos.\n\n")
            
            if tag_count:
                self.preview_text.insert(tk.END, f"Desglose por especie:\n")
                for t, c in sorted(tag_count.items(), key=lambda x: x[1], reverse=True):
                    self.preview_text.insert(tk.END, f"  • {t}: {c} videos\n")
            else:
                self.preview_text.insert(tk.END, f"(Sin especies seleccionadas o sin videos que coincidan)\n")
        except Exception as e:
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, f"Error al actualizar preview: {e}\n")
    
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
            # Obtener session_id legible seleccionado y mapear al ID técnico
            readable_session = self.session_combo.get()
            session_id = self.sessions_map.get(readable_session, "")
            session_filter = f"specific:{session_id}" if session_id else "all"
        else:
            session_filter = "all"
        
        # Aplicar filtrado centralizado
        from export_utils import filter_videos
        return filter_videos(
            self.metadata_list,
            session_filter=session_filter,
            tags=selected_tags or None,
            operators=selected_ops or None,
            cameras=selected_cams or None,
            sites=selected_sites or None,
            behaviors=selected_behaviors or None
        )
    
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
            src = v.get("file", {}).get("video_path") or v.get("video_path")
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