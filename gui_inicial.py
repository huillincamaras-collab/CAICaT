import os
import csv
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from procesamiento import (
    escanear_videos, wrapper, metadata_lock,
    obtener_fotos_con_timestamp, agrupar_en_rafagas, procesar_todas_las_rafagas
)
from gui_tagger import DynamicTagger
from config_utils import generate_session_id, load_config


def generate_deployment_id(location_id, location_name, camera_id, deployment_start):
    """Genera un deploymentID simple a partir de los campos disponibles."""
    parts = [p for p in [location_id, location_name, camera_id, deployment_start] if p]
    return "_".join(parts) if parts else "deployment_unknown"


class GUIInicial(tk.Tk):
    def __init__(self):
        super().__init__()

        # --- Cargar configuración ---
        self.config_data = load_config()
        gui_cfg = self.config_data.get("GUI_Inicial", {})

        # --- Parámetros de GUI ---
        self.title(gui_cfg.get("title", "Configuración inicial - Cámaras Trampa"))
        colors = gui_cfg.get("colors", {})
        fonts = gui_cfg.get("fonts", {})
        self.labels_cfg = gui_cfg.get("labels", {})
        self.buttons_cfg = gui_cfg.get("buttons", {})
        self.bg_color = colors.get("bg", "#f0f0f0")
        self.btn_bg = colors.get("button_bg", "#4CAF50")
        self.btn_fg = colors.get("button_fg", "white")
        self.font_default = tuple(fonts.get("default", ("Arial", 10)))
        self.configure(bg=self.bg_color)

        # --- Variables internas ---
        self.session_id = generate_session_id(self.config_data)
        self.input_folder = ""
        self.metadata_path = ""
        self.metadata_list = []
        self.camtrap_mode_var = tk.BooleanVar(value=False)
        self.deployments_csv_path = ""
        self.deployments_data = []

        # --- Construir UI ---
        self._build_ui()

    # -----------------------------------------------------------------------
    # Construcción de la interfaz
    # -----------------------------------------------------------------------
    def _build_ui(self):
        outer = tk.Frame(self, bg=self.bg_color)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.scroll_frame = tk.Frame(canvas, bg=self.bg_color)
        self._scroll_window = canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self._scroll_window, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        f = self.scroll_frame

        # ── TOGGLE MODERNO ─────────────────────────────────────────────
        self.switch_frame = tk.Frame(f, bg="#d0d0d0", height=38, relief="solid", bd=1)
        self.switch_frame.pack(pady=(10, 5), padx=20, fill="x")

        self.label_std = tk.Label(self.switch_frame, text="Modo Estándar", bg="#4CAF50", fg="white",
                                  font=self.font_default, cursor="hand2")
        self.label_sci = tk.Label(self.switch_frame, text="Modo Científico", bg="#d0d0d0", fg="#333333",
                                  font=self.font_default, cursor="hand2")
        self.label_std.pack(side="left", fill="both", expand=True)
        self.label_sci.pack(side="left", fill="both", expand=True)

        self.label_std.bind("<Button-1>", lambda e: self._set_mode(False))
        self.label_sci.bind("<Button-1>", lambda e: self._set_mode(True))
        self._update_switch_visual()

        # ── BLOQUE 1: Carpeta de videos ────────────────────────────────
        self.bloque1 = tk.LabelFrame(f, text="Archivos", bg=self.bg_color, font=self.font_default, padx=8, pady=6)
        self.bloque1.pack(fill="x", padx=10, pady=5)

        tk.Label(self.bloque1, text=self.labels_cfg.get("input_folder", "Carpeta de videos:"),
                 bg=self.bg_color, font=self.font_default).grid(row=0, column=0, sticky="e", pady=3)
        self.entry_input = tk.Entry(self.bloque1, width=38)
        self.entry_input.grid(row=0, column=1, padx=5, pady=3)
        tk.Button(self.bloque1, text=self.buttons_cfg.get("browse_input", "Examinar"),
                  command=self.select_input, bg=self.btn_bg, fg=self.btn_fg,
                  font=self.font_default).grid(row=0, column=2, padx=3)

        # ── BLOQUE 3: Deployment CSV (Crear pero NO empaquetar aún) ────
        self.bloque3 = tk.LabelFrame(f, text="Importar desde deployments.csv",
                                     bg=self.bg_color, font=self.font_default, padx=8, pady=6)
        
        tk.Label(self.bloque3, text=self.buttons_cfg.get("browse_deployments", "Archivo deployments.csv:"),
                 bg=self.bg_color, font=self.font_default).grid(row=0, column=0, sticky="e", pady=3)
        self.entry_deployments_csv = tk.Entry(self.bloque3, width=32)
        self.entry_deployments_csv.grid(row=0, column=1, padx=5, pady=3)
        tk.Button(self.bloque3, text="Seleccionar", command=self._browse_deployments_csv,
                  bg=self.btn_bg, fg=self.btn_fg, font=self.font_default).grid(row=0, column=2, padx=3)

        tk.Label(self.bloque3, text="Filtrar por sitio:", bg=self.bg_color, font=self.font_default).grid(row=1, column=0, sticky="e", pady=3)
        self.entry_filter_site = tk.Entry(self.bloque3, width=20)
        self.entry_filter_site.grid(row=1, column=1, padx=5, pady=3, sticky="w")
        self.entry_filter_site.bind("<KeyRelease>", self._filter_deployments)

        filter2_frame = tk.Frame(self.bloque3, bg=self.bg_color)
        filter2_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=4)
        tk.Label(filter2_frame, text="Mes:", bg=self.bg_color, font=self.font_default).pack(side="left", padx=(0,2))
        self.month_var = tk.StringVar(value="Todos")
        self.month_combo = ttk.Combobox(filter2_frame, textvariable=self.month_var, values=["Todos"] + [f"{i:02d}" for i in range(1, 13)], width=6, state="readonly")
        self.month_combo.pack(side="left", padx=2)
        self.month_var.trace_add("write", self._filter_deployments)

        tk.Label(filter2_frame, text="Año:", bg=self.bg_color, font=self.font_default).pack(side="left", padx=(10,2))
        self.year_var = tk.StringVar(value="Todos")
        self.year_combo = ttk.Combobox(filter2_frame, textvariable=self.year_var, values=["Todos"] + [str(y) for y in range(2015, 2035)], width=6, state="readonly")
        self.year_combo.pack(side="left", padx=2)
        self.year_var.trace_add("write", self._filter_deployments)

        tk.Label(self.bloque3, text="Deployment:", bg=self.bg_color, font=self.font_default).grid(row=3, column=0, sticky="ne", pady=3)
        self.deployment_listbox = tk.Listbox(self.bloque3, height=5, width=50, exportselection=False)
        self.deployment_listbox.grid(row=3, column=1, columnspan=2, padx=5, pady=3, sticky="w")
        self.deployment_listbox.bind("<<ListboxSelect>>", self._on_deployment_selected)

        scroll_lb = ttk.Scrollbar(self.bloque3, orient="vertical", command=self.deployment_listbox.yview)
        scroll_lb.grid(row=3, column=3, sticky="ns", pady=3)
        self.deployment_listbox.configure(yscrollcommand=scroll_lb.set)

        # ── BLOQUE 4: Campos deployment (Crear pero NO empaquetar aún) ─
        self.bloque4 = tk.LabelFrame(f, text="Datos del deployment",
                                     bg=self.bg_color, font=self.font_default, padx=8, pady=6)

        deployment_fields = [
            ("setupBy", "Instalado por:"), ("retrievedBy", "Retirado por:"),
            ("latitude", "Latitud:"), ("longitude", "Longitud:"),
            ("deploymentStart", "Inicio deployment\n(YYYY-MM-DD HH:MM):"),
            ("deploymentEnd", "Fin deployment\n(YYYY-MM-DD HH:MM):"),
            ("cameraHeight", "Altura cámara (m):"), ("cameraTilt", "Ángulo vertical (°):"),
            ("detectionDistance", "Distancia detección (m):"),
        ]
        self.deployment_entries = {}
        for row, (key, default_label) in enumerate(deployment_fields):
            label_text = self.labels_cfg.get(key, default_label)
            tk.Label(self.bloque4, text=label_text, bg=self.bg_color, font=self.font_default, justify="right").grid(
                row=row, column=0, sticky="e", pady=3, padx=(0, 5))
            e = tk.Entry(self.bloque4, width=30)
            e.grid(row=row, column=1, padx=5, pady=3, sticky="w")
            self.deployment_entries[key] = e

        self.timestamp_issues_var = tk.BooleanVar(value=False)
        self.bait_use_var = tk.BooleanVar(value=False)
        check_row = len(deployment_fields)
        tk.Checkbutton(self.bloque4, text=self.labels_cfg.get("timestampIssues", "Problemas en timestamps"),
                       variable=self.timestamp_issues_var, bg=self.bg_color, font=self.font_default
        ).grid(row=check_row, column=0, columnspan=2, sticky="w", pady=3)
        tk.Checkbutton(self.bloque4, text=self.labels_cfg.get("baitUse", "Uso de cebo"),
                       variable=self.bait_use_var, bg=self.bg_color, font=self.font_default
        ).grid(row=check_row + 1, column=0, columnspan=2, sticky="w", pady=3)

        # ── BLOQUE 2: Identificación (Siempre empaquetado AL FINAL) ────
        self.bloque2 = tk.LabelFrame(f, text="Identificación", bg=self.bg_color, font=self.font_default, padx=8, pady=6)
        self.bloque2.pack(fill="x", padx=10, pady=5)

        basic_fields = [
            ("locationID", "Sitio:"), ("locationName", "Subsitio:"),
            ("cameraID", "Cámara:"), ("classifiedBy", "Operador:"),
        ]
        self.basic_entries = {}
        for row, (key, default_label) in enumerate(basic_fields):
            label_text = self.labels_cfg.get(key, default_label)
            tk.Label(self.bloque2, text=label_text, bg=self.bg_color, font=self.font_default).grid(row=row, column=0, sticky="e", pady=3)
            e = tk.Entry(self.bloque2, width=38)
            e.grid(row=row, column=1, padx=5, pady=3, sticky="w")
            self.basic_entries[key] = e

        # ── Botón Iniciar ──────────────────────────────────────────────
        self.start_btn = tk.Button(f, text=self.buttons_cfg.get("start", "Iniciar"), command=self.start,
                  bg=self.btn_bg, fg=self.btn_fg, font=self.font_default, width=20, height=2)
        self.start_btn.pack(pady=12)

        self.geometry("520x380")
    # -----------------------------------------------------------------------
    # Toggle modo estándar / científico
    # -----------------------------------------------------------------------
    def _set_mode(self, is_scientific):
        self.camtrap_mode_var.set(is_scientific)
        self._update_switch_visual()
        
        if is_scientific:
            # Empacar justo ANTES de bloque2 para que quede: Carpeta → Deployments → Identificación
            self.bloque3.pack(fill="x", padx=10, pady=5, before=self.bloque2)
            self.bloque4.pack(fill="x", padx=10, pady=5, before=self.bloque2)
            self.geometry("520x820")
        else:
            self.bloque3.pack_forget()
            self.bloque4.pack_forget()
            self.geometry("520x380")

    def _update_switch_visual(self):
        is_sci = self.camtrap_mode_var.get()
        # Estándar activo / Científico inactivo
        self.label_std.config(bg="#4CAF50", fg="white") if not is_sci else self.label_std.config(bg="#e0e0e0", fg="#333333")
        # Científico activo / Estándar inactivo
        self.label_sci.config(bg="#9C27B0", fg="white") if is_sci else self.label_sci.config(bg="#e0e0e0", fg="#333333")

    def _get_start_button(self):
        for widget in self.scroll_frame.winfo_children():
            if isinstance(widget, tk.Button) and widget.cget("text") in (
                    self.buttons_cfg.get("start", "Iniciar"), "Iniciar"):
                return widget
        return None

    # -----------------------------------------------------------------------
    # Selección de carpeta de videos
    # -----------------------------------------------------------------------
    def select_input(self):
        folder = filedialog.askdirectory(parent=self, title="Seleccione carpeta de entrada")
        if folder:
            self.input_folder = folder
            self.entry_input.delete(0, tk.END)
            self.entry_input.insert(0, folder)
            threading.Thread(target=self._start_processing, daemon=True).start()

    # -----------------------------------------------------------------------
    # Deployments CSV
    # -----------------------------------------------------------------------
    def _browse_deployments_csv(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleccione deployments.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        self.deployments_csv_path = path
        self.entry_deployments_csv.delete(0, tk.END)
        self.entry_deployments_csv.insert(0, path)
        self._load_deployments_csv(path)

    def _load_deployments_csv(self, path):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.deployments_data = [row for row in reader]
            self._populate_deployment_listbox(self.deployments_data)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer deployments.csv:\n{e}")
            self.deployments_data = []

    def _filter_deployments(self, event=None, *args):
        site_filter = self.entry_filter_site.get().strip().lower()
        month_filter = self.month_var.get()
        year_filter = self.year_var.get()

        filtered = self.deployments_data
        if site_filter:
            filtered = [d for d in filtered if site_filter in d.get("locationID", "").lower()
                        or site_filter in d.get("locationName", "").lower()]
        if month_filter != "Todos":
            # Busca coincidencia exacta de mes en YYYY-MM-DD
            filtered = [d for d in filtered if f"-{month_filter}-" in d.get("deploymentStart", "")]
        if year_filter != "Todos":
            filtered = [d for d in filtered if d.get("deploymentStart", "").startswith(year_filter)]

        self._populate_deployment_listbox(filtered)

    def _populate_deployment_listbox(self, deployments):
        self.deployment_listbox.delete(0, tk.END)
        self._filtered_deployments = deployments
        for d in deployments:
            dep_id = d.get("deploymentID", "")
            loc = d.get("locationID", "")
            start = d.get("deploymentStart", "")
            label = f"{dep_id}  |  {loc}  |  {start}"
            self.deployment_listbox.insert(tk.END, label)

    def _on_deployment_selected(self, event=None):
        sel = self.deployment_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        deployments = getattr(self, "_filtered_deployments", self.deployments_data)
        if idx >= len(deployments):
            return
        d = deployments[idx]

        mapping_basic = {
            "locationID":   "locationID",
            "locationName": "locationName",
            "cameraID":     "cameraID",
        }
        for entry_key, csv_key in mapping_basic.items():
            val = d.get(csv_key, "")
            self.basic_entries[entry_key].delete(0, tk.END)
            self.basic_entries[entry_key].insert(0, val)

        mapping_dep = {
            "setupBy":           "setupBy",
            "retrievedBy":       "retrievedBy",
            "latitude":          "latitude",
            "longitude":         "longitude",
            "deploymentStart":   "deploymentStart",
            "deploymentEnd":     "deploymentEnd",
            "cameraHeight":      "cameraHeight",
            "cameraTilt":        "cameraTilt",
            "detectionDistance": "detectionDistance",
        }
        for entry_key, csv_key in mapping_dep.items():
            val = d.get(csv_key, "")
            self.deployment_entries[entry_key].delete(0, tk.END)
            self.deployment_entries[entry_key].insert(0, val)

        def _to_bool(val):
            return str(val).strip().lower() in ("true", "1", "yes", "sí", "si")

        self.timestamp_issues_var.set(_to_bool(d.get("timestampIssues", False)))
        self.bait_use_var.set(_to_bool(d.get("baitUse", False)))

    # -----------------------------------------------------------------------
    # Procesamiento en segundo plano
    # -----------------------------------------------------------------------
    def _start_processing(self):
        output_folder = self.config_data["General"]["output_folder"]

        # Crear carpeta de sesión
        session_folder = os.path.join(output_folder, "sessions", self.session_id)
        os.makedirs(session_folder, exist_ok=True)
        self.metadata_path = os.path.join(session_folder, "metadata.json")

        # Escanear como videos (incluye modo híbrido)
        self.metadata_list = escanear_videos(self.input_folder, output_folder)
        self._save_metadata_temporal()

        # Detectar si es modo fotos puras
        if not self.metadata_list:
            img_exts = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
            has_photos = any(
                os.path.isfile(os.path.join(self.input_folder, f)) and
                os.path.splitext(f)[1] in img_exts
                for f in os.listdir(self.input_folder)
            )
            if has_photos:
                self.metadata_list = []
                self._save_metadata_temporal()
                threading.Thread(
                    target=self._detectar_fotos_puras_bg,
                    args=(output_folder,),
                    daemon=True
                ).start()
                return

        def process_first_videos():
            first_n = min(3, len(self.metadata_list))
            for i in range(first_n):
                res = wrapper((self.metadata_list[i], output_folder))
                self.metadata_list[i] = res
                self._save_metadata_temporal()

            def process_rest():
                from multiprocessing import Pool, cpu_count
                rest = self.metadata_list[first_n:]
                if not rest:
                    return
                args_list = [(m, output_folder) for m in rest]
                num_proc = max(1, cpu_count() - 1)
                if num_proc > 1:
                    with Pool(num_proc) as pool:
                        for res in pool.imap_unordered(wrapper, args_list):
                            for idx, v in enumerate(self.metadata_list):
                                if v.get("filePath", v.get("video_path")) == res.get("filePath", res.get("video_path")):
                                    self.metadata_list[idx] = res
                            self._save_metadata_temporal()
                else:
                    for args in args_list:
                        res = wrapper(args)
                        for idx, v in enumerate(self.metadata_list):
                            if v.get("filePath", v.get("video_path")) == res.get("filePath", res.get("video_path")):
                                self.metadata_list[idx] = res
                        self._save_metadata_temporal()

            threading.Thread(target=process_rest, daemon=True).start()

        threading.Thread(target=process_first_videos, daemon=True).start()

    def _detectar_fotos_puras_bg(self, output_folder):
        try:
            fotos_con_ts = obtener_fotos_con_timestamp(self.input_folder)
            if not fotos_con_ts:
                return
            photo_groups = agrupar_en_rafagas(fotos_con_ts, umbral_seg=2.0)
            total = len(fotos_con_ts)
            n_grupos = len(photo_groups)
            avg_por_grupo = total / n_grupos if n_grupos else 1.0
            self.after(0, lambda: self._mostrar_dialogo_rafagas(fotos_con_ts, avg_por_grupo))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"No se pudieron analizar las fotos:\n{e}"))

    def _mostrar_dialogo_rafagas(self, fotos_con_ts, avg_estimado):
        dialog = tk.Toplevel(self)
        dialog.title("Configuración de ráfagas fotográficas")
        dialog.geometry("400x260")
        dialog.transient(self)
        dialog.grab_set()
        dialog.focus_set()

        total = len(fotos_con_ts)
        n_estimado = max(1, round(total / max(1, avg_estimado)))

        tk.Label(dialog, text=f"Fotos detectadas: {total}", font=("Arial", 10)).pack(pady=5)
        tk.Label(dialog, text=f"Ráfagas estimadas: {n_estimado}", font=("Arial", 10)).pack(pady=2)
        tk.Label(dialog, text=f"Promedio por ráfaga: {avg_estimado:.1f}", font=("Arial", 10)).pack(pady=2)
        tk.Label(dialog, text="Ajuste el número de fotos por activación:",
                 font=("Arial", 10, "bold")).pack(pady=(10, 5))

        burst_spin = tk.Spinbox(dialog, from_=1, to=total, width=8)
        burst_spin.delete(0, "end")
        burst_spin.insert(0, str(max(1, round(avg_estimado))))
        burst_spin.pack(pady=5)

        tk.Label(dialog, text="Nota: se reagruparán las fotos\nsegún este valor.",
                 font=("Arial", 9), fg="gray").pack(pady=5)

        def confirmar():
            try:
                burst_size = int(burst_spin.get())
            except Exception:
                burst_size = 1
            if burst_size < 1:
                burst_size = 1
            total_fotos = len(fotos_con_ts)
            resto = total_fotos % burst_size
            if resto != 0:
                msg = (f"Advertencia: {total_fotos} fotos no son múltiplo de {burst_size}.\n"
                       f"La última ráfaga tendrá {resto} fotos.\n\n¿Desea continuar?")
                if not messagebox.askyesno("Ráfaga incompleta", msg, parent=dialog):
                    return
            dialog.destroy()
            threading.Thread(
                target=self._procesar_fotos_con_parametro,
                args=(fotos_con_ts, burst_size, self.config_data["General"]["output_folder"]),
                daemon=True
            ).start()

        def cancelar():
            dialog.destroy()

        tk.Button(dialog, text="Aceptar", command=confirmar, bg="#4CAF50", fg="white").pack(pady=5)
        tk.Button(dialog, text="Cancelar", command=cancelar).pack()

    def _procesar_fotos_con_parametro(self, fotos_con_ts, burst_size, output_folder):
        try:
            photo_groups = []
            for i in range(0, len(fotos_con_ts), burst_size):
                photo_groups.append(fotos_con_ts[i:i + burst_size])
            metadata_list = procesar_todas_las_rafagas(photo_groups, output_folder)
            self.after(0, lambda: self._actualizar_metadata_fotos(metadata_list))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Fallo al procesar fotos:\n{e}"))

    def _actualizar_metadata_fotos(self, metadata_list):
        self.metadata_list = metadata_list
        self._save_metadata_temporal()

    # -----------------------------------------------------------------------
    # Iniciar sesión de etiquetado
    # -----------------------------------------------------------------------
    def start(self):
        if not self.input_folder:
            messagebox.showerror("Error", "Debe seleccionar la carpeta de videos.")
            return

        location_id = self.basic_entries["locationID"].get().strip()
        location_name = self.basic_entries["locationName"].get().strip()
        camera_id = self.basic_entries["cameraID"].get().strip()
        classified_by = self.basic_entries["classifiedBy"].get().strip()

        deployment_data = {}
        if self.camtrap_mode_var.get():
            for key, entry in self.deployment_entries.items():
                deployment_data[key] = entry.get().strip()
            deployment_data["timestampIssues"] = self.timestamp_issues_var.get()
            deployment_data["baitUse"] = self.bait_use_var.get()

        deployment_start = deployment_data.get("deploymentStart", "")
        deployment_id = generate_deployment_id(location_id, location_name, camera_id, deployment_start)

        for entry in self.metadata_list:
            # 1. Eliminar claves planas antiguas para evitar duplicados en el JSON
            for k in ["locationID", "locationName", "cameraID", "classifiedBy",
                      "site", "subsite", "camera", "operator", "session_id", "camtrap_db_session"]:
                entry.pop(k, None)

            # 2. Inyectar estructura unificada (exactamente como la esperan tagger y export)
            entry["classification"] = {
                "species": [],
                "counts": {},
                "behaviors": []
            }
            entry["metadata"] = {
                "site": location_id,
                "subsite": location_name,
                "camera": camera_id,
                "operator": classified_by,
                "recorded_at": entry.get("recorded_at", ""),
                "notes": ""
            }
            entry["ui"] = {
                "embed_metadata": False,
                "xlsx": False,
                "is_favorite": False,
                "is_excluded": False
            }
            entry["session"] = {
                "session_id": self.session_id,
                "camtrap_db_session": self.camtrap_mode_var.get(),
                "deployment_id": deployment_id
            }

            if self.camtrap_mode_var.get():
                entry["deployment"] = deployment_data

        self._save_metadata_temporal()
        self.after(100, self.open_tagger_delayed)

    def open_tagger_delayed(self):
        self.destroy()
        app = DynamicTagger(
            metadata_path=self.metadata_path, 
            session_id=self.session_id,
            scientific_mode=self.camtrap_mode_var.get()  # 🔹 CRÍTICO: Pasa el estado del toggle
        )
        app.mainloop()

    
    
    def _save_metadata_temporal(self):
        if not self.metadata_path:
            return
        with metadata_lock:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata_list, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    gui = GUIInicial()
    gui.mainloop()
