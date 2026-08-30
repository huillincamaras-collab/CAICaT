import os
import csv
import json
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from procesamiento import (
    escanear_videos, wrapper, metadata_lock, last_scan_stats,
    obtener_fotos_con_timestamp, agrupar_en_rafagas, procesar_todas_las_rafagas
)
from procesamiento_legacy import (
    escanear_videos_legacy, procesar_lote_legacy
)
from config_utils import generate_session_id, load_config


def generate_deployment_id(location_id, location_name, camera_id, deployment_start):
    """Genera un deploymentID simple a partir de los campos disponibles."""
    parts = [p for p in [location_id, location_name, camera_id, deployment_start] if p]
    return "_".join(parts) if parts else "deployment_unknown"


class GUIInicial(tk.Tk):
    def __init__(self):
        super().__init__()

        self.config_data = load_config()
        gui_cfg = self.config_data.get("GUI_Inicial", {})

        self.title(gui_cfg.get("title", "Configuración inicial - Cámaras Trampa"))
        colors = gui_cfg.get("colors", {})
        fonts = gui_cfg.get("fonts", {})
        self.labels_cfg = gui_cfg.get("labels", {})
        self.buttons_cfg = gui_cfg.get("buttons", {})
        self.bg_color = colors.get("bg", "#f0f0f0")
        self.btn_bg = colors.get("button_bg", "#4CAF50")
        self.btn_fg = colors.get("button_fg", "#111111")
        self.font_default = tuple(fonts.get("default", ("Arial", 10)))
        self.configure(bg=self.bg_color)

        self.session_id = generate_session_id(self.config_data)
        self.input_folder = ""
        self.metadata_path = ""
        self.metadata_list = []
        self.camtrap_mode_var = tk.BooleanVar(value=False)
        self.legacy_mode_var = tk.BooleanVar(value=False)
        self.deployments_csv_path = ""
        self.deployments_data = []
        self._legacy_processing_done = False

        self._build_ui()

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

        self.switch_frame = tk.Frame(f, bg="#d0d0d0", height=38, relief="solid", bd=1)
        self.switch_frame.pack(pady=(10, 5), padx=20, fill="x")

        self.label_std = tk.Label(self.switch_frame, text="Modo Básico", bg="#4CAF50", fg="#111111",
                                  font=self.font_default, cursor="hand2")
        self.label_sci = tk.Label(self.switch_frame, text="Modo Científico", bg="#d0d0d0", fg="#333333",
                                  font=self.font_default, cursor="hand2")
        self.label_std.pack(side="left", fill="both", expand=True)
        self.label_sci.pack(side="left", fill="both", expand=True)

        self.label_std.bind("<Button-1>", lambda e: self._set_mode(False))
        self.label_sci.bind("<Button-1>", lambda e: self._set_mode(True))

        self._update_switch_visual()

        legacy_frame = tk.LabelFrame(f, text="Modo de Procesamiento", bg=self.bg_color, font=self.font_default, padx=8, pady=6)
        legacy_frame.pack(fill="x", padx=10, pady=5)

        tk.Checkbutton(
            legacy_frame,
            text="🐌 Modo Legacy (PCs lentas - procesamiento secuencial)",
            variable=self.legacy_mode_var,
            bg=self.bg_color,
            font=self.font_default
        ).pack(anchor="w", pady=3, padx=5)

        self.bloque1 = tk.LabelFrame(f, text="Archivos", bg=self.bg_color, font=self.font_default, padx=8, pady=6)
        self.bloque1.pack(fill="x", padx=10, pady=5)

        tk.Label(self.bloque1, text=self.labels_cfg.get("input_folder", "Carpeta de videos: "),
                 bg=self.bg_color, font=self.font_default).grid(row=0, column=0, sticky="e", pady=3)

        self.entry_input = tk.Entry(self.bloque1, width=38)
        self.entry_input.grid(row=0, column=1, padx=5, pady=3)

        tk.Button(self.bloque1, text=self.buttons_cfg.get("browse_input", "Examinar"),
                  command=self.select_input, bg=self.btn_bg, fg="#111111",
                  font=self.font_default).grid(row=0, column=2, padx=3)

        self.bloque3 = tk.LabelFrame(f, text="Importar desde deployments.csv",
                                     bg=self.bg_color, font=self.font_default, padx=8, pady=6)

        tk.Label(self.bloque3, text=self.buttons_cfg.get("browse_deployments", "Archivo deployments.csv: "),
                 bg=self.bg_color, font=self.font_default).grid(row=0, column=0, sticky="e", pady=3)

        self.entry_deployments_csv = tk.Entry(self.bloque3, width=32)
        self.entry_deployments_csv.grid(row=0, column=1, padx=5, pady=3)

        tk.Button(self.bloque3, text="Seleccionar", command=self._browse_deployments_csv,
                  bg=self.btn_bg, fg="#111111", font=self.font_default).grid(row=0, column=2, padx=3)

        tk.Label(self.bloque3, text="Filtrar por sitio: ", bg=self.bg_color, font=self.font_default).grid(row=1, column=0, sticky="e", pady=3)
        self.entry_filter_site = tk.Entry(self.bloque3, width=20)
        self.entry_filter_site.grid(row=1, column=1, padx=5, pady=3, sticky="w")
        self.entry_filter_site.bind("<KeyRelease>", self._filter_deployments)

        filter2_frame = tk.Frame(self.bloque3, bg=self.bg_color)
        filter2_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=4)

        tk.Label(filter2_frame, text="Mes: ", bg=self.bg_color, font=self.font_default).pack(side="left", padx=(0,2))
        self.month_var = tk.StringVar(value="Todos")
        self.month_combo = ttk.Combobox(filter2_frame, textvariable=self.month_var, values=["Todos"] + [f"{i:02d}" for i in range(1, 13)], width=6, state="readonly")
        self.month_combo.pack(side="left", padx=2)
        self.month_var.trace_add("write", self._filter_deployments)

        tk.Label(filter2_frame, text="Año: ", bg=self.bg_color, font=self.font_default).pack(side="left", padx=(10,2))
        self.year_var = tk.StringVar(value="Todos")
        self.year_combo = ttk.Combobox(filter2_frame, textvariable=self.year_var, values=["Todos"] + [str(y) for y in range(2015, 2035)], width=6, state="readonly")
        self.year_combo.pack(side="left", padx=2)
        self.year_var.trace_add("write", self._filter_deployments)

        tk.Label(self.bloque3, text="Deployment: ", bg=self.bg_color, font=self.font_default).grid(row=3, column=0, sticky="ne", pady=3)
        self.deployment_listbox = tk.Listbox(self.bloque3, height=5, width=50, exportselection=False)
        self.deployment_listbox.grid(row=3, column=1, columnspan=2, padx=5, pady=3, sticky="w")
        self.deployment_listbox.bind("<<ListboxSelect>>", self._on_deployment_selected)

        scroll_lb = ttk.Scrollbar(self.bloque3, orient="vertical", command=self.deployment_listbox.yview)
        scroll_lb.grid(row=3, column=3, sticky="ns", pady=3)
        self.deployment_listbox.configure(yscrollcommand=scroll_lb.set)

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

        self.start_btn = tk.Button(f, text=self.buttons_cfg.get("start", "Iniciar"), command=self.start,
                  bg=self.btn_bg, fg=self.btn_fg, font=self.font_default, width=20, height=2)
        self.start_btn.pack(pady=12)

        self.bind("<Return>", lambda e: self.start())
        self.start_btn.focus_set()

        self.geometry("575x420")

    def _set_mode(self, is_scientific):
        self.camtrap_mode_var.set(is_scientific)
        self._update_switch_visual()

        if is_scientific:
            self.bloque3.pack(fill="x", padx=10, pady=5, before=self.bloque2)
            self.bloque4.pack(fill="x", padx=10, pady=5, before=self.bloque2)
            self.geometry("575x900")
        else:
            self.bloque3.pack_forget()
            self.bloque4.pack_forget()
            self.geometry("575x420")

    def _update_switch_visual(self):
        is_sci = self.camtrap_mode_var.get()
        self.label_std.config(bg="#4CAF50", fg="#111111") if not is_sci else self.label_std.config(bg="#e0e0e0", fg="#333333")
        self.label_sci.config(bg="#9C27B0", fg="#111111") if is_sci else self.label_sci.config(bg="#e0e0e0", fg="#333333")

    def _get_start_button(self):
        for widget in self.scroll_frame.winfo_children():
            if isinstance(widget, tk.Button) and widget.cget("text") in (
                    self.buttons_cfg.get("start", "Iniciar"), "Iniciar"):
                return widget
        return None

    def _mostrar_dialogo_contenido_mixto(self, video_count, photo_count, orphan_estimate):
        """Diálogo para elegir modo de procesamiento cuando hay videos Y fotos."""
        dialog = tk.Toplevel(self)
        dialog.title("📁 Contenido mixto detectado")
        dialog.geometry("480x400")
        dialog.transient(self)
        dialog.grab_set()
        dialog.focus_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (480 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"480x400+{x}+{y}")
        
        info_frame = tk.LabelFrame(dialog, text="Contenido de la carpeta",
                                font=("Arial", 10, "bold"), padx=10, pady=8)
        info_frame.pack(fill="x", padx=15, pady=(10, 5))
        
        tk.Label(info_frame, text=f"🎥 Videos detectados: {video_count}",
                font=("Arial", 10)).pack(anchor="w", pady=2)
        tk.Label(info_frame, text=f"📷 Fotos detectadas: {photo_count}",
                font=("Arial", 10)).pack(anchor="w", pady=2)
        
        # 🔒 FIX: Aclarar que es una estimación aproximada
        tk.Label(info_frame, text=f"📷 Fotos que podrían ser huérfanas: ~{orphan_estimate}",
                font=("Arial", 10), fg="#d32f2f").pack(anchor="w", pady=2)
        tk.Label(info_frame, text="(Estimación basada en fotos por video. El número real se calculará después)",
                font=("Arial", 8), fg="gray").pack(anchor="w")
        
        tk.Label(dialog, text="¿Qué desea procesar?",
                font=("Arial", 11, "bold")).pack(pady=(10, 5))
        
        self._process_mode = tk.StringVar(value="both")
        tk.Radiobutton(dialog, text="🎥 Solo videos", variable=self._process_mode,
                    value="videos", font=("Arial", 10)).pack(anchor="w", padx=40, pady=2)
        tk.Radiobutton(dialog, text="📷 Solo fotos (ráfagas)", variable=self._process_mode,
                    value="photos", font=("Arial", 10)).pack(anchor="w", padx=40, pady=2)
        tk.Radiobutton(dialog, text="🔄 Ambos (videos + fotos asociadas + huérfanas)",
                    variable=self._process_mode,
                    value="both", font=("Arial", 10)).pack(anchor="w", padx=40, pady=2)
        
        photos_frame = tk.Frame(dialog)
        photos_frame.pack(pady=(8, 2), padx=40, fill="x")
        
        tk.Label(photos_frame, text="Fotos a asociar por video: ",
                font=("Arial", 10)).pack(side="left")
        
        photos_spin = tk.Spinbox(photos_frame, from_=0, to=10, width=5, font=("Arial", 10))
        photos_spin.delete(0, "end")
        photos_spin.insert(0, str(self.config_data.get("General", {}).get("photos_per_video", 1)))
        photos_spin.pack(side="left")
        
        def update_visibility(*args):
            if self._process_mode.get() == "both":
                photos_frame.pack(pady=(8, 2), padx=40, fill="x")
            else:
                photos_frame.pack_forget()
        
        self._process_mode.trace_add("write", update_visibility)
        update_visibility()
        
        tk.Label(dialog,
                text="Las fotos huérfanas se procesarán como ráfagas\ny se mezclarán en orden cronológico con los videos.",
                font=("Arial", 9), fg="gray", justify="center").pack(pady=5)
        
        result = {"mode": None, "photos_per_video": 1}
        
        def aceptar():
            result["mode"] = self._process_mode.get()
            try:
                result["photos_per_video"] = int(photos_spin.get())
            except Exception:
                result["photos_per_video"] = 1
            dialog.destroy()
        
        def cancelar():
            result["mode"] = None
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="✅ Aceptar", command=aceptar,
                bg="#4CAF50", fg="white", width=12,
                font=("Arial", 10, "bold")).pack(side="left", padx=10)
        tk.Button(btn_frame, text="❌ Cancelar", command=cancelar,
                width=12).pack(side="left", padx=10)
        
        dialog.wait_window()
        return result

    def select_input(self):
        folder = filedialog.askdirectory(parent=self, title="Seleccione carpeta de entrada")
        if not folder:
            return

        video_exts = {'.avi', '.mp4', '.mov', '.mkv', '.AVI', '.MP4', '.MOV', '.MKV',
                    '.webm', '.flv', '.wmv', '.m4v', '.3gp', '.mpg', '.mpeg', '.ts', '.mts'}
        img_exts = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}

        try:
            all_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
            video_count = sum(1 for f in all_files if os.path.splitext(f)[1].lower() in video_exts)
            photo_count = sum(1 for f in all_files if os.path.splitext(f)[1].lower() in img_exts)

            has_media = (video_count + photo_count) > 0

            if not has_media:
                messagebox.showwarning(
                    "Carpeta sin contenido válido",
                    "No se encontraron videos ni imágenes en la carpeta seleccionada.\n\n"
                    "Extensiones soportadas:\n"
                    "🎥 Videos: .avi, .mp4, .mov, .mkv\n"
                    "📷 Fotos: .jpg, .jpeg, .png\n\n"
                    "Seleccione otra carpeta o verifique el contenido.",
                    parent=self
                )
                return
        except Exception as e:
            messagebox.showerror("Error de acceso", f"No se pudo leer la carpeta:\n{e}", parent=self)
            return

        self.input_folder = folder
        self.entry_input.delete(0, tk.END)
        self.entry_input.insert(0, folder)

        self.process_mode = "both"
        self.photos_per_video = self.config_data.get("General", {}).get("photos_per_video", 1)

        if video_count > 0 and photo_count > 0:
            orphan_estimate = max(0, photo_count - video_count * self.photos_per_video)
            result = self._mostrar_dialogo_contenido_mixto(video_count, photo_count, orphan_estimate)
            if result["mode"] is None:
                return
            self.process_mode = result["mode"]
            self.photos_per_video = result["photos_per_video"]
        elif video_count == 0 and photo_count > 0:
            self.process_mode = "photos"
        elif video_count > 0 and photo_count == 0:
            self.process_mode = "videos"

        use_legacy = self.legacy_mode_var.get()
        if use_legacy:
            threading.Thread(target=self._scan_only_legacy, daemon=True).start()
        else:
            threading.Thread(target=self._start_processing, daemon=True).start()

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

