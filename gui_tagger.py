# gui_tagger.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageEnhance, ImageFilter
import cv2, os, glob, subprocess, threading, json
import numpy as np
import uuid
from config_utils import load_config

metadata_lock = threading.Lock()

# Valores por defecto para ajustes de imagen
DEFAULT_ADJUSTMENTS = {
    "brightness": 1.0,
    "contrast": 1.0,
    "sharpness": 1.0,
    "smoothness": 0.0,
    "denoise": 0.0,
    "flatfield": 0.0
}


def open_video_default(video_path):
    if os.name == "nt":
        os.startfile(video_path)
    elif os.uname().sysname == "Darwin":
        subprocess.Popen(["open", video_path])
    else:
        subprocess.Popen(["xdg-open", video_path])


class DynamicTagger(tk.Tk):
    def __init__(self, metadata_path=None, session_id=None):
        super().__init__()
        # --- Cargar configuración ---
        self.config_data = load_config()
        gui_cfg = self.config_data.get("GUI_Tagger", {})
        self.species_tags = gui_cfg.get("species_tags", [])
        self.secondary_tags = gui_cfg.get("secondary_tags", [])
        self.behavior_tags = gui_cfg.get("behavior_tags", [])
        colors = gui_cfg.get("colors", {})
        labels_cfg = gui_cfg.get("labels", {})
        buttons_cfg = gui_cfg.get("buttons", {})
        # Lista de tags "otros" leída desde config.ini
        self.other_tags_list = gui_cfg.get("other_tags_list", [
            "Zorro", "Puma", "Tapir", "Gato montés", "Venado",
            "Ñandú", "Coipo", "Jaguar", "Carpincho", "Humano"
        ])
        self.title(gui_cfg.get("title", "Dynamic Video Tagger"))
        self.geometry(gui_cfg.get("geometry", "1300x750"))
        # --- Leer output_folder desde config.ini ---
        self.output_folder = self.config_data["General"]["output_folder"]
        if metadata_path is None:
            metadata_path = os.path.join(self.output_folder, "videos_metadata.json")
        self.metadata_path = metadata_path
        self.video_dirs = []
        self.session_id = session_id if session_id else str(uuid.uuid4())
        self.load_metadata(self.metadata_path)
        for v in self.video_dirs:
            if "session_id" not in v:
                v["session_id"] = self.session_id
        self.current_video_index = 0
        self.current_frame_index = 0
        # <-- AÑADIR ESTA LÍNEA -->
        # Detectar si la sesión actual es en modo Camtrap DB
        # Esto se basa en la bandera guardada en la metadata de la sesión por gui_inicial.py
        first_video_meta = self.video_dirs[0] if self.video_dirs else {}
        self.camtrap_db_session = first_video_meta.get("camtrap_db_session", False)
        # <-- FIN AÑADIDO -->
        self.show_mask = True
        self.blink_mode = True
        self.blink_state = True
        self.blink_interval = 500
        self.tk_imgs = {}
        self.count_var = tk.IntVar(value=1)
        self.embed_metadata_var = tk.BooleanVar(value=False)
        self.xlsx_var = tk.BooleanVar(value=False)
        self.metadata_vars = {
            "Temp": tk.StringVar(),
            "Fase Lunar": tk.StringVar(),
            "Clima": tk.StringVar(),
            "Corrección Horaria": tk.StringVar(),
            "Deployment": tk.StringVar(),
            "Altura": tk.StringVar()
        }
        # Atributos para ajustes de imagen
        self.image_adjustments = DEFAULT_ADJUSTMENTS.copy()
        self.adjust_window = None
        self.adjust_sliders = {}  # Referencia a los sliders
        self.clipboard_data = None  # ←←← ya la añadiste antes, pero asegúrate
        self.main_buttons = []
        self.left_buttons = []
        self.behaviors = {}
        self.species_buttons = {}  # ←←← NUEVO: para gestionar estado visual de tags de especie
        self.dropdown_window = None  # referencia al popup de lista desplegable
        self.labels_cfg = labels_cfg
        self.colors_cfg = colors
        # ←←← NUEVO: colores unificados para botones de tags →→→
        self.tag_active_bg = self.colors_cfg.get("tag_active", "#90ee90")
        self.tag_inactive_bg = self.colors_cfg.get("tag_inactive", "#f0f0f0")
        # (Opcional) Si prefieres colores separados, también los defines aquí:
        self.species_active_bg = self.colors_cfg.get("species_active", "#90ee90")
        self.species_inactive_bg = self.colors_cfg.get("species_inactive", "#f0f0f0")
        self.behavior_active_bg = self.colors_cfg.get("behavior_active", "#ffff99")
        self.behavior_inactive_bg = self.colors_cfg.get("behavior_inactive", "#f0f0f0")
        # →→→ FIN NUEVO ←←←
        self.buttons_cfg = buttons_cfg
        self.build_layout()
        # --- Bind teclas ---
        self.bind("<space>", self.toggle_mask)
        self.bind("<Shift-space>", self.toggle_blink_mode)
        self.bind("<Left>", lambda e: self.prev_frame())
        self.bind("<Right>", lambda e: self.next_frame())
        self.bind("<Down>", lambda e: self.prev_video())
        self.bind("<Up>", lambda e: self.next_video())
        self.bind("<Control-c>", self._handle_copy)
        self.bind("<Control-v>", self._handle_paste)
        self.after(100, self.show_frame)
        self.after(self.blink_interval, self.blink_mask)
    # -------------------------------
    def load_metadata(self, metadata_path):
        if not os.path.exists(metadata_path):
            self.video_dirs = []
            return
        with open(metadata_path, "r") as f:
            self.video_dirs = json.load(f)
        
        # ←←← NUEVO: Sincronizar todos los videos con el estado en disco →→→
        self.sync_all_videos_with_disk()
        for entry in self.video_dirs:
            entry.setdefault("tags", [])
            entry.setdefault("species_counts", {})
            entry.setdefault("behaviors", [])
            entry.setdefault("notes", "")
            entry.setdefault("embed_metadata", False)
            entry.setdefault("xlsx", False)
            entry.setdefault("is_favorite", False)
            if "session_id" not in entry:
                entry["session_id"] = self.session_id
            # Asegurar que la bandera camtrap_db_session exista en cada entrada (por si acaso)
            entry.setdefault("camtrap_db_session", False)
            
    def sync_all_videos_with_disk(self):
        """Sincroniza el estado de todos los videos con lo que hay en disco."""
        if not self.video_dirs:
            return
        for entry in self.video_dirs:
            if entry.get("status") != "pending":
                continue
            frames_folder = os.path.join(self.output_folder, "frames", entry.get("frames_folder", ""))
            if not os.path.exists(frames_folder):
                continue
            # ←←← NUEVO: Buscar archivos sin depender de fecha_prefix →→→
            files_in_folder = os.listdir(frames_folder)
            # Buscar promedio (cualquier archivo que contenga "promedio")
            promedio_files = [f for f in files_in_folder if "promedio" in f.lower()]
            top_files = sorted([f for f in files_in_folder if "top_" in f.lower()])

            if promedio_files and top_files:
                entry["status"] = "done"
                # Rellenar promedio
                if not entry.get("promedio"):
                    entry["promedio"] = os.path.join(frames_folder, promedio_files[0])
                # Rellenar tops
                if not entry.get("tops"):
                    entry["tops"] = [os.path.join(frames_folder, f) for f in top_files]

                # <-- NUEVO: Calcular y asignar la ruta de la máscara -->
                # Asumimos que la máscara siempre existe si existen promedio y tops,
                # y que su nombre se deriva del promedio.
                if entry.get("promedio"):
                    # Ejemplo: promedio_path = ".../230926_131616_promedio.jpg"
                    promedio_path = entry["promedio"]
                    promedio_filename = os.path.basename(promedio_path) # "230926_131616_promedio.jpg"
                    # Reemplazar "_promedio" por "_mask"
                    mask_filename = promedio_filename.replace("_promedio", "_mask") # "230926_131616_mask.jpg"
                    mask_path = os.path.join(frames_folder, mask_filename) # Ruta completa
                    # Asignar la ruta calculada al entry
                    entry["mask"] = mask_path

                # Actualizar fecha_prefix si es necesario
                if not entry.get("fecha_prefix") and promedio_files[0]:
                    # Extraer del nombre del archivo: "251025_143022_promedio.jpg" → "251025_143022"
                    name = os.path.splitext(promedio_files[0])[0]
                    if "_promedio" in name:
                        entry["fecha_prefix"] = name.replace("_promedio", "")

    def reload_current_video_from_disk(self):
        """Recarga el video actual desde disco (archivos + JSON)."""
        try:
            if not (0 <= self.current_video_index < len(self.video_dirs)):
                return
            entry = self.video_dirs[self.current_video_index]
            if entry.get("status") != "pending":
                return  # Solo procesar si está pendiente
            frames_folder = os.path.join(self.output_folder, "frames", entry.get("frames_folder", ""))
            if not os.path.exists(frames_folder):
                return
            files_in_folder = os.listdir(frames_folder)
            promedio_files = [f for f in files_in_folder if "promedio" in f.lower()]
            top_files = sorted([f for f in files_in_folder if "top_" in f.lower()])

            if promedio_files and top_files:
                entry["status"] = "done"
                if not entry.get("promedio"):
                    entry["promedio"] = os.path.join(frames_folder, promedio_files[0])
                if not entry.get("tops"):
                    entry["tops"] = [os.path.join(frames_folder, f) for f in top_files]

                # <-- NUEVO: Calcular y asignar la ruta de la máscara -->
                # Similar a sync_all, se hace dentro del bloque de "done".
                if entry.get("promedio"):
                    promedio_path = entry["promedio"]
                    promedio_filename = os.path.basename(promedio_path)
                    mask_filename = promedio_filename.replace("_promedio", "_mask")
                    mask_path = os.path.join(frames_folder, mask_filename)
                    entry["mask"] = mask_path

                # Guardar inmediatamente en el archivo de sesión
                self.save_metadata()
        except Exception as e:
            pass  # Silencioso, como antes
    # -------------------------------
    def build_layout(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True)

        # --- Columna central ---
        center_frame = tk.Frame(main_frame)
        center_frame.pack(side="left", padx=5, pady=5)

        # Checkboxes embed metadata / .xlsx
        check_frame = tk.Frame(center_frame)
        check_frame.pack(fill="x", pady=(0, 5))
        tk.Checkbutton(check_frame, text="Embed metadata", variable=self.embed_metadata_var,
                       command=self.update_checkbox).pack(side="left", padx=5)
        tk.Checkbutton(check_frame, text=".xlsx", variable=self.xlsx_var,
                       command=self.update_checkbox).pack(side="left", padx=5)

        # Label de video + contadores + favorito
        top_frame = tk.Frame(center_frame)
        top_frame.pack(fill="x")
        
        # Botón de favorito
        self.favorite_button = tk.Button(
            top_frame, 
            text="☆", 
            width=2, 
            height=1,
            font=("Arial", 16),
            command=self.toggle_favorite,
            bg=self.colors_cfg.get("favorite_button_bg", "#ffffff"),
            fg=self.colors_cfg.get("favorite_button_fg", "#ffd700")
        )
        self.favorite_button.pack(side="left", padx=(0, 5))

        # Botón de exclusión
        self.exclude_button = tk.Button(
            top_frame, 
            text="🚫", # Puedes cambiar este texto por otro símbolo o texto si prefieres
            width=2, 
            height=1,
            font=("Arial", 16),
            command=self.toggle_exclude,
            bg=self.colors_cfg.get("exclude_button_bg", "#ffffff"), # Puedes definir este color en config.ini
            fg=self.colors_cfg.get("exclude_button_fg", "#ff0000")   # Puedes definir este color en config.ini
        )
        self.exclude_button.pack(side="left", padx=(0, 5))        
        
        self.video_label = tk.Label(top_frame, text="", font=("Arial", 14), anchor="w")
        self.video_label.pack(side="left", fill="x", expand=True)
        self.counter_label = tk.Label(top_frame, text="", font=("Arial", 14))
        self.counter_label.pack(side="right")

        # Canvas
        self.canvas = tk.Canvas(center_frame, width=912, height=513, bg="black")
        self.canvas.pack()
        self.canvas.bind("<Double-Button-1>", self.play_video)

        # Botones principales
        control_frame = tk.Frame(center_frame)
        control_frame.pack(pady=5)
        self.tag_frame_bottom = tk.Frame(control_frame)
        self.tag_frame_bottom.pack(side="left", padx=10)

        # --- MODIFICACIÓN AQUÍ ---
        # Colores específicos para los botones principales (vistosos, diferentes y NO VERDE/ROSA por defecto)
        main_button_1_inactive_bg = self.colors_cfg.get("main_button_1_inactive", "#FFD700") # Dorado (puedes cambiarlo)
        main_button_2_inactive_bg = self.colors_cfg.get("main_button_2_inactive", "#87CEEB") # Azul cielo (puedes cambiarlo)
        main_button_active_bg = self.tag_active_bg # Reutiliza el color de activo general

        for i, tag in enumerate(self.species_tags[:2]): # Solo los dos primeros
            # Ajustar el ancho aquí (por ejemplo, width=23, que es un 53% más que 15)
            # Asignar color inactivo específico según el índice
            if i == 0:
                color_inactivo = main_button_1_inactive_bg
            else: # i == 1
                color_inactivo = main_button_2_inactive_bg

            b = tk.Button(self.tag_frame_bottom, text=tag, width=23, height=2, bg=color_inactivo) # Ancho aumentado a 23
            b.pack(side="left", padx=5)
            b.bind("<Button-1>", lambda e, t=tag: self.species_click(t, left=True, event=e))
            b.bind("<Button-3>", lambda e, t=tag: self.species_click(t, left=False, event=e))
            self.main_buttons.append(b)
            self.species_buttons[tag] = b # Registrar también en el diccionario general
        # --- FIN MODIFICACIÓN ---
            

        tk.Label(self.tag_frame_bottom, text=self.labels_cfg.get("count", "Cantidad:")).pack(side="left",
                                                                                            padx=(10, 0))
        self.count_dropdown = ttk.Combobox(self.tag_frame_bottom, textvariable=self.count_var, width=3,
                                           state="readonly")
        self.count_dropdown['values'] = list(range(1, 10))
        self.count_dropdown.current(0)
        self.count_dropdown.pack(side="left", padx=(0, 10))

        # Botón Limpiar
        clear_btn = tk.Button(control_frame, text="Limpiar", width=8, height=2,
                            bg=self.colors_cfg.get("clear_button_bg", "#ff9999"),
                            fg=self.colors_cfg.get("clear_button_fg", "black"))
        clear_btn.pack(side="left", padx=10)
        clear_btn.bind("<Button-1>", lambda e: self.clear_current_video())
        clear_btn.bind("<Button-3>", lambda e: self.clear_all_videos_ask())

        # ←←← NUEVO: Botón para mostrar/ocultar metadatos →→→
        self.toggle_meta_btn = tk.Button(
            control_frame, 
            text="Metadatos", 
            width=8, 
            height=2,
            command=self.toggle_metadata_fields,
            bg=self.colors_cfg.get("metadata_button_bg", "#d0d0d0"),
            fg=self.colors_cfg.get("metadata_button_fg", "black")
        )
        self.toggle_meta_btn.pack(side="left", padx=10)


         # Label info tags
        self.label_frame = tk.Label(center_frame, text="", font=("Arial", 12), justify="left", anchor="w")
        # Cuadro de texto para anotaciones
        self.notes_label = tk.Label(center_frame, text="Notas:")
        self.notes_text = tk.Text(center_frame, height=4, width=100)

        # Frame para metadatos (oculto por defecto)
        self.meta_frame = tk.Frame(center_frame)
        for i, (label, var) in enumerate(self.metadata_vars.items()):
            tk.Label(self.meta_frame, text=label).grid(row=0, column=2 * i, padx=2, sticky="e")
            entry = tk.Entry(self.meta_frame, textvariable=var, width=8)
            entry.grid(row=0, column=2 * i + 1, padx=2, sticky="w")
            entry.bind("<FocusOut>", lambda e: self.save_metadata())

        # Empaquetar en orden correcto
        self.label_frame.pack(pady=5, fill="x")
        self.notes_label.pack(anchor="w")
        self.notes_text.pack(fill="x", pady=(0, 5))

        # Ocultar metadatos al inicio (sin empaquetar aún)
        # → se mostrará con `pack(before=self.label_frame)`

        # --- Botones secundarios y comportamiento (alineados al borde inferior del canvas) ---
        btn_frame_height = 513  # altura del canvas
        # Botones secundarios izquierda
        self.tag_frame_left = tk.Frame(main_frame)
        pady_left = max(0, btn_frame_height - len(self.secondary_tags) * 32)
        self.tag_frame_left.pack(side="left", padx=5, pady=(pady_left, 60))

        for i, tag in enumerate(self.secondary_tags):
            b = tk.Button(self.tag_frame_left, text=tag, width=6, bg=self.tag_inactive_bg)           
            b.pack(pady=2)
            if i == 0:
                b.bind("<Button-1>", self.show_secondary_dropdown)
            else:
                b.bind("<Button-1>", lambda e, t=tag: self.species_click(t, left=True, event=e))
                b.bind("<Button-3>", lambda e, t=tag: self.species_click(t, left=False, event=e))
                self.species_buttons[tag] = b  # ←←← REGISTRAR (solo si no es el desplegable)
            self.left_buttons.append(b)

        # Botones comportamiento derecha
        self.tag_frame_right = tk.Frame(main_frame)
        pady_right = max(0, btn_frame_height - len(self.behavior_tags) * 32)
        self.tag_frame_right.pack(side="left", padx=5, pady=(pady_right, 60))
        for tag in self.behavior_tags:
            b = tk.Button(self.tag_frame_right, text=tag, width=6, bg=self.tag_inactive_bg)     
            b.pack(pady=2)
            b.bind("<Button-1>", lambda e, t=tag: self.behavior_click(t))
            self.behaviors[tag] = b

        # Botón flotante "Ajustes" (hijo de la ventana raíz, siempre al frente)
        self.adjust_btn = tk.Button(self, text="Ajustes", width=8, command=self.open_adjust_window)
        # Posicionar relativo al canvas: necesitamos coordenadas absolutas
        self.after(100, self._place_adjust_button)  # Esperar a que el layout se termine de dibujar

    # -------------------------------
    # Lista desplegable (popup) para el primer botón secundario
    # -------------------------------
    def show_secondary_dropdown(self, event):
        # Cerrar si ya está abierta
        if getattr(self, "dropdown_window", None) and tk.Toplevel.winfo_exists(self.dropdown_window):
            try:
                self.dropdown_window.destroy()
            except:
                pass
            self.dropdown_window = None
            return

        tags_extra = self.other_tags_list

        menu = tk.Toplevel(self)
        menu.wm_overrideredirect(True)
        menu.configure(bg="white", bd=1, relief="solid")

        widget = event.widget
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
        menu.geometry(f"+{x}+{y}")

        active_bg = "#cce6ff"
        normal_bg = "white"

        for tag in tags_extra:
            lbl = tk.Label(menu, text=tag, bg=normal_bg, width=18, anchor="w", padx=6, pady=3)
            lbl.pack(fill="x")
            lbl.bind("<Enter>", lambda e, w=lbl: w.config(bg=active_bg))
            lbl.bind("<Leave>", lambda e, w=lbl: w.config(bg=normal_bg))
            lbl.bind("<Button-1>", lambda e, t=tag: self._select_extra_tag(t, left=True))
            lbl.bind("<Button-3>", lambda e, t=tag: self._select_extra_tag(t, left=False))

        # Temporizador para cierre automático
        self._dropdown_close_timer = None

        def schedule_close():
            if self._dropdown_close_timer:
                self._dropdown_close_timer = None
            self._dropdown_close_timer = self.after(300, lambda: self._close_dropdown(menu))

        def cancel_close():
            if self._dropdown_close_timer:
                self.after_cancel(self._dropdown_close_timer)
                self._dropdown_close_timer = None

        # Vincular eventos de mouse a la ventana completa
        menu.bind("<Enter>", lambda e: cancel_close())
        menu.bind("<Leave>", lambda e: schedule_close())

        # También cerrar si se hace clic fuera (FocusOut sigue siendo útil)
        def on_focus_out(ev):
            self._close_dropdown(menu)

        menu.bind("<FocusOut>", on_focus_out)
        try:
            menu.focus_force()
        except:
            pass

        self.dropdown_window = menu

    def _close_dropdown(self, menu):
        """Cierra la lista desplegable de forma segura."""
        if getattr(self, "dropdown_window", None) is menu and tk.Toplevel.winfo_exists(menu):
            try:
                menu.destroy()
            except:
                pass
        self.dropdown_window = None
        if hasattr(self, '_dropdown_close_timer') and self._dropdown_close_timer:
            try:
                self.after_cancel(self._dropdown_close_timer)
            except:
                pass
            self._dropdown_close_timer = None

    def _select_extra_tag(self, tag, left=True):
        if getattr(self, "dropdown_window", None) and tk.Toplevel.winfo_exists(self.dropdown_window):
            try:
                self.dropdown_window.destroy()
            except:
                pass
            self.dropdown_window = None
        # No hay evento real en el menú desplegable → event=None (Alt no aplicable aquí)
        self.species_click(tag, left=left, event=None)

    def _place_adjust_button(self):
        """Posiciona el botón 'Ajustes' en la esquina superior derecha del canvas."""
        if not self.canvas.winfo_viewable():
            # Si aún no está visible, reintentar
            self.after(50, self._place_adjust_button)
            return

        # Obtener la posición absoluta del canvas en la pantalla
        canvas_x = self.canvas.winfo_rootx()
        canvas_y = self.canvas.winfo_rooty()

        # Posición relativa dentro de la ventana raíz
        rel_x = canvas_x - self.winfo_rootx() + 950  # 870px desde la izquierda del canvas
        rel_y = canvas_y - self.winfo_rooty() + 4    # 5px desde arriba

        # Asegurar que no se salga del canvas
        if rel_x < 0:
            rel_x = 10
        if rel_y < 0:
            rel_y = 10

        self.adjust_btn.place(x=rel_x, y=rel_y)
        self.adjust_btn.lift()

    # -------------------------------
    # Ventana secundaria de ajustes
    # -------------------------------
    def open_adjust_window(self):
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            self.adjust_window.lift()
            return

        win = tk.Toplevel(self)
        win.title("Ajustes de imagen")
        win_width = 360
        win_height = 500

        # Ocultar temporalmente para evitar parpadeo
        win.withdraw()

        # Calcular posición a la derecha de la ventana principal
        self.update_idletasks()
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        screen_width = self.winfo_screenwidth()

        win_x = main_x + main_width + 10
        win_y = main_y

        # Asegurar que no se salga de la pantalla
        if win_x + win_width > screen_width:
            win_x = screen_width - win_width - 10
        if win_y + win_height > self.winfo_screenheight():
            win_y = self.winfo_screenheight() - win_height - 50

        win.geometry(f"{win_width}x{win_height}+{win_x}+{win_y}")

        # Mostrar la ventana ya posicionada
        win.deiconify()

        self.adjust_window = win

        controls = [
            ("Brillo", "brightness", 0.0, 2.0, 0.1),
            ("Contraste", "contrast", 0.0, 2.0, 0.1),
            ("Nitidez", "sharpness", 0.0, 3.0, 0.1),
            ("Suavidad", "smoothness", 0.0, 5.0, 0.1),
            ("Reducción Ruido", "denoise", 0.0, 20.0, 1.0),
            ("Flatfield", "flatfield", 0.0, 1.0, 0.05)
        ]

        self.adjust_sliders = {}
        for i, (label_text, key, min_val, max_val, step) in enumerate(controls):
            tk.Label(win, text=label_text).pack(anchor="w", padx=10)
            s = tk.Scale(win, from_=min_val, to=max_val, resolution=step, orient="horizontal",
                         length=300,
                         command=lambda val, k=key: self.update_adjustment(k, float(val)))
            s.set(self.image_adjustments[key])
            s.pack(pady=5)
            self.adjust_sliders[key] = s

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Auto-mejorar", command=self.auto_adjust).pack(side="left", padx=3)
        tk.Button(btn_frame, text="Reset", command=self.reset_adjustments).pack(side="left", padx=3)
        tk.Button(btn_frame, text="Guardar", command=self.save_adjusted_image).pack(side="left", padx=3)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="left", padx=3)

    def update_adjustment(self, key, value):
        self.image_adjustments[key] = value
        self.show_frame()

    def auto_adjust(self):
        # Valores automáticos sugeridos
        self.image_adjustments.update({
            "brightness": 1.2,
            "contrast": 1.2,
            "sharpness": 1.5,
            "smoothness": 0.5,
            "denoise": 5.0,
            "flatfield": 0.1
        })
        # Actualizar sliders si la ventana está abierta
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            for key, slider in self.adjust_sliders.items():
                slider.set(self.image_adjustments[key])
        self.show_frame()

    def reset_adjustments(self):
        """Restablece los ajustes a los valores por defecto."""
        self.image_adjustments.update(DEFAULT_ADJUSTMENTS)
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            for key, slider in self.adjust_sliders.items():
                slider.set(self.image_adjustments[key])
        self.show_frame()

    def save_adjusted_image(self):
        """Guarda la imagen ajustada con sufijo '_adjusted'."""
        frames = self.get_current_frames()
        if not frames or self.current_frame_index >= len(frames):
            return

        frame_path = frames[self.current_frame_index]
        img = cv2.imread(frame_path)
        if img is None:
            return

        pil_img = self.apply_adjustments(img)
        base, ext = os.path.splitext(frame_path)
        adjusted_path = f"{base}_adjusted{ext}"
        pil_img.save(adjusted_path)

        # Opcional: notificación en consola
        print(f"Imagen ajustada guardada: {adjusted_path}")

        # Cerrar ventana tras guardar
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            self.adjust_window.destroy()

    def apply_adjustments(self, img):
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        # Brillo
        pil_img = ImageEnhance.Brightness(pil_img).enhance(self.image_adjustments["brightness"])
        # Contraste
        pil_img = ImageEnhance.Contrast(pil_img).enhance(self.image_adjustments["contrast"])
        # Nitidez
        pil_img = ImageEnhance.Sharpness(pil_img).enhance(self.image_adjustments["sharpness"])
        # Suavidad
        if self.image_adjustments["smoothness"] > 0:
            pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=self.image_adjustments["smoothness"]))
        # Flatfield
        if self.image_adjustments["flatfield"] > 0:
            arr = np.array(pil_img).astype(np.float32)
            arr = arr * (1 - self.image_adjustments["flatfield"]) + np.mean(arr) * self.image_adjustments["flatfield"]
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            pil_img = Image.fromarray(arr)
        # Reducción de ruido
        if self.image_adjustments["denoise"] > 0:
            arr = np.array(pil_img)
            arr = cv2.fastNlMeansDenoisingColored(arr, None,
                                                  h=self.image_adjustments["denoise"],
                                                  hColor=self.image_adjustments["denoise"],
                                                  templateWindowSize=7,
                                                  searchWindowSize=21)
            pil_img = Image.fromarray(arr)

        return pil_img

    def toggle_metadata_fields(self):
        if self.meta_frame.winfo_viewable():
            self.meta_frame.pack_forget()
            self.toggle_meta_btn.config(text="Metadatos")
        else:
            # Insertar justo antes del label de tags
            self.meta_frame.pack(before=self.label_frame, fill="x", pady=5)
            self.toggle_meta_btn.config(text="Ocultar")

    def update_checkbox(self):
        video_meta = self.video_dirs[self.current_video_index]
        video_meta["embed_metadata"] = self.embed_metadata_var.get()
        video_meta["xlsx"] = self.xlsx_var.get()
        self.save_metadata()

    def species_click(self, tag, left=True, event=None):
        is_alt = event and (event.state & 0x20000)  # Alt key (Windows/Linux)
        indices = range(len(self.video_dirs)) if is_alt else [self.current_video_index]
        was_added_to_current = False  # solo para navegación en modo individual

        # Leer el conteo actual solo si se va a agregar (toggle ON)
        current_count = self.count_var.get()
        if current_count < 1: # Validación básica
            print("Advertencia: El conteo debe ser al menos 1.")
            return

        for idx in indices:
            if not (0 <= idx < len(self.video_dirs)):
                continue
            video_meta = self.video_dirs[idx]
            tags_list = video_meta["tags"]
            species_counts = video_meta["species_counts"] # Accedemos al diccionario

            if tag in tags_list:
                # --- Modo: Quitar especie ---
                tags_list.remove(tag)
                species_counts.pop(tag, None) # Eliminar entrada de conteo si existe
            else:
                # --- Modo: Agregar especie ---
                tags_list.append(tag)
                species_counts[tag] = current_count # Guardar conteo para esta especie
                if not is_alt and idx == self.current_video_index:
                    was_added_to_current = True

        # Resetear el contador solo si se agregó una especie en modo individual
        # (Esto se mantiene para el flujo de navegación automática)
        if not is_alt and left and was_added_to_current:
            self.count_var.set(1)

        # --- AÑADIDO: Resetear el contador y quitar foco tras cualquier clic en botón de especie ---
        # Esto evita que el foco permanezca en el Spinbox
        if not is_alt: # Solo en modo individual
            self.count_var.set(1) # Siempre resetear a 1 tras clic en botón (izq o der)
            # Opcional: forzar foco en el canvas para que las flechas naveguen videos
            self.canvas.focus_set()

        self.save_metadata()

        # --- Navegación: solo si se agregó con clic izquierdo en modo individual ---
        if not is_alt and left and was_added_to_current:
            all_tagged = all(len(v.get("tags", [])) > 0 for v in self.video_dirs)
            if all_tagged:
                self._show_completion_dialog()
            elif self.current_video_index < len(self.video_dirs) - 1:
                self.current_video_index += 1
                self.current_frame_index = 0
                # El reset ya se hizo arriba, no aquí
        # --- Actualizar UI ---
        if not is_alt:
            self.show_frame()
        else:
            print(f"Toggle '{tag}' aplicado a {len(indices)} videos.")

    def _handle_copy(self, event=None):
        """Copia tags, behaviors e is_favorite del video actual al portapapeles interno."""
        if not self.video_dirs or self.current_video_index < 0:
            return
        
        current = self.video_dirs[self.current_video_index]
        self.clipboard_data = {
            "tags": current.get("tags", []).copy(),
            "behaviors": current.get("behaviors", []).copy(),
            "is_favorite": current.get("is_favorite", False)
        }
        print("✓ Metadatos de etiquetado copiados.")

    def _handle_paste(self, event=None):
        """Pega los datos del portapapeles interno en el video actual o en todos (si Alt está presionado)."""
        if self.clipboard_data is None:
            print("⚠️ Portapapeles vacío.")
            return

        is_alt = event and (event.state & 0x20000)  # Alt key
        indices = range(len(self.video_dirs)) if is_alt else [self.current_video_index]

        for idx in indices:
            if not (0 <= idx < len(self.video_dirs)):
                continue
            target = self.video_dirs[idx]
            target["tags"] = self.clipboard_data["tags"].copy()
            target["behaviors"] = self.clipboard_data["behaviors"].copy()
            target["is_favorite"] = self.clipboard_data["is_favorite"]

        self.save_metadata()

        if not is_alt:
            self.show_frame()  # Actualizar UI del actual
            print("✓ Metadatos pegados en el video actual.")
        else:
            print(f"✓ Metadatos pegados en {len(indices)} videos.")
    
    def clear_current_video(self):
        """Elimina todas las etiquetas, comportamientos y notas del video actual."""
        if not self.video_dirs:
            return
            
        video_meta = self.video_dirs[self.current_video_index]
        
        # Limpiar todos los campos editables
        video_meta["tags"] = []
        video_meta["behaviors"] = []
        video_meta["notes"] = ""
        video_meta["embed_metadata"] = False
        video_meta["xlsx"] = False
        video_meta["is_favorite"] = False  # También quitar favorito si lo deseas
        
        # Guardar inmediatamente
        self.save_metadata()
        
        # Actualizar la interfaz
        self.show_frame()
        
        # Restablecer controles
        self.count_var.set(1)
        self.embed_metadata_var.set(False)
        self.xlsx_var.set(False)

    def clear_all_videos_ask(self):
        """Muestra un diálogo de confirmación antes de limpiar toda la sesión."""
        from tkinter import messagebox
        
        if not self.video_dirs:
            return
            
        total = len(self.video_dirs)
        msg = f"¿Está seguro de que desea eliminar TODOS los tags, comportamientos y favoritos de los {total} videos de esta sesión?\n\nEsta acción no se puede deshacer."
        
        if messagebox.askyesno("Confirmar limpieza masiva", msg):
            self.clear_all_videos()

    def clear_all_videos(self):
        """Elimina tags, behaviors e is_favorite de todos los videos."""
        for video_meta in self.video_dirs:
            video_meta["tags"] = []
            video_meta["behaviors"] = []
            video_meta["is_favorite"] = False
        self.save_metadata()
        self.show_frame()  # Actualiza la UI del video actual
        print(f"✓ Todos los tags de la sesión han sido eliminados.")
    
    def _show_completion_dialog(self):
        """Muestra diálogo de finalización con dos opciones."""
        from tkinter import Toplevel, Button, Label
        
        dialog = Toplevel(self)
        dialog.title("Sesión completada")
        dialog.geometry("300x120")
        dialog.transient(self)
        dialog.focus_set()
        
        Label(dialog, text="¡Todos los videos han sido etiquetados!", pady=10).pack()
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        def add_more_videos():
            dialog.destroy()
            self.destroy()
            # Abrir gui_inicial en modo append
            import os
            import sys
            import subprocess
            gui_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "gui_inicial.py")
            try:
                subprocess.Popen([sys.executable, gui_path, "--session_id", self.session_id])
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Error", f"No se pudo abrir GUI Inicial:\n{e}")
                # Fallback: volver a main
                try:
                    from main import MainApp
                    MainApp().mainloop()
                except Exception:
                    pass
        
        def finish_session():
            dialog.destroy()
            self.destroy()
            try:
                from main import MainApp
                MainApp().mainloop()
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Error", f"No se pudo volver al menú principal:\n{e}")
        
        Button(btn_frame, text="Agregar más videos", command=add_more_videos, bg="#4CAF50", fg="white").pack(side="left", padx=5)
        Button(btn_frame, text="Finalizar", command=finish_session, bg="#f44336", fg="white").pack(side="left", padx=5)
        
        # ←←← NUEVO: Asegurar que la ventana sea visible antes de grab_set
        dialog.update_idletasks()  # Fuerza a que la ventana se dibuje
        dialog.grab_set()          # Ahora sí funciona
        # →→→
        
    def behavior_click(self, tag):
        video_meta = self.video_dirs[self.current_video_index]
        if tag in video_meta["behaviors"]:
            video_meta["behaviors"].remove(tag)
        else:
            video_meta["behaviors"].append(tag)
        self.save_metadata()
        self.show_frame()

    def save_metadata(self):
        # Guardar en el archivo de sesión (actual)
        with metadata_lock:
            video_meta = self.video_dirs[self.current_video_index]
            # Guardar notas
            video_meta["notes"] = self.notes_text.get("1.0", "end-1c")
            # Guardar metadatos editables (aunque el frame esté oculto)
            for key, var in self.metadata_vars.items():
                video_meta[key] = var.get()
            video_meta["is_excluded"] = self.video_dirs[self.current_video_index].get("is_excluded", False)
            # Escribir todo a disco
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self.video_dirs, f, indent=4, ensure_ascii=False)
        # Actualizar archivo consolidado global
        self.update_consolidated_metadata(video_meta)
        
    def update_consolidated_metadata(self, updated_video_meta):
        """Actualiza el archivo consolidado global con los metadatos del video."""
        consolidated_dir = os.path.join(self.output_folder, "consolidated")
        os.makedirs(consolidated_dir, exist_ok=True)
        consolidated_path = os.path.join(consolidated_dir, "all_sessions_metadata.json")
        # Cargar consolidado existente o crear lista vacía
        if os.path.exists(consolidated_path):
            with open(consolidated_path, "r", encoding="utf-8") as f:
                try:
                    consolidated = json.load(f)
                except json.JSONDecodeError:
                    print(f"⚠️ Archivo consolidado corrupto, creando nuevo: {consolidated_path}")
                    consolidated = []
        else:
            consolidated = []
        # Buscar entrada por video_path (clave única)
        video_path = updated_video_meta["video_path"]
        found = False
        for entry in consolidated:
            if entry.get("video_path") == video_path:
                # Actualizar campos editables
                for key in [
                    "tags", "behaviors", "notes", "embed_metadata", "xlsx",
                    "session_id", "site", "subsite", "camera", "operator",
                    "recorded_at", "frames_folder", "video_hash",
                    "is_excluded" # <-- AÑADIR ESTA CLAVE AQUÍ -->
                ]:
                    if key in updated_video_meta:
                        entry[key] = updated_video_meta[key]
                found = True
                break
        if not found:
            # Añadir nuevo video (poco común, pero posible)
            # Asegurar que is_excluded también se copie si es nuevo
            updated_video_meta.setdefault("is_excluded", False)
            consolidated.append(updated_video_meta.copy())
        # Guardar
        with open(consolidated_path, "w", encoding="utf-8") as f:
            json.dump(consolidated, f, indent=4, ensure_ascii=False)

    def get_current_frames(self):
        video_meta = self.video_dirs[self.current_video_index]
        frames = []
        
        # 1. Fotos originales (si existen) → máxima información, van primero
        original_photos = video_meta.get("original_photos", [])
        frames.extend([p for p in original_photos if p and os.path.exists(p)])
        
        # 2. Tops generados → ya ordenados: top_00.jpg es el de mayor movimiento
        tops = video_meta.get("tops", [])
        valid_tops = [p for p in tops if p and os.path.exists(p)]
        
        if valid_tops:
            # El mejor top (índice 0) va inmediatamente después de las originales
            frames.append(valid_tops[0])
            # Luego el resto de tops, en orden
            frames.extend(valid_tops[1:])
        
        return frames
  
    def show_frame(self):
        try:
            # ←←← NUEVO: refresco de metadatos con protección
            self.reload_current_video_from_disk()
            # →→→ FIN NUEVO
            
            video_meta = self.video_dirs[self.current_video_index] if self.video_dirs else {}
            if not video_meta or "video_path" not in video_meta:
                self._show_empty_state("Sin datos")
                return

            frames = self.get_current_frames()
            if not frames:
                status = video_meta.get("status", "pending")
                if status == "pending":
                    pending_before = sum(1 for v in self.video_dirs[:self.current_video_index] 
                                        if v.get("status") == "pending")
                    total_pending = sum(1 for v in self.video_dirs if v.get("status") == "pending")
                    msg = f"En cola ({pending_before + 1}/{total_pending})"
                elif status == "error":
                    msg = "Error de procesamiento"
                else:
                    msg = "Procesando video..."
                self._show_empty_state(msg)
                return

            if self.current_frame_index >= len(frames):
                self.current_frame_index = len(frames) - 1
            frame_path = frames[self.current_frame_index]
            img = cv2.imread(frame_path)
            if img is None:
                self._show_empty_state("Error al cargar frame")
                return
            # Mostrar nombre útil según el tipo de entrada
            if video_meta.get("is_photo"):
                if video_meta.get("is_burst"):
                    label_text = f"Ráfaga: {video_meta.get('fecha_prefix', 'unknown')}"
                else:
                    img_path = video_meta.get("image_path") or (video_meta.get("original_photos", [None])[0])
                    label_text = f"Foto: {os.path.basename(img_path) if img_path else 'unknown'}"
            else:
                folder_name = video_meta.get("frames_folder", "")
                label_text = f"Video: {folder_name}"

            self.video_label.config(text=label_text)
            self.counter_label.config(
                text=f"{self.current_video_index + 1}/{len(self.video_dirs)} | {self.current_frame_index + 1}/{len(frames)}")

            # Aplicar ajustes de imagen antes de la máscara
            img_pil = self.apply_adjustments(img)
            img = np.array(img_pil)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # Máscara roja con alpha → solo para frames generados (no para fotos originales)
            if self.show_mask and (not self.blink_mode or self.blink_state):
                current_frame_path = frames[self.current_frame_index]
                original_photos_set = set(video_meta.get("original_photos", []))
                if current_frame_path not in original_photos_set:
                    mask_path = video_meta.get("mask")
                    if mask_path and os.path.exists(mask_path):
                        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                        if mask is not None:
                            mask_resized = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                            alpha = (mask_resized.astype(np.float32) / 255.0) * 0.6
                            overlay = np.zeros_like(img, dtype=np.float32)
                            overlay[:, :, 2] = 255
                            img = img.astype(np.float32)
                            img = (1 - alpha[:, :, None]) * img + alpha[:, :, None] * overlay
                            img = img.astype(np.uint8)

            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            img.thumbnail((912, 513))
            tk_img = ImageTk.PhotoImage(img)
            self.tk_imgs["current"] = tk_img
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=tk_img)

            tags_especie = ", ".join(video_meta.get("tags", [])) or "ninguno"
            tags_behav = ", ".join(video_meta.get("behaviors", [])) or "ninguno"
            self.label_frame.config(
                text=f"Tags especie: {tags_especie}\nTags comportamiento: {tags_behav}"
            )

            # ←←← ACTUALIZACIÓN UNIFICADA DE BOTONES DE TAGS →→→
            if not self.video_dirs:
                current_tags = set()
                current_behaviors = set()
            else:
                current_item = self.video_dirs[self.current_video_index]
                current_tags = set(current_item.get("tags", []))
                current_behaviors = set(current_item.get("behaviors", []))

            # --- Especies: desactivar todos, luego activar y actualizar texto los presentes ---
            for tag, btn in self.species_buttons.items(): # Iteramos clave-valor
                if btn.winfo_exists():
                    # <-- MODIFICACIÓN: Usar el color inactivo general o específico para botones principales -->
                    # Determinar color base inactivo
                    if tag in self.species_tags[:2]: # Si es uno de los dos primeros
                         # Usar el color inactivo definido para botones principales
                         # Obtenemos el color específico según el tag (posición en la lista)
                         if tag == self.species_tags[0]:
                             base_inactive_color = self.colors_cfg.get("main_button_1_inactive", "#FFD700") # Debe coincidir con el valor en build_layout
                         else: # tag == self.species_tags[1]
                             base_inactive_color = self.colors_cfg.get("main_button_2_inactive", "#87CEEB") # Debe coincidir con el valor en build_layout
                    else:
                         # Usar el color inactivo general
                         base_inactive_color = self.tag_inactive_bg
                    # <-- FIN MODIFICACIÓN -->
                    btn.config(bg=base_inactive_color, text=tag) # Resetear a nombre base y color inactivo correspondiente
            # --- Activar los que están en los tags actuales ---
            for tag in current_tags:
                if tag in self.species_buttons:
                    btn = self.species_buttons[tag]
                    if btn.winfo_exists():
                        # Aplicar color activo a cualquier botón de especie presente
                        btn.config(bg=self.tag_active_bg)
                        # ... (lógica de conteo) ...
                        # Verificar si hay un conteo específico para esta especie
                        current_species_counts = self.video_dirs[self.current_video_index].get("species_counts", {})
                        count = current_species_counts.get(tag, 1) # Usar 1 como fallback si no está en species_counts
                        btn.config(text=f"{tag} ({count})") # Actualizar texto con conteo
            # --- Comportamientos: desactivar todos, luego activar los presentes ---
            for btn in self.behaviors.values():
                if btn.winfo_exists():
                    btn.config(bg=self.tag_inactive_bg)
            for tag in current_behaviors:
                if tag in self.behaviors:
                    btn = self.behaviors[tag]
                    if btn.winfo_exists():
                        btn.config(bg=self.tag_active_bg)
            # →→→ FIN ←←←
                        # Verificar si hay un conteo específico para esta especie
                        current_species_counts = self.video_dirs[self.current_video_index].get("species_counts", {})
                        count = current_species_counts.get(tag, 1) # Usar 1 como fallback si no está en species_counts
                        btn.config(text=f"{tag} ({count})") # Actualizar texto con conteo
            # --- Comportamientos: desactivar todos, luego activar los presentes ---
            for btn in self.behaviors.values():
                if btn.winfo_exists():
                    btn.config(bg=self.tag_inactive_bg)
            for tag in current_behaviors:
                if tag in self.behaviors:
                    btn = self.behaviors[tag]
                    if btn.winfo_exists():
                        btn.config(bg=self.tag_active_bg)
            # →→→ FIN ←←←
                        # Verificar si hay un conteo específico para esta especie
                        current_species_counts = self.video_dirs[self.current_video_index].get("species_counts", {})
                        count = current_species_counts.get(tag, 1) # Usar 1 como fallback si no está en species_counts
                        btn.config(text=f"{tag} ({count})") # Actualizar texto con conteo
            # --- Comportamientos: desactivar todos, luego activar los presentes ---
            for btn in self.behaviors.values():
                if btn.winfo_exists():
                    btn.config(bg=self.tag_inactive_bg)
            for tag in current_behaviors:
                if tag in self.behaviors:
                    btn = self.behaviors[tag]
                    if btn.winfo_exists():
                        btn.config(bg=self.tag_active_bg)
            # →→→ FIN ←←←
                        # Verificar si hay un conteo específico para esta especie
                        current_species_counts = self.video_dirs[self.current_video_index].get("species_counts", {})
                        count = current_species_counts.get(tag, 1) # Usar 1 como fallback si no está en species_counts
                        btn.config(text=f"{tag} ({count})") # Actualizar texto con conteo

            # --- Comportamientos: desactivar todos, luego activar los presentes ---
            for btn in self.behaviors.values():
                if btn.winfo_exists():
                    btn.config(bg=self.tag_inactive_bg)
            for tag in current_behaviors:
                if tag in self.behaviors:
                    btn = self.behaviors[tag]
                    if btn.winfo_exists():
                        btn.config(bg=self.tag_active_bg)
            # →→→ FIN ←←←

            self.notes_text.delete("1.0", "end")
            self.notes_text.insert("1.0", video_meta.get("notes", ""))
            self.embed_metadata_var.set(video_meta.get("embed_metadata", False))
            self.xlsx_var.set(video_meta.get("xlsx", False))
            
            # ←←← NUEVO: actualizar favorito con protección
            try:
                self.update_favorite_button()
            except Exception:
                pass
            # →→→ FIN NUEVO
            # ←←← NUEVO: actualizar exclusión con protección
            try:
                self.update_exclude_button()
            except Exception:
                pass
            # →→→ FIN NUEVO
                        
        except Exception as e:
            print(f"Error en show_frame: {e}")
            self._show_empty_state("Error al mostrar frame")
      
    # Navegación
    def next_frame(self):
        frames = self.get_current_frames()
        if frames:
            self.current_frame_index = min(self.current_frame_index + 1, len(frames) - 1)
            self.show_frame()

    def prev_frame(self):
        frames = self.get_current_frames()
        if frames:
            self.current_frame_index = max(self.current_frame_index - 1, 0)
            self.show_frame()

    def next_video(self):
        if self.current_video_index < len(self.video_dirs) - 1:
            self.current_video_index += 1
            self.current_frame_index = 0
            self.count_var.set(1) # <-- Asegura reset
            self.canvas.focus_set() # <-- Asegura pérdida de foco del Spinbox
            self.show_frame()

    def prev_video(self):
        if self.current_video_index > 0:
            self.current_video_index -= 1
            self.current_frame_index = 0
            self.count_var.set(1) # <-- Asegura reset
            self.canvas.focus_set() # <-- Asegura pérdida de foco del Spinbox
            self.show_frame()

    # Toggle máscara
    def toggle_mask(self, event=None):
        self.show_mask = not self.show_mask
        self.show_frame()

    def toggle_blink_mode(self, event=None):
        self.blink_mode = not self.blink_mode

    def blink_mask(self):
        if self.blink_mode:
            self.blink_state = not self.blink_state
            self.show_frame()
        self._blink_after_id = self.after(self.blink_interval, self.blink_mask)

    def _cancel_blink_timer(self):
        if hasattr(self, '_blink_after_id'):
            try:
                self.after_cancel(self._blink_after_id)
            except:
                pass

    def destroy(self):
        self._cancel_blink_timer()
        super().destroy()

    # Reproducción de video completo
    def play_video(self, event=None):
        video_meta = self.video_dirs[self.current_video_index]
        video_path = video_meta.get("video_path", "")
        if video_path and os.path.exists(video_path):
            open_video_default(video_path)
        else:
            # En modo foto, abrir la imagen actual en el visor predeterminado
            frames = self.get_current_frames()
            if frames and self.current_frame_index < len(frames):
                current_img = frames[self.current_frame_index]
                if os.path.exists(current_img):
                    open_video_default(current_img)  # reutiliza la misma función (funciona para imágenes)


    # Favoritos
    def toggle_favorite(self):
        """Alterna el estado de favorito del video actual."""
        if not self.video_dirs:
            return
            
        video_meta = self.video_dirs[self.current_video_index]
        current = video_meta.get("is_favorite", False)
        video_meta["is_favorite"] = not current
        self.save_metadata()
        self.update_favorite_button()

    def update_favorite_button(self):
        """Actualiza el ícono del botón de favorito según el estado actual."""
        if not hasattr(self, 'favorite_button') or not self.favorite_button.winfo_exists():
            return  # El botón aún no existe o fue destruido
            
        if not self.video_dirs:
            is_fav = False
        else:
            is_fav = self.video_dirs[self.current_video_index].get("is_favorite", False)
        
        text = "★" if is_fav else "☆"
        self.favorite_button.config(text=text)
 
    def toggle_exclude(self):
        """Alterna el estado de exclusión del video actual."""
        if not self.video_dirs:
            return
        video_meta = self.video_dirs[self.current_video_index]
        current = video_meta.get("is_excluded", False)
        video_meta["is_excluded"] = not current
        self.save_metadata()
        self.update_exclude_button()

    def update_exclude_button(self):
        """Actualiza el ícono del botón de exclusión según el estado actual."""
        if not hasattr(self, 'exclude_button') or not self.exclude_button.winfo_exists():
            return  # El botón aún no existe o fue destruido
        if not self.video_dirs:
            is_excl = False
        else:
            is_excl = self.video_dirs[self.current_video_index].get("is_excluded", False)
        text = "🚫" if is_excl else "☐" # Puedes cambiar "☐" por otro símbolo para "no excluido"
        # Opcional: Cambiar color del botón según estado
        bg_color = self.colors_cfg.get("exclude_button_active_bg", "#ffebee") if is_excl else self.colors_cfg.get("exclude_button_bg", "#ffffff")
        fg_color = self.colors_cfg.get("exclude_button_active_fg", "#d32f2f") if is_excl else self.colors_cfg.get("exclude_button_fg", "#000000")
        self.exclude_button.config(text=text, bg=bg_color, fg=fg_color)

    def _show_empty_state(self, message):
        """Muestra un mensaje en el canvas cuando no hay frames."""
        self.label_frame.config(text=message)
        self.canvas.delete("all")
        self.video_label.config(text="")
        self.counter_label.config(text="")

# -------------------------------
def run_gui_tagger():
    app = DynamicTagger()
    app.mainloop()


# -------------------------------
if __name__ == "__main__":
    run_gui_tagger()