#------------------Bloque2----------------------------------------------
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
            "locationID":    "locationID",
            "locationName":  "locationName",
            "cameraID":      "cameraID",
        }

        for entry_key, csv_key in mapping_basic.items():
            val = d.get(csv_key, "")
            self.basic_entries[entry_key].delete(0, tk.END)
            self.basic_entries[entry_key].insert(0, val)

        mapping_dep = {
            "setupBy":            "setupBy",
            "retrievedBy":        "retrievedBy",
            "latitude":           "latitude",
            "longitude":          "longitude",
            "deploymentStart":    "deploymentStart",
            "deploymentEnd":      "deploymentEnd",
            "cameraHeight":       "cameraHeight",
            "cameraTilt":         "cameraTilt",
            "detectionDistance":  "detectionDistance",
        }

        for entry_key, csv_key in mapping_dep.items():
            val = d.get(csv_key, "")
            self.deployment_entries[entry_key].delete(0, tk.END)
            self.deployment_entries[entry_key].insert(0, val)

        def _to_bool(val):
            return str(val).strip().lower() in ("true", "1", "yes", "sí", "si")

        self.timestamp_issues_var.set(_to_bool(d.get("timestampIssues", False)))
        self.bait_use_var.set(_to_bool(d.get("baitUse", False)))

    def _scan_only_legacy(self):
        """Escaneo inicial en modo legacy. Si hay fotos huérfanas, va directo al diálogo de ráfagas."""
        output_folder = self.config_data["General"]["output_folder"]
        session_folder = os.path.join(output_folder, "sessions", self.session_id)
        os.makedirs(session_folder, exist_ok=True)
        self.metadata_path = os.path.join(session_folder, "metadata.json")
        process_mode = getattr(self, "process_mode", "both")
        photos_per_video = getattr(self, "photos_per_video", 1)
        
        # 1. Escanear
        self.metadata_list = escanear_videos_legacy(
            self.input_folder, output_folder,
            photos_per_video=photos_per_video,
            process_mode=process_mode
        )
        self._save_metadata_temporal()
        
        # 2. 🔒 FIX: Obtener fotos huérfanas ANTES de mostrar stats
        try:
            import procesamiento
            orphan_with_ts = procesamiento.last_scan_stats.get("orphan_photos_with_ts", [])
        except Exception:
            orphan_with_ts = []
        
        # 3. 🔒 FIX: Si hay fotos huérfanas (o modo "photos"), ir DIRECTO al diálogo de ráfagas
        #    (NO mostrar messagebox de stats intermedio para evitar redundancia)
        if orphan_with_ts and process_mode in ("both", "photos"):
            threading.Thread(
                target=self._detectar_fotos_puras_bg,
                args=(output_folder, orphan_with_ts),
                daemon=True
            ).start()
            return  # El diálogo disparará el procesamiento después
        
        # 4. Si no hay nada que procesar, informar
        if not self.metadata_list:
            try:
                if self.winfo_exists():
                    self.after(0, lambda: messagebox.showinfo(
                        "Sin contenido",
                        "No se encontraron archivos para procesar con el modo seleccionado.",
                        parent=self
                    ))
            except Exception:
                pass
            return
        
        # 5. Si no hay fotos huérfanas, mostrar stats finales (solo en este caso)
        try:
            import procesamiento
            stats = procesamiento.last_scan_stats
            msg = self._build_scan_message(stats, process_mode)
            if msg:
                try:
                    if self.winfo_exists():
                        self.after(0, lambda: messagebox.showinfo(
                            "Escaneo completado", msg, parent=self
                        ))
                except Exception:
                    print(msg)
        except Exception as e:
            print(f"⚠️ Error leyendo estadísticas de escaneo: {e}")
        
        # 6. Informar al usuario que debe presionar Iniciar (solo videos pendientes)
        pending = sum(1 for m in self.metadata_list if m.get("status") == "pending")
        already_done = len(self.metadata_list) - pending
        msg = (
            f"✅ Escaneo completado (legacy):\n\n"
            f"📹 Videos detectados: {len(self.metadata_list)}\n"
            f"⏳ Pendientes: {pending}\n"
            f"✔️ Ya procesados: {already_done}\n\n"
            f"Complete los datos de deployment y presione 'Iniciar' para procesar."
        )
        try:
            if self.winfo_exists():
                self.after(0, lambda: messagebox.showinfo("Escaneo completado", msg, parent=self))
        except Exception:
            print(msg)


    def _start_processing(self):
        """Escaneo inicial en modo normal. Si hay fotos huérfanas, va directo al diálogo de ráfagas."""
        output_folder = self.config_data["General"]["output_folder"]
        session_folder = os.path.join(output_folder, "sessions", self.session_id)
        os.makedirs(session_folder, exist_ok=True)
        self.metadata_path = os.path.join(session_folder, "metadata.json")
        process_mode = getattr(self, "process_mode", "both")
        photos_per_video = getattr(self, "photos_per_video", 1)
        
        # 1. Escanear
        self.metadata_list = escanear_videos(
            self.input_folder, output_folder,
            photos_per_video=photos_per_video,
            process_mode=process_mode
        )
        self._save_metadata_temporal()
        
        # 2. 🔒 FIX: Obtener fotos huérfanas ANTES de mostrar stats
        try:
            from procesamiento import last_scan_stats
            orphan_with_ts = last_scan_stats.get("orphan_photos_with_ts", [])
        except Exception:
            orphan_with_ts = []
        
        # 3. 🔒 FIX: Si hay fotos huérfanas (o modo "photos"), ir DIRECTO al diálogo de ráfagas
        #    (NO mostrar messagebox de stats intermedio para evitar redundancia)
        if orphan_with_ts and process_mode in ("both", "photos"):
            threading.Thread(
                target=self._detectar_fotos_puras_bg,
                args=(output_folder, orphan_with_ts),
                daemon=True
            ).start()
            return  # El diálogo disparará el procesamiento después
        
        # 4. Si no hay nada que procesar, informar
        if not self.metadata_list:
            try:
                if self.winfo_exists():
                    self.after(0, lambda: messagebox.showinfo(
                        "Sin contenido",
                        "No se encontraron archivos para procesar con el modo seleccionado.",
                        parent=self
                    ))
            except Exception:
                pass
            return
        
        # 5. Si no hay fotos huérfanas, mostrar stats finales (solo en este caso)
        try:
            from procesamiento import last_scan_stats
            stats = last_scan_stats
            msg = self._build_scan_message(stats, process_mode)
            if msg:
                try:
                    if self.winfo_exists():
                        self.after(0, lambda: messagebox.showinfo(
                            "Escaneo completado", msg, parent=self
                        ))
                except Exception:
                    print(msg)
        except Exception as e:
            print(f"⚠️ Error leyendo estadísticas de escaneo: {e}")
        
        # 6. Procesar videos en segundo plano
        self._procesar_videos_en_background(output_folder)

    def _build_scan_message(self, stats, process_mode):
        """Construye el mensaje de estadísticas adaptado al modo de procesamiento."""
        mode = process_mode
        total_videos_found = stats.get("total_videos_found", 0)
        total_videos_processed = stats.get("total_videos_processed", 0)
        total_photos = stats.get("total_photos", 0)
        associated = stats.get("associated_photos", 0)
        orphans = stats.get("orphan_photos", 0)

        if mode == "videos":
            return (
                f"✅ Escaneo completado (solo videos):\n\n"
                f"🎥 Videos procesados: {total_videos_processed}\n"
                f"📷 Fotos ignoradas: {total_photos}"
            )
        elif mode == "photos":
            return (
                f"✅ Escaneo completado (solo fotos):\n\n"
                f"📷 Fotos detectadas: {total_photos}\n"
                f"🎥 Videos ignorados: {total_videos_found}\n\n"
                f"A continuación configurará el tamaño de ráfaga."
            )
        else:  # both
            if orphans > 0:
                return (
                    f"✅ Escaneo completado:\n\n"
                    f"🎥 Videos procesados: {total_videos_processed}\n"
                    f"📷 Fotos asociadas: {associated}\n"
                    f"📷 Fotos huérfanas: {orphans}\n\n"
                    f"Todo el contenido se mezclará en orden cronológico."
                )
            else:
                return (
                    f"✅ Escaneo completado:\n\n"
                    f"🎥 Videos procesados: {total_videos_processed}\n"
                    f"📷 Fotos asociadas: {associated}"
                )


    def _procesar_videos_en_background(self, output_folder):
        """Procesa los videos en metadata_list (los primeros 3 sincrónicos, el resto en pool)."""
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

    def _detectar_fotos_puras_bg(self, output_folder, orphan_with_ts):
        """Estima el tamaño de ráfaga a partir de gaps de tiempo y muestra el diálogo."""
        try:
            if not orphan_with_ts:
                return

            total = len(orphan_with_ts)

            # Estimar tamaño de ráfaga por gaps de tiempo
            gaps = []
            for i in range(1, len(orphan_with_ts)):
                gaps.append(orphan_with_ts[i]["ts"] - orphan_with_ts[i-1]["ts"])

            if gaps:
                # Umbral: fotos separadas por <= 2s pertenecen a la misma ráfaga
                umbral = 2.0
                grupos_estimados = 1
                tamano_actual = 1
                for g in gaps:
                    if g <= umbral:
                        tamano_actual += 1
                    else:
                        grupos_estimados += 1
                        tamano_actual = 1
                avg_estimado = max(1.0, total / max(1, grupos_estimados))
            else:
                avg_estimado = float(total)

            self.after(0, lambda: self._mostrar_dialogo_rafagas(orphan_with_ts, avg_estimado, output_folder))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"No se pudieron analizar las fotos:\n{e}"))

    def _mostrar_dialogo_rafagas(self, fotos_con_ts, avg_estimado, output_folder):
        """Diálogo interactivo para configurar el tamaño de ráfaga de fotos."""
        dialog = tk.Toplevel(self)
        dialog.title("📷 Configuración de ráfagas fotográficas")
        dialog.geometry("520x480")
        dialog.transient(self)
        dialog.grab_set()
        dialog.focus_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (520 // 2)
        y = (dialog.winfo_screenheight() // 2) - (480 // 2)
        dialog.geometry(f"520x480+{x}+{y}")
        
        total = len(fotos_con_ts)
        initial_burst = max(1, round(avg_estimado))
        process_mode = getattr(self, "process_mode", "both")
        
        # --- Frame superior: info con contexto según el modo ---
        info_frame = tk.LabelFrame(dialog, text="Información",
                                font=("Arial", 10, "bold"), padx=10, pady=8)
        info_frame.pack(fill="x", padx=15, pady=(10, 5))
        
        # 🔒 NUEVO: Mostrar contexto según el modo (evita redundancia con diálogos previos)
        if process_mode == "photos":
            tk.Label(info_frame, text=f"📷 Fotos en la carpeta: {total}",
                    font=("Arial", 10)).pack(anchor="w", pady=2)
            tk.Label(info_frame, text="(Modo: solo fotos, todos los archivos son candidatos)",
                    font=("Arial", 8), fg="gray").pack(anchor="w")
        else:  # both
            tk.Label(info_frame, text=f"📷 Fotos huérfanas detectadas: {total}",
                    font=("Arial", 10)).pack(anchor="w", pady=2)
            tk.Label(info_frame, text="(Fotos sin video asociado, se procesarán como ráfagas)",
                    font=("Arial", 8), fg="gray").pack(anchor="w")
        
        lbl_estimado = tk.Label(info_frame,
                                text=f"💡 Estimación automática: {initial_burst} fotos por ráfaga",
                                font=("Arial", 10), fg="#1976d2")
        lbl_estimado.pack(anchor="w", pady=2)
        
        # --- Frame central: control ---
        control_frame = tk.LabelFrame(dialog, text="Ajustar tamaño de ráfaga",
                                    font=("Arial", 10, "bold"), padx=10, pady=8)
        control_frame.pack(fill="x", padx=15, pady=5)
        
        tk.Label(control_frame, text="Fotos por ráfaga:",
                font=("Arial", 10)).pack(side="left", padx=(0, 5))
        
        burst_var = tk.StringVar(value=str(initial_burst))
        burst_spin = tk.Spinbox(control_frame, from_=1, to=max(1, total),
                                width=6, font=("Arial", 10, "bold"),
                                textvariable=burst_var)
        burst_spin.pack(side="left", padx=5)
        
        # --- Frame de preview (se actualiza en vivo) ---
        preview_frame = tk.LabelFrame(dialog, text="Vista previa",
                                    font=("Arial", 10, "bold"), padx=10, pady=8)
        preview_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        preview_label = tk.Label(preview_frame, text="", font=("Courier", 9),
                                justify="left", anchor="w")
        preview_label.pack(fill="both", expand=True)
        
        def update_preview(*args):
            try:
                burst_size = int(burst_var.get())
                if burst_size < 1:
                    burst_size = 1
            except Exception:
                burst_size = 1
            
            n_grupos = (total + burst_size - 1) // burst_size
            resto = total % burst_size if total % burst_size != 0 else burst_size
            
            lineas = []
            lineas.append(f"📦 Ráfagas resultantes: {n_grupos}")
            if resto != burst_size:
                lineas.append(f"⚠️  Última ráfaga: {resto} fotos (incompleta)")
            lineas.append("")
            
            # Mostrar hasta 5 grupos de ejemplo
            max_preview = 5
            for i in range(min(n_grupos, max_preview)):
                inicio = i * burst_size
                fin = min(inicio + burst_size, total)
                # Mostrar timestamps relativos
                try:
                    t_ini = datetime.fromtimestamp(fotos_con_ts[inicio]["ts"]).strftime("%H:%M:%S")
                    t_fin = datetime.fromtimestamp(fotos_con_ts[fin-1]["ts"]).strftime("%H:%M:%S")
                    lineas.append(f"  Ráfaga {i+1}: {fin - inicio} fotos  [{t_ini} → {t_fin}]")
                except Exception:
                    lineas.append(f"  Ráfaga {i+1}: {fin - inicio} fotos")
            
            if n_grupos > max_preview:
                lineas.append(f"  ... y {n_grupos - max_preview} ráfagas más")
            
            # 🔒 NUEVO: Mostrar qué pasa después según el modo
            lineas.append("")
            if process_mode == "both":
                lineas.append("→ Después se procesarán los videos pendientes")
            else:
                lineas.append("→ Después podrá etiquetar las fotos")
            
            preview_label.config(text="\n".join(lineas))
        
        burst_var.trace_add("write", update_preview)
        update_preview()
        
        # --- Botones ---
        result = {"burst_size": initial_burst, "confirmed": False}
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        def confirmar():
            try:
                result["burst_size"] = int(burst_var.get())
            except Exception:
                result["burst_size"] = 1
            if result["burst_size"] < 1:
                result["burst_size"] = 1
            result["confirmed"] = True
            dialog.destroy()
        
        def cancelar():
            result["confirmed"] = False
            dialog.destroy()
        
        # 🔒 NUEVO: Texto del botón más claro según el modo
        btn_text = "✅ Procesar fotos y continuar" if process_mode == "both" else "✅ Procesar fotos"
        tk.Button(btn_frame, text=btn_text, command=confirmar,
                bg="#4CAF50", fg="white", width=22,
                font=("Arial", 10, "bold")).pack(side="left", padx=10)
        tk.Button(btn_frame, text="❌ Cancelar", command=cancelar,
                width=12).pack(side="left", padx=10)
        
        dialog.wait_window()
        
        if result["confirmed"]:
            threading.Thread(
                target=self._procesar_fotos_con_parametro,
                args=(fotos_con_ts, result["burst_size"], output_folder),
                daemon=True
            ).start()

    def _procesar_fotos_con_parametro(self, fotos_con_ts, burst_size, output_folder):
        """Agrupa fotos por burst_size fijo y las procesa como ráfagas.
        Detecta modo legacy y usa funciones apropiadas."""
        try:
            # Agrupar fotos
            photo_groups = []
            for i in range(0, len(fotos_con_ts), burst_size):
                photo_groups.append(fotos_con_ts[i:i + burst_size])
            
            # Detectar modo legacy
            use_legacy = self.legacy_mode_var.get()
            
            if use_legacy:
                # 🔒 MODO LEGACY: procesar con ventana de progreso no modal
                self._show_photo_progress_and_process_legacy(photo_groups, output_folder)
            else:
                # 🔒 MODO NORMAL: procesar normalmente
                metadata_fotos = procesar_todas_las_rafagas(photo_groups, output_folder)
                
                # 🔒 FIX: en modo "both", las fotos se agregan a los videos ya escaneados
                # en modo "photos", reemplazan el metadata_list
                process_mode = getattr(self, "process_mode", "both")
                if process_mode == "both":
                    self.metadata_list.extend(metadata_fotos)
                    # Ordenar todo por timestamp
                    self.metadata_list.sort(key=lambda x: x.get("recorded_at", ""))
                else:
                    self.metadata_list = metadata_fotos
                
                self._save_metadata_temporal()
                
                # 🔒 FIX: si el modo es "both" y hay videos pendientes, continuar con
                # el procesamiento de videos correspondiente (legacy o normal)
                if process_mode == "both":
                    has_pending_videos = any(
                        not m.get("is_photo") and m.get("status") == "pending"
                        for m in self.metadata_list
                    )
                    if has_pending_videos:
                        # En modo normal, procesar videos en background
                        self.after(0, lambda: self._procesar_videos_en_background(output_folder))
        
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Fallo al procesar fotos:\n{e}"))

    def _show_photo_progress_and_process_legacy(self, photo_groups, output_folder):
        """Ventana de progreso NO MODAL para procesamiento de fotos en modo legacy."""
        from procesamiento_legacy import procesar_todas_las_rafagas_legacy
        
        progress_window = tk.Toplevel(self)
        progress_window.title("📷 Procesando fotos (Modo Legacy)")
        progress_window.geometry("500x300")
        progress_window.transient(self)
        progress_window.resizable(False, False)
        progress_window.attributes('-topmost', True)
        
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (progress_window.winfo_screenheight() // 2) - (300 // 2)
        progress_window.geometry(f"500x300+{x}+{y}")
        
        main_frame = tk.Frame(progress_window, bg="#f0f0f0", padx=20, pady=15)
        main_frame.pack(fill="both", expand=True)
        
        title_label = tk.Label(main_frame, text="Procesamiento de Fotos (Legacy)",
                            font=("Arial", 12, "bold"), bg="#f0f0f0")
        title_label.pack(pady=(0, 10))
        
        current_photo_label = tk.Label(main_frame, text="Preparando...",
                                    font=("Arial", 10), bg="#f0f0f0", wraplength=450)
        current_photo_label.pack(pady=5)
        
        progress_bar = ttk.Progressbar(main_frame, length=450, mode='determinate', maximum=len(photo_groups))
        progress_bar.pack(pady=10)
        
        stats_frame = tk.Frame(main_frame, bg="#f0f0f0")
        stats_frame.pack(pady=5)
        stats_label = tk.Label(stats_frame, text=f"0 / {len(photo_groups)} ráfagas completadas (0%)",
                            font=("Arial", 10), bg="#f0f0f0")
        stats_label.pack()
        
        import time
        start_time = time.time()
        errors_list = []
        
        def progress_callback(current, total):
            elapsed = time.time() - start_time
            avg_time = elapsed / current if current > 0 else 0
            remaining = avg_time * (total - current)
            remaining_str = f"{int(remaining // 60)}m {int(remaining % 60)}s" if remaining > 60 else f"{int(remaining)}s"
            
            current_photo_label.config(
                text=f"✅ Ráfaga {current}/{total} completada\nTiempo restante estimado: {remaining_str}",
                fg="#2e7d32"
            )
            
            progress_bar['value'] = current
            percentage = int((current / total) * 100)
            stats_label.config(text=f"{current} / {total} ráfagas completadas ({percentage}%)")
            
            if current >= total:
                current_photo_label.config(
                    text=f"✅ Procesamiento completado!\n{total} ráfagas procesadas",
                    fg="#1976d2", font=("Arial", 11, "bold")
                )
                progress_window.attributes('-topmost', False)
            
            progress_window.update()
        
        def process_with_progress():
            try:
                metadata_fotos = procesar_todas_las_rafagas_legacy(
                    photo_groups, output_folder, progress_callback
                )
                
                # Filtrar errores
                for meta in metadata_fotos:
                    if meta.get("status") == "error":
                        errors_list.append(f"• {os.path.basename(meta.get('video_path', 'unknown'))}: {meta.get('error_message', 'Error desconocido')}")
                
                # Actualizar metadata_list
                process_mode = getattr(self, "process_mode", "both")
                if process_mode == "both":
                    self.metadata_list.extend(metadata_fotos)
                    self.metadata_list.sort(key=lambda x: x.get("recorded_at", ""))
                else:
                    self.metadata_list = metadata_fotos
                
                self._save_metadata_temporal()
                
                # Cerrar ventana de progreso después de 2 segundos
                self.after(2000, progress_window.destroy)
                
                # Mostrar errores si los hay
                if errors_list:
                    self.after(2500, lambda: messagebox.showwarning(
                        "Errores en procesamiento de fotos",
                        f"Se completaron {len(metadata_fotos) - len(errors_list)} ráfagas correctamente.\n\n"
                        f"❌ {len(errors_list)} ráfagas fallaron:\n\n" + "\n".join(errors_list[:10]) +
                        (f"\n... y {len(errors_list) - 10} más" if len(errors_list) > 10 else "")
                    ))
                
                # Continuar con videos si modo "both"
                if process_mode == "both":
                    has_pending_videos = any(
                        not m.get("is_photo") and m.get("status") == "pending"
                        for m in self.metadata_list
                    )
                    if has_pending_videos:
                        # En legacy, el procesamiento se dispara al presionar "Iniciar"
                        pass
            
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Error crítico",
                    f"Error durante el procesamiento de fotos:\n{e}",
                    parent=progress_window
                ))
                progress_window.destroy()
        
        # Iniciar procesamiento en thread separado
        threading.Thread(target=process_with_progress, daemon=True).start()




    def _actualizar_metadata_fotos(self, metadata_list):
        self.metadata_list = metadata_list
        self._save_metadata_temporal()

    def start(self):
        if not self.input_folder:
            messagebox.showerror("Error", "Debe seleccionar la carpeta de videos.")
            return

        basic_fields = {
            "Sitio": self.basic_entries["locationID"].get().strip(),
            "Subsitio": self.basic_entries["locationName"].get().strip(),
            "Cámara": self.basic_entries["cameraID"].get().strip(),
            "Operador": self.basic_entries["classifiedBy"].get().strip()
        }

        missing_basic = [name for name, val in basic_fields.items() if not val]
        if missing_basic:
            messagebox.showerror(
                "Campos obligatorios",
                "Complete los siguientes campos:\n• " + "\n• ".join(missing_basic)
            )
            return

        if self.camtrap_mode_var.get():
            dep_fields = {
                "Instalado por": self.deployment_entries["setupBy"].get().strip(),
                "Retirado por": self.deployment_entries["retrievedBy"].get().strip(),
                "Latitud": self.deployment_entries["latitude"].get().strip(),
                "Longitud": self.deployment_entries["longitude"].get().strip(),
                "Inicio deployment": self.deployment_entries["deploymentStart"].get().strip(),
                "Fin deployment": self.deployment_entries["deploymentEnd"].get().strip(),
                "Altura cámara": self.deployment_entries["cameraHeight"].get().strip(),
                "Ángulo vertical": self.deployment_entries["cameraTilt"].get().strip(),
                "Distancia detección": self.deployment_entries["detectionDistance"].get().strip()
            }

            missing_dep = [name for name, val in dep_fields.items() if not val]
            if missing_dep:
                messagebox.showerror(
                    "Campos obligatorios (Modo Científico)",
                    "Falta completar:\n• " + "\n• ".join(missing_dep)
                )
                return

        location_id = basic_fields["Sitio"]
        location_name = basic_fields["Subsitio"]
        camera_id = basic_fields["Cámara"]
        classified_by = basic_fields["Operador"]

        deployment_data = {}
        if self.camtrap_mode_var.get():
            for key, entry in self.deployment_entries.items():
                deployment_data[key] = entry.get().strip()
            deployment_data["timestampIssues"] = self.timestamp_issues_var.get()
            deployment_data["baitUse"] = self.bait_use_var.get()

        deployment_start = deployment_data.get("deploymentStart", "")
        deployment_id = generate_deployment_id(location_id, location_name, camera_id, deployment_start)

        for entry in self.metadata_list:
            for k in ["locationID", "locationName", "cameraID", "classifiedBy",
                      "site", "subsite", "camera", "operator", "session_id", "camtrap_db_session"]:
                entry.pop(k, None)

            entry["classification"] = {
                "species": [],
                "counts": {},
                "behaviors": [],
                "optional_tags": []
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

            entry["file"] = {
                "video_path": entry.get("video_path", ""),
                "video_hash": entry.get("video_hash", ""),
                "frames_folder": entry.get("frames_folder", ""),
                "promedio": entry.get("promedio"),
                "tops": entry.get("tops", []),
                "mask": entry.get("mask")
            }

        self._save_metadata_temporal()

        use_legacy = self.legacy_mode_var.get()
        pending = sum(1 for m in self.metadata_list if m.get("status") == "pending")

        if use_legacy and pending > 0:
            self._show_progress_and_process()
        else:
            self.after(100, self.open_tagger_delayed)

#-----------------------------Bloque 3---------------------------------------------------
    def _show_progress_and_process(self):
        progress_window = tk.Toplevel(self)
        progress_window.title("🐌 Procesando en Modo Legacy")
        progress_window.geometry("500x280")
        progress_window.transient(self)
        progress_window.resizable(False, False)

        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (progress_window.winfo_screenheight() // 2) - (280 // 2)
        progress_window.geometry(f"500x280+{x}+{y}")

        progress_window.attributes('-topmost', True)

        total_videos = len(self.metadata_list)
        pending_videos = [m for m in self.metadata_list if m.get("status") == "pending"]
        pending_count = len(pending_videos)

        main_frame = tk.Frame(progress_window, bg="#f0f0f0", padx=20, pady=15)
        main_frame.pack(fill="both", expand=True)

        title_label = tk.Label(main_frame, text="Procesamiento Secuencial",
                              font=("Arial", 12, "bold"), bg="#f0f0f0")
        title_label.pack(pady=(0, 10))

        current_video_label = tk.Label(main_frame, text="Preparando...",
                                      font=("Arial", 10), bg="#f0f0f0", wraplength=450)
        current_video_label.pack(pady=5)

        progress_bar = ttk.Progressbar(main_frame, length=450, mode='determinate', maximum=pending_count)
        progress_bar.pack(pady=10)

        stats_frame = tk.Frame(main_frame, bg="#f0f0f0")
        stats_frame.pack(pady=5)
        stats_label = tk.Label(stats_frame, text=f"0 / {pending_count} completados (0%)",
                              font=("Arial", 10), bg="#f0f0f0")
        stats_label.pack()

        error_frame = tk.Frame(main_frame, bg="#fff5f5", relief="solid", bd=1)
        error_label = tk.Label(error_frame, text="", font=("Arial", 9), bg="#fff5f5",
                              fg="#d32f2f", wraplength=450, justify="left")
        error_label.pack(padx=5, pady=5)
        errors_list = []

        close_btn = tk.Button(main_frame, text="Cerrar y continuar", state="disabled",
                             command=lambda: self._close_progress_and_continue(progress_window),
                             bg="#4CAF50", fg="#ffffff", font=("Arial", 10, "bold"),
                             padx=20, pady=5)
        close_btn.pack(pady=(10, 0))

        import time
        start_time = time.time()

        def progress_callback(current, total):
            if current <= len(self.metadata_list):
                video_meta = self.metadata_list[current - 1]
                video_name = os.path.basename(video_meta.get("video_path", "unknown"))
                status = video_meta.get("status", "unknown")

                if status == "error":
                    error_msg = video_meta.get("error_message", "Error desconocido")
                    current_video_label.config(
                        text=f"❌ Error en: {video_name}\n{error_msg}",
                        fg="#d32f2f"
                    )
                    errors_list.append(f"• {video_name}: {error_msg}")
                else:
                    elapsed = time.time() - start_time
                    avg_time = elapsed / current if current > 0 else 0
                    remaining = avg_time * (total - current)
                    remaining_str = f"{int(remaining // 60)}m {int(remaining % 60)}s" if remaining > 60 else f"{int(remaining)}s"
                    current_video_label.config(
                        text=f"✅ Procesado: {video_name}\nTiempo restante estimado: {remaining_str}",
                        fg="#2e7d32"
                    )

                progress_bar['value'] = current

                percentage = int((current / total) * 100)
                stats_label.config(text=f"{current} / {total} completados ({percentage}%)")

                if errors_list:
                    error_text = f"⚠️ Errores encontrados ({len(errors_list)}):\n" + "\n".join(errors_list[-3:])
                    if len(errors_list) > 3:
                        error_text += f"\n... y {len(errors_list) - 3} más"
                    error_label.config(text=error_text)
                    error_frame.pack(pady=5, fill="x")

                if current >= total:
                    current_video_label.config(
                        text=f"✅ Procesamiento completado!\n{total} videos procesados, {len(errors_list)} errores",
                        fg="#1976d2", font=("Arial", 11, "bold")
                    )
                    close_btn.config(state="normal")
                    progress_window.attributes('-topmost', False)

                self._save_metadata_temporal()

            progress_window.update()

        output_folder = self.config_data["General"]["output_folder"]

        def process_with_progress():
            try:
                processed = procesar_lote_legacy(self.metadata_list, output_folder, progress_callback)
                self.metadata_list = processed
                self._save_metadata_temporal()
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "Error crítico",
                    f"Error durante el procesamiento:\n{e}",
                    parent=progress_window
                ))

        threading.Thread(target=process_with_progress, daemon=True).start()

    def _close_progress_and_continue(self, progress_window):
        progress_window.destroy()

        failed_videos = [v for v in self.metadata_list if v.get("status") == "error"]

        if failed_videos:
            msg = f"Procesamiento completado\n\n"
            msg += f"✅ {len(self.metadata_list) - len(failed_videos)} videos procesados correctamente\n"
            msg += f"❌ {len(failed_videos)} videos fallaron\n\n"
            msg += "¿Desea etiquetar manualmente los videos fallidos?\n"
            msg += "(Podrá reproducirlos con su reproductor de video)"

            result = messagebox.askyesno("Videos Fallidos", msg)

            if result:
                self.after(100, lambda: self.open_manual_tagger(failed_videos))
            else:
                self.after(100, self.open_tagger_delayed)
        else:
            self.after(100, self.open_tagger_delayed)

    def open_manual_tagger(self, failed_videos):
        from gui_manual_tagger import ManualTaggerGUI
        self.destroy()
        app = ManualTaggerGUI(
            failed_videos=failed_videos,
            config_data=self.config_data,
            metadata_path=self.metadata_path
        )
        app.mainloop()

    def open_tagger_delayed(self):
        from gui_tagger import DynamicTagger
        self.destroy()
        app = DynamicTagger(
            metadata_path=self.metadata_path,
            session_id=self.session_id,
            scientific_mode=self.camtrap_mode_var.get()
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