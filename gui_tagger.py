import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageEnhance, ImageFilter
import cv2, os, glob, subprocess, threading, json
import numpy as np
import uuid
import time

from datetime import datetime
from config_utils import (
    load_config, save_config,
    list_tagger_configs, load_tagger_config, save_tagger_config,
    apply_tagger_config,
    get_template_tagger_config, get_tagger_configs_dir,
    search_taxa_local, search_taxa_gbif,
    get_available_regions, load_region_species, get_default_region_id, set_default_region_id,
    get_recent_configs, update_recent_configs
)
from config_manager import ConfigManager

metadata_lock = threading.RLock()  # 🔒 FIX BUG-002: Use RLock for nested locking

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

    def __init__(self, metadata_path=None, session_id=None, scientific_mode=False, correction_mode=False):
        super().__init__()
        self.scientific_mode = scientific_mode
        self.correction_mode = correction_mode
        self.config_data = load_config()
        gui_cfg = self.config_data.get("GUI_Tagger", {})
        
        # 🔹 CRÍTICO: Usar SOLO last_used_configs[0] como última configuración
        from config_utils import get_recent_configs
        recent_configs = get_recent_configs(self.config_data)
        if recent_configs and len(recent_configs) > 0:
            last_config_path = recent_configs[0]['path']
            try:
                tagger_cfg_data = load_tagger_config(last_config_path)
                apply_tagger_config(tagger_cfg_data, self.config_data)
                gui_cfg = self.config_data.get("GUI_Tagger", {})
                self.active_tagger_config_path = last_config_path
                self.active_tagger_config_name = tagger_cfg_data.get("_metadata", {}).get("name", "")
            except Exception as e:
                print(f"⚠️ Error cargando última config: {e}")
                self.active_tagger_config_path = ""
                self.active_tagger_config_name = ""
        else:
            self.active_tagger_config_path = ""
            self.active_tagger_config_name = ""
        
        # 🔒 FIX: Auto-refresh timer for pending videos
        self._auto_refresh_id = None
        self._pending_videos_exist = False
        
        # 🔒 FIX: Cargar listas de tags UNA SOLA VEZ (sin duplicados)
        self.species_tags = gui_cfg.get("species_tags", [])
        self.secondary_tags = gui_cfg.get("secondary_tags", [])
        self.behavior_tags = gui_cfg.get("behavior_tags", [])
        self.other_tags_list = gui_cfg.get("other_tags_list", [
            "Zorro", "Puma", "Tapir", "Gato montés", "Venado",
            "Ñandú", "Coipo", "Jaguar", "Carpincho", "Humano"
        ])
        # 🔒 NUEVO: Opcionales (categorías independientes, máx 6)
        self.optional_tags = gui_cfg.get("optional_tags", [])
        self.taxon_map = gui_cfg.get("taxon_map", {})
        
        # 🔒 FIX: Cargar colors, labels y buttons (faltaban en la versión anterior)
        colors = gui_cfg.get("colors", {})
        labels_cfg = gui_cfg.get("labels", {})
        buttons_cfg = gui_cfg.get("buttons", {})
        
        # 🌿 BIOGEOGRAPHIC REGION SYSTEM
        self.current_region_id = get_default_region_id(self.config_data)
        self.current_region_species = load_region_species(self.current_region_id)
        self.available_regions = get_available_regions()
        print(f"🌿 Loaded region: {self.current_region_id} ({len(self.current_region_species)} species)")
        
        # 🔄 RECENT CONFIGS
        self.recent_configs = get_recent_configs(self.config_data)
        mode_suffix = " [Modo Científico]" if scientific_mode else ""
        self.title(f"{gui_cfg.get('title', 'Dynamic Video Tagger')}{mode_suffix}")
        self.geometry(gui_cfg.get("geometry", "1300x750"))
        self.output_folder = self.config_data["General"]["output_folder"]
        if metadata_path is None:
            metadata_path = os.path.join(self.output_folder, "videos_metadata.json")
        self.metadata_path = metadata_path
        self.video_dirs = []
        self.session_id = session_id if session_id else str(uuid.uuid4())
        self.load_metadata(self.metadata_path)
        for v in self.video_dirs:
            if "session_id" not in v: v["session_id"] = self.session_id
        self.current_video_index = 0
        self.current_frame_index = 0
        self.mask_mode = 1  # 0: Oculta | 1: Constante | 2: Titilante
        self.mask_colors = [
            (255, 0, 0),    # Rojo
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 255, 0),  # Amarillo
            (0, 255, 0)     # Verde
        ]
        self.mask_color_index = 0
        self.blink_state = True
        self.blink_interval = 500
        self.tk_imgs = {}
        self.count_var = tk.IntVar(value=1)
        self.embed_metadata_var = tk.BooleanVar(value=False)
        self.xlsx_var = tk.BooleanVar(value=False)
        self.metadata_vars = {
            "Temp": tk.StringVar(), "Fase Lunar": tk.StringVar(), "Clima": tk.StringVar(),
            "Corrección Horaria": tk.StringVar(), "Deployment": tk.StringVar(), "Altura": tk.StringVar()
        }
        self.image_adjustments = DEFAULT_ADJUSTMENTS.copy()
        self.adjust_window = None
        self.adjust_sliders = {}
        self.clipboard_data = None
        self._has_unsaved_changes = False
        self.main_buttons = []
        self.left_buttons = []
        self.behaviors = {}
        self.species_buttons = {}
        self.dropdown_window = None
        
        # 🔒 FIX: Asignar colors, labels y buttons (ahora sí están definidos)
        self.labels_cfg = labels_cfg
        self.colors_cfg = colors
        self.buttons_cfg = buttons_cfg
        
        self.tag_active_bg = self.colors_cfg.get("tag_active", "#90ee90")
        self.tag_inactive_bg = self.colors_cfg.get("tag_inactive", "#f0f0f0")
        self.species_active_bg = self.colors_cfg.get("species_active", "#90ee90")
        self.species_inactive_bg = self.colors_cfg.get("species_inactive", "#f0f0f0")
        self.behavior_active_bg = self.colors_cfg.get("behavior_active", "#ffff99")
        self.behavior_inactive_bg = self.colors_cfg.get("behavior_inactive", "#f0f0f0")
        
        self.build_layout()
        self.bind("<space>", self.handle_mask_key)
        self.bind("<Shift-space>", self.handle_mask_key)
        self.bind("<Left>", lambda e: self.prev_frame())
        self.bind("<Right>", lambda e: self.next_frame())
        self.bind("<Down>", lambda e: self.prev_video())
        self.bind("<Up>", lambda e: self.next_video())
        self.bind("<Control-c>", self._handle_copy)
        self.bind("<Control-v>", self._handle_paste)
        self.after(100, self.show_frame)
        self.after(self.blink_interval, self.blink_mask)
        self.after(1000, self._auto_refresh_pending)

    # -----------------------------------------------------------------
    # LAYOUT DE 4 COLUMNAS
    # -----------------------------------------------------------------
    def handle_mask_key(self, event=None):
        """Espacio: cambia modo | Shift+Espacio: cambia color"""
        is_shift = False
        if event:
            # 0x1 es la máscara de tecla Shift en Tkinter
            is_shift = bool(event.state & 0x1)

        if is_shift:
            # 🔹 Cambiar color (Shift + Espacio)
            self.mask_color_index = (self.mask_color_index + 1) % len(self.mask_colors)
            color_names = ["Rojo", "Magenta", "Cyan", "Amarillo", "Verde"]
            print(f"🎨 Color máscara: {color_names[self.mask_color_index]}")
        else:
            # 🔹 Cambiar modo (Espacio solo)
            self.mask_mode = (self.mask_mode + 1) % 3
            mode_names = ["Ocultar", "Constante", "Titilante"]
            print(f"👁️ Máscara: {mode_names[self.mask_mode]}")

        self.show_frame()

    def build_layout(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        # ================= COLUMNA 1: HERRAMIENTAS =================
        col1 = tk.Frame(main_frame, bd=1, relief="sunken", width=160)
        col1.pack(side="left", fill="y", padx=(0, 5))
        col1.pack_propagate(False)
        tk.Checkbutton(col1, text="Embed metadata", variable=self.embed_metadata_var,
                    command=self.update_checkbox).pack(pady=2, padx=5, anchor="w")
        tk.Checkbutton(col1, text=".xlsx", variable=self.xlsx_var,
                    command=self.update_checkbox).pack(pady=2, padx=5, anchor="w")
        tk.Frame(col1, height=10).pack()
        # 🔧 CONFIG MANAGER
        self.config_btn = tk.Button(col1, text="⚙️ Config", command=self.open_config_manager,
                                    bg="#4CAF50", fg="black", font=("Arial", 9, "bold"))
        self.config_btn.pack(fill="x", pady=2, padx=5)
        # 💾 BOTÓN DE GUARDADO (OCULTO POR DEFECTO, APARECE SOLO SI HAY CAMBIOS)
        self.save_config_btn = tk.Button(col1, text="💾 Guardar Config", command=self._prompt_save_config,
                                        bg="#FF9800", fg="white", font=("Arial", 9, "bold"))
        self.save_config_btn.pack_forget()  # Oculto inicialmente
        # 🔄 RECENT CONFIGS DROPDOWN (SIEMPRE VISIBLE)
        tk.Label(col1, text="Recientes:", font=("Arial", 8, "bold")).pack(anchor="w", padx=5, pady=(5, 0))
        self.recent_combo = ttk.Combobox(col1, state="readonly", font=("Arial", 8), width=16)
        # 🔹 NUEVO: Poner configuración actual PRIMERO
        current_config_path = self.active_tagger_config_path
        current_config_name = self.active_tagger_config_name
        # Si hay configuración actual, ponerla primero
        if current_config_path and current_config_name:
            # Crear lista con config actual primero
            reordered_configs = [{
                'path': current_config_path,
                'name': current_config_name,
                'country_id': '',
                'country': '',
                'region': '',
                'region_id': ''
            }]
            # Agregar las demás (sin duplicar la actual)
            for cfg in self.recent_configs:
                if cfg['path'] != current_config_path:
                    reordered_configs.append(cfg)
            self.recent_configs = reordered_configs
        elif not self.recent_configs:
            # Si no hay recientes ni actual, usar Base
            base_path = os.path.join(get_tagger_configs_dir(), "base.json")
            if os.path.exists(base_path):
                self.recent_configs = [{
                    'path': base_path,
                    'name': 'Base',
                    'country_id': 'argentina',
                    'country': 'Argentina',
                    'region': 'Base',
                    'region_id': 'base'
                }]
        # Formato: SOLO nombre (sin país)
        # 🔄 DROPDOWN DE CONFIGURACIONES (limpio y delega la lógica)
        tk.Label(col1, text="Recientes: ", font=("Arial", 8, "bold")).pack(anchor="w", padx=5, pady=(5, 0))
        self.recent_combo = ttk.Combobox(col1, state="readonly", font=("Arial", 8), width=16)
        self.recent_combo.pack(fill="x", pady=2, padx=5)
        self.recent_combo.bind("<<ComboboxSelected>>", self.on_recent_config_selected)
        # Poblado inicial (llamar DESPUÉS de que exista el widget)
        self.after(150, self._scan_and_populate_dropdown)
        self.adjust_btn = tk.Button(col1, text="Ajustes", command=self.open_adjust_window)
        self.adjust_btn.pack(fill="x", pady=2, padx=5)
        tk.Frame(col1, height=5).pack()
        self.meta_preview = tk.Text(col1, height=10, width=18, wrap="word",
                                    state="disabled", bd=1, relief="sunken",
                                    bg="#e8e8e8", font=("Arial", 9))
        self.meta_preview.pack(fill="x", padx=5, pady=2)
        self.meta_btn = tk.Button(col1, text="Metadatos", command=self.open_metadata_editor)
        self.meta_btn.pack(fill="x", pady=2, padx=5)
        # ================= COLUMNA 2: CANVAS + CONTROLES =================
        col2 = tk.Frame(main_frame)
        col2.pack(side="left", fill="both", expand=True, padx=5)
        # 🔹 BARRA SUPERIOR CON NAVEGACIÓN
        top_info = tk.Frame(col2)
        top_info.pack(fill="x", pady=(0, 2))
        # Favorito y Exclusión (izquierda extrema)
        self.favorite_button = tk.Button(top_info, text="☆", command=self.toggle_favorite)
        self.favorite_button.pack(side="left", padx=2)
        self.exclude_button = tk.Button(top_info, text="☐", command=self.toggle_exclude)
        self.exclude_button.pack(side="left", padx=2)
        # Nombre del video (ocupa espacio disponible)
        self.video_label = tk.Label(top_info, text="", anchor="w", font=("Arial", 10))
        self.video_label.pack(side="left", fill="x", expand=True, padx=5)
        # Navegación Videos (▲ / ▼)
        self.prev_video_btn = tk.Button(top_info, text="▲", width=2, command=self.next_video)
        self.prev_video_btn.pack(side="left", padx=1)
        self.next_video_btn = tk.Button(top_info, text="▼", width=2, command=self.prev_video)
        self.next_video_btn.pack(side="left", padx=1)
        # Contador de Videos
        self.video_counter_label = tk.Label(top_info, text="Video 0/0", anchor="w", font=("Arial", 9))
        self.video_counter_label.pack(side="left", padx=5)
        # Navegación Frames (◀ / ▶)
        self.prev_frame_btn = tk.Button(top_info, text="◀", width=2, command=self.prev_frame)
        self.prev_frame_btn.pack(side="left", padx=1)
        self.next_frame_btn = tk.Button(top_info, text="▶", width=2, command=self.next_frame)
        self.next_frame_btn.pack(side="left", padx=1)
        # Contador de Frames
        self.frame_counter_label = tk.Label(top_info, text="Frame 0/0", anchor="e", font=("Arial", 9))
        self.frame_counter_label.pack(side="left", padx=5)
        # Botón "Ver pendientes" en la misma línea
        self.pending_btn = tk.Button(top_info, text="📊 Pendientes: 0", command=self._show_untagged_videos, 
                                    bg="#e0e0e0", font=("Arial", 9))
        self.pending_btn.pack(side="left", padx=10)
        # Canvas (más angosto para dar espacio a columnas 3 y 4)
        self.canvas_frame = tk.Frame(col2)
        self.canvas_frame.pack(fill="both", expand=True, pady=2)
        self.canvas = tk.Canvas(self.canvas_frame, width=650, height=513, bg="black")
        self.canvas.pack(fill="both", expand=True)
        # Mouse navigation bindings
        self.canvas.bind("<Double-Button-1>", self.play_video)  # Keep existing double-click
        self.canvas.bind("<Button-1>", self._handle_canvas_click)  # Zone-based navigation
        self.canvas.bind("<Button-3>", lambda e: self.next_frame())  # Right-click = next frame
        self.canvas.bind("<MouseWheel>", self._handle_canvas_scroll)  # Windows/macOS
        self.canvas.bind("<Button-4>", self._handle_canvas_scroll)  # Linux scroll up
        self.canvas.bind("<Button-5>", self._handle_canvas_scroll)  # Linux scroll down
        # Debounce timer for mouse wheel
        self._scroll_debounce_id = None
        # Controles inferiores (Limpiar, Botones Especie, Contador)
        control_frame = tk.Frame(col2)
        control_frame.pack(fill="x", pady=(5, 0))
        self.clear_btn = tk.Button(control_frame, text="Limpiar", width=10, height=2,
                                bg=self.colors_cfg.get("clear_button_bg", "#ff9999"))
        self.clear_btn.bind("<Button-1>", lambda e: self.clear_current_video())
        self.clear_btn.bind("<Button-3>", lambda e: self.clear_all_videos_ask())
        self.clear_btn.pack(side="left", padx=5)
        # 🔹 Botones principales + contador
        buttons_container = tk.Frame(control_frame, bg="#f5f5f5")
        buttons_container.pack(side="left", padx=5, fill="both", expand=True)
        self.tag_frame_bottom = tk.Frame(buttons_container, bg="#f5f5f5")
        self.tag_frame_bottom.pack(side="left", padx=0)
        self.main_buttons = []
        self.species_buttons = {}
        # 🔹 NUEVOS COLORES: Más variados y diferenciados - Forzar colores vivos
        c1 = "#FF6B6B"  # Rojo vibrante
        c2 = "#4ECDC4"  # Turquesa vibrante
        for i, tag in enumerate(self.species_tags[:2]):
            bg = c1 if i == 0 else c2
            b = tk.Button(self.tag_frame_bottom, text=tag, width=28, height=3, bg=bg, fg="black", font=("Arial", 11, "bold"))
            b.pack(side="left", padx=4)
            b.bind("<Button-1>", lambda e, t=tag: self.species_click(t, left=True, event=e))
            b.bind("<Button-3>", lambda e, t=tag: self.species_click(t, left=False, event=e))
            self.main_buttons.append(b)
            self.species_buttons[tag] = b
        # 🔹 Contador a la derecha
        counter_frame = tk.Frame(buttons_container, bg="#f5f5f5")
        counter_frame.pack(side="left", padx=15, fill="y")
        tk.Label(counter_frame, text=self.labels_cfg.get("count", "Cantidad:"), bg="#f5f5f5", font=("Arial", 10, "bold")).pack(side="top")
        self.count_dropdown = ttk.Combobox(counter_frame, textvariable=self.count_var, width=5, state="readonly", font=("Arial", 12))
        self.count_dropdown['values'] = list(range(1, 10))
        self.count_dropdown.current(0)
        self.count_dropdown.pack(side="top", pady=3)
        # ================= COLUMNA 3: COMPORTAMIENTO + SECUNDARIOS =================
        self.col3 = tk.Frame(main_frame, bd=1, relief="sunken", width=170, bg="#fff3e0")
        self.col3.pack(side="left", fill="y", padx=5)
        self.col3.pack_propagate(False)
        tk.Label(self.col3, text="Comportamiento", font=("Arial", 9, "bold"), bg="#fff3e0").pack(pady=(5, 2))
        self.behaviors = {}
        for tag in self.behavior_tags:
            b = tk.Button(self.col3, text=tag, width=12, bg=self.behavior_inactive_bg)
            b.pack(fill="x", pady=2, padx=5)
            b.bind("<Button-1>", lambda e, t=tag: self.behavior_click(t, event=e))
            self.behaviors[tag] = b
        tk.Frame(self.col3, height=2, bd=1, relief="groove", bg="#fff3e0").pack(fill="x", padx=5, pady=5)
        tk.Label(self.col3, text="Secundarios", font=("Arial", 9, "bold"), bg="#fff3e0").pack(pady=(2, 2))
        self.left_buttons = []
        # 🔒 FIX: Todos los secundarios se comportan igual (sin "primero especial")
        for tag in self.secondary_tags:
            b = tk.Button(self.col3, text=tag, width=12, bg=self.tag_inactive_bg)
            b.pack(fill="x", pady=2, padx=5)
            b.bind("<Button-1>", lambda e, t=tag: self.species_click(t, left=True, event=e))
            b.bind("<Button-3>", lambda e, t=tag: self.species_click(t, left=False, event=e))
            self.species_buttons[tag] = b
            self.left_buttons.append(b)
        # 🔒 NUEVO: Botón "Otros ▼" al final de los secundarios
        if self.other_tags_list:
            b = tk.Button(self.col3, text="Otros ▼", width=12, bg=self.tag_inactive_bg)
            b.pack(fill="x", pady=2, padx=5)
            b.bind("<Button-1>", self.show_secondary_dropdown)
            self.left_buttons.append(b)
        # ================= COLUMNA 4: ETIQUETAS (Arriba 50%) + NOTAS (Abajo 50%) =================
        col4 = tk.Frame(main_frame, bd=1, relief="sunken", width=180, bg="#e8eaf6")
        col4.pack(side="left", fill="y", padx=(5, 0))
        col4.pack_propagate(False)
        col4_top = tk.Frame(col4, bg="#e8eaf6")
        col4_top.pack(side="top", fill="both", expand=True, pady=(5, 0))
        tk.Label(col4_top, text="Clasificación", font=("Arial", 10, "bold"), bg="#e8eaf6").pack(anchor="w", padx=5)
        self.label_frame = tk.Text(col4_top, height=10, width=20, wrap="word", bd=1, relief="sunken", state="disabled")
        self.label_frame.pack(fill="both", expand=True, padx=5, pady=2)
        self.label_frame.bind("<Key>", lambda e: "break")
        tk.Frame(col4, height=1, bg="#b0b0b0").pack(fill="x", padx=5, pady=3)
        self.col4_bottom = tk.Frame(col4, bg="#e8eaf6")
        self.col4_bottom.pack(side="top", fill="both", expand=True, padx=2)
        # 🔒 NUEVO: Categorías Opcionales (dinámico, 0 a 6 botones según config)
        self.optional_tags_label = tk.Label(self.col4_bottom, text="Categorías Opcionales", 
                                            font=("Arial", 10, "bold"), bg="#e8eaf6")
        self.optional_tags_frame = tk.Frame(self.col4_bottom, bg="#e8eaf6")
        # Solo mostrar si hay optional_tags configurados
        if self.optional_tags:
            self.optional_tags_label.pack(anchor="w", padx=5, pady=(5, 2))
            self.optional_tags_frame.pack(fill="x", padx=5, pady=2)
            self.optional_buttons = []
            for i, tag in enumerate(self.optional_tags[:6]):  # Máximo 6
                btn = tk.Button(self.optional_tags_frame, text=tag, bg=self.tag_inactive_bg, 
                            font=("Arial", 8), height=1)
                btn.pack(fill="x", pady=1, padx=2)
                btn.bind("<Button-1>", lambda e, idx=i: self._handle_optional_button_click(idx, e))
                self.optional_buttons.append(btn)
        else:
            self.optional_buttons = []
        # ================= NOTES SECTION (NEW POSITION: BOTTOM OF COL1) =================
        # Create notes frame at bottom-left
        notes_frame_col1 = tk.Frame(col1)
        notes_frame_col1.pack(side="bottom", fill="both", expand=True, pady=(10, 0))
        self.notes_label = tk.Label(notes_frame_col1, text="Notas", font=("Arial", 10, "bold"))
        self.notes_label.pack(anchor="w", padx=5)
        self.notes_text = tk.Text(notes_frame_col1, height=6, width=42, wrap="word",
                                state="disabled", bd=1, relief="sunken", bg="#e8e8e8")
        self.notes_text.pack(fill="both", expand=True, padx=5, pady=2)
        self.open_notes_btn = tk.Button(notes_frame_col1, text="Editar Notas", font=("Arial", 9, "bold"),
                                        command=self.open_note_editor, bg="#d0d0d0")
        self.open_notes_btn.pack(fill="x", padx=5, pady=(2, 5))

    def _search_local_csv(self, query):
        """Busca taxones en config/species_list.csv"""
        import csv
        results = []
        
        # Rutas posibles (relativa al script y relativa al CWD)
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "species_list.csv")
        if not os.path.exists(csv_path):
            csv_path = os.path.join("config", "species_list.csv")
        if not os.path.exists(csv_path):
            return []

        query_lower = query.lower()
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                # Detectar formato automáticamente
                dialect = csv.Sniffer().sniff(f.read(1024))
                f.seek(0)
                reader = csv.DictReader(f, dialect=dialect)
                
                headers = reader.fieldnames
                if not headers: return []

                # Heurística para encontrar columnas clave
                name_col = next((h for h in headers if 'name' in h.lower()), headers[0])
                id_col = next((h for h in headers if 'id' in h.lower()), headers[1] if len(headers)>1 else None)
                vern_col = next((h for h in headers if 'verna' in h.lower() or 'comun' in h.lower()), None)

                for row in reader:
                    name = row.get(name_col, "")
                    if name and query_lower in name.lower():
                        results.append({
                            "scientificName": name,
                            "taxonID": row.get(id_col, ""),
                            "vernacularName": row.get(vern_col, "") if vern_col else ""
                        })
                        if len(results) >= 50: break # Límite para rendimiento
        except Exception as e:
            print(f"⚠️ Error leyendo species_list.csv: {e}")
        return results
    
    def _is_ctrl_pressed(self, event):
        """Detecta Ctrl (Win/Linux) o Cmd/Ctrl (macOS) de forma segura."""
        if event is None: return False
        return bool(event.state & 0x4) or bool(event.state & 0x10000)

    def open_button_config_dialog(self, tag, tag_type=None):
        if tag_type is None:
            tag_type = self._get_tag_type(tag)
            if tag_type == "unknown": return

        win = tk.Toplevel(self)
        win.title(f"Configurar botón: {tag}")
        win.geometry("380x240")
        win.transient(self)

        tk.Label(win, text=f"Propiedades ({tag_type.upper()})", font=("Arial", 11, "bold")).pack(pady=8)

        current_taxon = self.taxon_map.get(tag, {}).get("taxonID", "")

        f1 = tk.Frame(win)
        f1.pack(fill="x", padx=15, pady=4)
        tk.Label(f1, text="Etiqueta: ").pack(side="left")
        lbl_var = tk.StringVar(value=tag)
        tk.Entry(f1, textvariable=lbl_var, width=28).pack(side="left", padx=5)

        f2 = tk.Frame(win)
        f2.pack(fill="x", padx=15, pady=4)
        tk.Label(f2, text="TaxonID: ").pack(side="left")
        taxon_var = tk.StringVar(value=current_taxon)
        tk.Entry(f2, textvariable=taxon_var, width=20).pack(side="left", padx=5)

        def apply_session():
            new_tag = lbl_var.get().strip()
            new_taxon = taxon_var.get().strip()
            if not new_tag:
                messagebox.showwarning("Atención", "La etiqueta no puede estar vacía.", parent=win)
                return

            # 1. Sincronizar renombrado en listas internas (ya modifica en memoria directamente)
            if new_tag != tag:
                self._sync_renamed_tag(tag, new_tag, tag_type)

            # 2. Actualizar TaxonMap en memoria
            if new_taxon:
                self.taxon_map[new_tag] = {"taxonID": new_taxon}
                if tag != new_tag:
                    self.taxon_map.pop(tag, None)
            elif tag in self.taxon_map and tag != new_tag:
                self.taxon_map.pop(tag, None)

            # 3. Refrescar UI y marcar cambios (SIN recargar desde config_data)
            self._rebuild_tag_buttons()
            self.show_frame()
            self._mark_changed()
            win.destroy()
        tk.Button(win, text="✅ Aplicar (Sesión)", command=apply_session, bg="#4CAF50", fg="white").pack(pady=12)
        tk.Button(win, text="Cancelar", command=win.destroy).pack()

        win.update_idletasks()
        win.wait_visibility()
        try: win.grab_set()
        except tk.TclError: pass


    def _get_tag_type(self, tag):
        if tag in self.species_tags: return "species"
        if tag in self.secondary_tags: return "secondary"
        if tag in self.behavior_tags: return "behavior"
        return "unknown"

    def _pick_color(self, var):
        import tkinter.colorchooser as cc
        color = cc.askcolor()[1]
        if color: var.set(color)

    def _search_taxon_dialog(self, target_var, parent_win):
        win = tk.Toplevel(self)
        win.title("Buscar TaxonID")
        win.geometry("400x350")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Buscar (GBIF o Local):").pack(pady=5)
        q_var = tk.StringVar()
        tk.Entry(win, textvariable=q_var, width=30).pack(pady=2)

        status_lbl = tk.Label(win, text="", fg="gray", font=("Arial", 8))
        status_lbl.pack()

        lst = tk.Listbox(win, width=45)
        lst.pack(fill="both", expand=True, padx=10, pady=5)

        def _fill_listbox(results):
            lst.delete(0, "end")
            for r in results:
                lst.insert("end", f"{r.get('scientificName','')} | ID:{r.get('taxonID','')}")

        def do_search():
            q = q_var.get().strip()
            if not q: return
            status_lbl.config(text="Buscando...")
            win.update_idletasks()

            def search_thread():
                try:
                    from config_utils import search_taxa_gbif
                    res = search_taxa_gbif(q)
                    if res:
                        parent_win.after(0, lambda: [status_lbl.config(text=f"GBIF: {len(res)} resultados"), _fill_listbox(res)])
                        return
                except Exception: pass
                
                res = self._search_local_csv(q)
                parent_win.after(0, lambda: [status_lbl.config(text=f"Local: {len(res)} resultados"), _fill_listbox(res)])

            threading.Thread(target=search_thread, daemon=True).start()

        tk.Button(win, text="Buscar", command=do_search).pack(pady=3)
        win.bind("<Return>", lambda e: do_search())

        def select():
            sel = lst.curselection()
            if sel:
                line = lst.get(sel[0])
                tid = line.split("ID:")[1] if "ID:" in line else ""
                target_var.set(tid)
                win.destroy()

        tk.Button(win, text="Seleccionar", command=select, bg="#2196F3", fg="black").pack(pady=5)
        

    def _update_meta_preview(self, metadata):
        """Actualiza el cuadro de vista previa de metadatos en la columna 1."""
        self.meta_preview.config(state="normal")
        self.meta_preview.delete("1.0", "end")
        lines = [f"{k}: {v}" for k, v in metadata.items() if v]
        self.meta_preview.insert("1.0", "\n".join(lines) if lines else "Sin metadatos")
        self.meta_preview.config(state="disabled")

    def open_metadata_editor(self):
        """Abre ventana independiente para editar metadatos del video actual."""
        if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
            return
        if hasattr(self, '_meta_editor') and self._meta_editor and tk.Toplevel.winfo_exists(self._meta_editor):
            self._meta_editor.lift()
            return

        video_meta = self.video_dirs[self.current_video_index]
        metadata = video_meta.get("metadata", {})

        win = tk.Toplevel(self)
        win.title(f"Metadatos - {os.path.basename(video_meta.get('video_path', ''))}")
        win.geometry("420x480")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Editar metadatos (se guarda automáticamente al cerrar)",
                 font=("Arial", 9, "italic"), fg="#555").pack(pady=(5, 0))

        canvas = tk.Canvas(win)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        entry_widgets = {}
        for i, key in enumerate(self.metadata_vars.keys()):
            tk.Label(scrollable_frame, text=f"{key}:", font=("Arial", 10)).grid(row=i, column=0, sticky="e", padx=5, pady=4)
            entry = tk.Entry(scrollable_frame, width=30, font=("Arial", 10))
            entry.grid(row=i, column=1, sticky="w", padx=5, pady=4)
            entry.insert(0, str(metadata.get(key, "")))
            entry_widgets[key] = entry

        def save_and_close():
            for key, entry in entry_widgets.items():
                metadata[key] = entry.get().strip()
            video_meta["metadata"] = metadata
            self.save_metadata()
            self._update_meta_preview(metadata)
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(btn_frame, text="Guardar y Cerrar", bg="#4CAF50", fg="black", command=save_and_close).pack(side="right", padx=5)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="right", padx=5)

        win.protocol("WM_DELETE_WINDOW", save_and_close)
        self._meta_editor = win

    def open_note_editor(self):
        if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
            return

        # Evitar múltiples ventanas
        if hasattr(self, '_note_editor') and self._note_editor and tk.Toplevel.winfo_exists(self._note_editor):
            self._note_editor.lift()
            return

        video_meta = self.video_dirs[self.current_video_index]
        win = tk.Toplevel(self)
        win.title(f"Notas - {os.path.basename(video_meta.get('video_path', ''))}")
        win.geometry("450x350")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Editor de notas (se guarda automáticamente al cerrar)", font=("Arial", 9, "italic"), fg="#555").pack(pady=(5, 0))

        text_frame = tk.Frame(win)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        note_text = tk.Text(text_frame, wrap="word", font=("Arial", 11))
        note_text.pack(fill="both", expand=True)

        # Cargar notas actuales
        current_notes = video_meta.get("metadata", {}).get("notes", "")
        note_text.insert("1.0", current_notes)
        note_text.focus_set()

        def save_notes():
            notes = note_text.get("1.0", "end-1c")
            video_meta.setdefault("metadata", {})
            video_meta["metadata"]["notes"] = notes
            self.save_metadata()
            self.show_frame()
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(btn_frame, text="Guardar y Cerrar", bg="#4CAF50", fg="black", command=save_notes).pack(side="right", padx=5)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="right", padx=5)

        # Guardar también si cierra con la X
        win.protocol("WM_DELETE_WINDOW", save_notes)
        self._note_editor = win

    def update_checkbox(self):
        if self.video_dirs:
            video_meta = self.video_dirs[self.current_video_index]
            video_meta.setdefault("ui", {})
            video_meta["ui"]["embed_metadata"] = self.embed_metadata_var.get()
            video_meta["ui"]["xlsx"] = self.xlsx_var.get()
            self.save_metadata()

    def show_secondary_dropdown(self, event):
        if getattr(self, "dropdown_window", None) and tk.Toplevel.winfo_exists(self.dropdown_window):
            try: self.dropdown_window.destroy()
            except: pass
            self.dropdown_window = None
            return
        tags_extra = self.other_tags_list
        menu = tk.Toplevel(self)
        menu.wm_overrideredirect(True)
        menu.configure(bg="white", bd=1, relief="solid")
        widget = event.widget
        x = widget.winfo_rootx()
        # 🔹 CAMBIO: Desplegar HACIA ARRIBA en lugar de hacia abajo
        # Altura estimada por ítem: ~28px (pady=3 + padding interno + borde)
        menu_height = len(tags_extra) * 28 + 4
        y = widget.winfo_rooty() - menu_height
        # 🔹 FIX: Si no hay espacio arriba, caer hacia abajo
        if y < 0:
            y = widget.winfo_rooty() + widget.winfo_height()
        menu.geometry(f"+{x}+{y}")
        active_bg, normal_bg = "#cce6ff", "white"
        for tag in tags_extra:
            lbl = tk.Label(menu, text=tag, bg=normal_bg, width=18, anchor="w", padx=6, pady=3)
            lbl.pack(fill="x")
            lbl.bind("<Enter>", lambda e, w=lbl: w.config(bg=active_bg))
            lbl.bind("<Leave>", lambda e, w=lbl: w.config(bg=normal_bg))
            # 🔹 INTERCEPTAR "OTRO" / "OTROS" PARA DIÁLOGO PERSONALIZADO
            if tag.strip().lower() in ["otro", "otros"]:
                lbl.bind("<Button-1>", lambda e: self._open_custom_tag_dialog(left=True))
                lbl.bind("<Button-3>", lambda e: self._open_custom_tag_dialog(left=False))
            else:
                lbl.bind("<Button-1>", lambda e, t=tag: self._select_extra_tag(t, left=True))
                lbl.bind("<Button-3>", lambda e, t=tag: self._select_extra_tag(t, left=False))
        self._dropdown_close_timer = None
        def schedule_close():
            self._dropdown_close_timer = self.after(300, lambda: self._close_dropdown(menu))
        def cancel_close():
            if self._dropdown_close_timer:
                self.after_cancel(self._dropdown_close_timer)
                self._dropdown_close_timer = None
        menu.bind("<Enter>", lambda e: cancel_close())
        menu.bind("<Leave>", lambda e: schedule_close())
        menu.bind("<FocusOut>", lambda ev: self._close_dropdown(menu))
        try: menu.focus_force()
        except: pass
        self.dropdown_window = menu
        
    def _open_custom_tag_dialog(self, left=True):
        """Abre un cuadro de diálogo para ingresar una etiqueta personalizada y la aplica como especie."""
        self._close_dropdown(self.dropdown_window)

        win = tk.Toplevel(self)
        win.title("Etiqueta personalizada")
        win.geometry("320x130")
        win.transient(self)

        tk.Label(win, text="Escriba el nombre de la etiqueta:", font=("Arial", 10)).pack(pady=(10, 0))
        
        var = tk.StringVar()
        entry = tk.Entry(win, textvariable=var, width=30, font=("Arial", 11))
        entry.pack(pady=5, padx=10)
        entry.focus_set()

        def on_accept():
            custom_tag = var.get().strip()
            if not custom_tag:
                win.destroy()
                return

            # --- APLICAR LA ETIQUETA PERSONALIZADA COMO ESPECIE ---
            if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
                win.destroy()
                return

            video_meta = self.video_dirs[self.current_video_index]
            video_meta.setdefault("classification", {})
            species_list = video_meta["classification"].setdefault("species", [])
            counts_dict = video_meta["classification"].setdefault("counts", {})

            # Toggle: si ya existe, la quitamos; si no, la agregamos con count=1
            if custom_tag in species_list:
                species_list.remove(custom_tag)
                counts_dict.pop(custom_tag, None)
            else:
                species_list.append(custom_tag)
                counts_dict[custom_tag] = 1  # Siempre 1 para etiquetas personalizadas

            # Guardar y refrescar
            self.save_metadata()
            self.show_frame()
            win.destroy()

        entry.bind("<Return>", lambda e: on_accept())
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Aceptar", command=on_accept, bg="#4CAF50", fg="black").pack(side="left", padx=10)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="left", padx=10)

        win.update_idletasks()
        win.wait_visibility()
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _close_dropdown(self, menu):
        if getattr(self, "dropdown_window", None) is menu and tk.Toplevel.winfo_exists(menu):
            try: menu.destroy()
            except: pass
        self.dropdown_window = None
        if hasattr(self, '_dropdown_close_timer') and self._dropdown_close_timer:
            try: self.after_cancel(self._dropdown_close_timer)
            except: pass
            self._dropdown_close_timer = None

    def _select_extra_tag(self, tag, left=True):
        if getattr(self, "dropdown_window", None) and tk.Toplevel.winfo_exists(self.dropdown_window):
            try: self.dropdown_window.destroy()
            except: pass
            self.dropdown_window = None
        self.species_click(tag, left=left, event=None)

    def species_click(self, tag, left=True, event=None):
        # 🔹 INTERCEPTAR CTRL+CLICK PARA CONFIGURACIÓN
        if self._is_ctrl_pressed(event):
            # Detección robusta: verifica a qué lista pertenece realmente el tag
            if tag in self.secondary_tags:
                tag_type = "secondary"
            elif tag in self.behavior_tags:
                tag_type = "behavior"
            else:
                tag_type = "species"
            self.open_button_config_dialog(tag, tag_type)
            return

        # Lógica original de etiquetado
        is_alt = event and (event.state & 0x20000)
        indices = range(len(self.video_dirs)) if is_alt else [self.current_video_index]
        was_added_to_current = False
        current_count = self.count_var.get()
        if current_count < 1: return

        for idx in indices:
            if not (0 <= idx < len(self.video_dirs)): continue
            video_meta = self.video_dirs[idx]
            if "classification" not in video_meta:
                video_meta["classification"] = {"species": [], "counts": {}, "behaviors": []}
            species_list = video_meta["classification"]["species"]
            species_counts = video_meta["classification"]["counts"]
            if tag in species_list:
                species_list.remove(tag)
                species_counts.pop(tag, None)
            else:
                species_list.append(tag)
                species_counts[tag] = current_count
                if not is_alt and idx == self.current_video_index: was_added_to_current = True

        if not is_alt:
            self.count_var.set(1)
            self.canvas.focus_set()
        self.save_metadata()

        if not is_alt and left and was_added_to_current:
            all_tagged = all(
                len(v.get("classification", {}).get("species", [])) > 0 or 
                v.get("ui", {}).get("is_excluded", False) or v.get("is_excluded", False)
                for v in self.video_dirs
            )
            if all_tagged: self._show_completion_dialog()
            elif self.current_video_index < len(self.video_dirs) - 1:
                self.current_video_index += 1
                self.current_frame_index = 0
        self.show_frame()


    def behavior_click(self, tag, event=None):
        # 🔹 INTERCEPTAR CTRL+CLICK PARA CONFIGURACIÓN
        if self._is_ctrl_pressed(event):
            self.open_button_config_dialog(tag, "behavior")
            return

        # Lógica original de etiquetado
        if not self.video_dirs: return
        video_meta = self.video_dirs[self.current_video_index]
        behaviors = video_meta["classification"]["behaviors"]
        if tag in behaviors: behaviors.remove(tag)
        else: behaviors.append(tag)
        self.save_metadata()
        self.show_frame()

    def _handle_copy(self, event=None):
        """Copia clasificación, conteos, favorito y opcionales del video actual al portapapeles interno."""
        if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
            return
        current = self.video_dirs[self.current_video_index]
        classif = current.get("classification", {})
        self.clipboard_data = {
            "species": classif.get("species", []).copy(),
            "behaviors": classif.get("behaviors", []).copy(),
            "counts": classif.get("counts", {}).copy(),
            "optional_tags": classif.get("optional_tags", []).copy(),  # 🔒 NUEVO
            "is_favorite": current.get("ui", {}).get("is_favorite", False)
        }
        print("✓ Metadatos copiados al portapapeles interno.")

    def _handle_paste(self, event=None):
        """Pega los datos en el video actual o en todos (si se mantiene Alt/Ctrl presionado)."""
        if self.clipboard_data is None:
            print("⚠️ Portapapeles vacío.")
            return
        is_alt = event and (event.state & 0x20000)
        indices = range(len(self.video_dirs)) if is_alt else [self.current_video_index]
        for idx in indices:
            if not (0 <= idx < len(self.video_dirs)):
                continue
            target = self.video_dirs[idx]
            target.setdefault("classification", {})
            target["classification"]["species"] = self.clipboard_data["species"].copy()
            target["classification"]["behaviors"] = self.clipboard_data["behaviors"].copy()
            target["classification"]["counts"] = self.clipboard_data["counts"].copy()
            # 🔒 NUEVO: Pegar optional_tags
            target["classification"]["optional_tags"] = self.clipboard_data.get("optional_tags", []).copy()
            target.setdefault("ui", {})
            target["ui"]["is_favorite"] = self.clipboard_data["is_favorite"]
        self.save_metadata()
        if not is_alt:
            self.show_frame()
            
    def clear_current_video(self):
        if not self.video_dirs: return
        video_meta = self.video_dirs[self.current_video_index]
        if "classification" in video_meta:
            video_meta.setdefault("classification", {})
            video_meta["classification"]["species"] = []
            video_meta["classification"]["behaviors"] = []
            video_meta["classification"]["counts"] = {}
            video_meta["classification"]["optional_tags"] = []  # 🔒 NUEVO
        video_meta.setdefault("metadata", {})
        video_meta["metadata"]["notes"] = ""
        video_meta.setdefault("ui", {})
        video_meta["ui"]["is_favorite"] = False
        self.save_metadata()
        self.show_frame()
        self.count_var.set(1)

    def clear_all_videos_ask(self):
        if not self.video_dirs:
            return
        total = len(self.video_dirs)
        msg = f"¿Está seguro de que desea eliminar TODAS las etiquetas, comportamientos, notas y favoritos de los {total} videos de esta sesión?\n\nEsta acción no se puede deshacer."
        if messagebox.askyesno("Confirmar limpieza masiva", msg):
            self.clear_all_videos()

    def clear_all_videos(self):
        """Elimina tags, comportamientos, opcionales, notas y favoritos de TODOS los videos de la sesión."""
        for video_meta in self.video_dirs:
            # Asegurar que existan las claves (por si algún video es nuevo o está corrupto)
            video_meta.setdefault("classification", {})
            video_meta.setdefault("metadata", {})
            video_meta.setdefault("ui", {})
            # Limpiar clasificación (estructura actual)
            video_meta.setdefault("classification", {})
            video_meta["classification"]["species"] = []
            video_meta["classification"]["behaviors"] = []
            video_meta["classification"]["counts"] = {}
            video_meta["classification"]["optional_tags"] = []  # 🔒 NUEVO
            # Limpiar notas y favoritos
            video_meta.setdefault("metadata", {})
            video_meta["metadata"]["notes"] = ""
            video_meta.setdefault("ui", {})
            video_meta["ui"]["is_favorite"] = False
        # Persistir cambios en disco y refrescar UI
        self.save_metadata()
        self.show_frame()


    def _get_pending_count(self):
        """Calcula videos sin tag Y no excluidos."""
        if not self.video_dirs: return 0
        return sum(1 for v in self.video_dirs if 
                   not v.get("classification", {}).get("species", []) and
                   not v.get("ui", {}).get("is_excluded", False))

    def _update_pending_button(self):
        """Actualiza el texto y color del botón en tiempo real."""
        if not hasattr(self, 'pending_btn'): return
        count = self._get_pending_count()
        self.pending_btn.config(text=f"📊 Pendientes: {count}")
        # Verde suave si no hay pendientes, gris si hay trabajo
        self.pending_btn.config(bg="#c8e6c9" if count == 0 else "#e0e0e0")

    def _show_untagged_videos(self):
        if not self.video_dirs: return
        pending = []
        for i, v in enumerate(self.video_dirs):
            has_species = len(v.get("classification", {}).get("species", [])) > 0
            is_excl = v.get("ui", {}).get("is_excluded", False) or v.get("is_excluded", False)
            if not has_species and not is_excl:
                pending.append(f"#{i+1} {os.path.basename(v.get('video_path', ''))}")
        msg = f"Videos sin etiquetar: {len(pending)}\n"
        msg += "\n".join(pending[:20]) + ("\n... y más" if len(pending)>20 else "") if pending else "✅ ¡Todos los videos están listos!"
        messagebox.showinfo("Estado de etiquetado", msg)

    def _show_completion_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Sesión completada")
        dialog.geometry("300x120")
        dialog.transient(self)
        dialog.focus_set()
        tk.Label(dialog, text="¡Todos los videos han sido etiquetados!", pady=10).pack()
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        def add_more_videos():
            dialog.destroy()
            self.destroy()
            
            # Robust path detection for Nuitka environment
            import sys
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_dir = os.path.dirname(sys.executable)
            else:
                # Running as script
                base_dir = os.path.dirname(os.path.abspath(__file__))
            
            gui_path = os.path.join(base_dir, "gui_inicial.py")
            
            # Verify file exists before attempting to run
            if not os.path.exists(gui_path):
                messagebox.showerror(
                    "Error", 
                    f"No se encontró gui_inicial.py en:\n{gui_path}\n\n"
                    f"Por favor, asegúrese de que todos los archivos estén presentes."
                )
                try:
                    from main import MainApp
                    MainApp().mainloop()
                except: pass
                return
            
            try: 
                subprocess.Popen([sys.executable, gui_path, "--session_id", self.session_id])
            except Exception as e: 
                messagebox.showerror("Error", f"No se pudo abrir GUI Inicial:\n{e}")
            try:
                from main import MainApp
                MainApp().mainloop()
            except: pass
        def finish_session():
            # 🔹 NUEVA: Guardar metadata final antes de procesos automáticos
            self.save_metadata()
            
            # 🔹 NUEVA: Procesos automáticos según checkboxes
            try:
                # Variables para rastrear si hay trabajo pendiente
                videos_to_embed = []
                videos_to_export = []
                
                # 1. Identificar videos para embed y export (excluyendo excluidos)
                for video_meta in self.video_dirs:
                    is_excluded = video_meta.get("ui", {}).get("is_excluded", False)
                    if not is_excluded:
                        if video_meta.get("ui", {}).get("embed_metadata", False):
                            videos_to_embed.append(video_meta)
                        if video_meta.get("ui", {}).get("xlsx", False):
                            videos_to_export.append(video_meta)
                
                # 2. Ejecutar embed_metadata si hay videos marcados
                if videos_to_embed:
                    try:
                        self._auto_embed_metadata(videos_to_embed)
                    except Exception as e:
                        print(f"⚠️ Error en embed automático: {e}")
                
                # 3. Ejecutar export Excel si hay videos marcados
                if videos_to_export:
                    try:
                        self._auto_export_excel()
                    except Exception as e:
                        print(f"⚠️ Error en export automático: {e}")
                
            except Exception as e:
                print(f"⚠️ Error en procesos automáticos: {e}")
            
            # 4. Proceder con el cierre normal
            dialog.destroy()
            self.destroy()
            try:
                from main import MainApp
                MainApp().mainloop()
            except Exception as e: messagebox.showerror("Error", f"No se pudo volver al menú principal:\n{e}")
            
        tk.Button(btn_frame, text="Agregar más videos", command=add_more_videos, bg="#4CAF50", fg="black").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Finalizar", command=finish_session, bg="#f44336", fg="black").pack(side="left", padx=5)
        dialog.update_idletasks()
        dialog.grab_set()

    def save_metadata(self):
        with metadata_lock:
            if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
                return

            video_meta = self.video_dirs[self.current_video_index]
            
            # ✅ FIX: Ensure all nested structures exist with defaults
            video_meta.setdefault("ui", {})
            video_meta.setdefault("classification", {})
            video_meta.setdefault("metadata", {})
            video_meta.setdefault("processing", {})
            video_meta.setdefault("session", {})

            # Update UI flags
            video_meta["ui"]["embed_metadata"] = self.embed_metadata_var.get()
            video_meta["ui"]["xlsx"] = self.xlsx_var.get()
            video_meta["ui"]["is_excluded"] = video_meta["ui"].get("is_excluded", False)
            
            # Ensure session_id is set
            if "session_id" not in video_meta.get("session", {}):
                video_meta.setdefault("session", {})["session_id"] = self.session_id

            try:
                with open(self.metadata_path, "w", encoding="utf-8") as f:
                    json.dump(self.video_dirs, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"❌ Error crítico al guardar {self.metadata_path}: {e}")
        
        # 🔒 FIX BUG-008: Rebuild consolidated after session save so analysis sees updated data
        try:
            from config_utils import rebuild_consolidated_metadata
            rebuild_consolidated_metadata(self.config_data)
        except Exception as e:
            print(f"⚠️ Error rebuilding consolidated: {e}")

    def update_consolidated_metadata(self, video_meta):
        try:
            config = self.config_data
            json_path = config.get("General", {}).get("json_file")
            if not json_path:
                output_folder = config.get("General", {}).get("output_folder", "output")
                json_path = os.path.join(output_folder, "videos_metadata.json")
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with metadata_lock:
                data = {}
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
                    except json.JSONDecodeError: data = {}
                video_key = video_meta.get("video_path")
                if video_key:
                    data[video_key] = video_meta
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e: print(f"CRÍTICO: No se pudo guardar en el JSON: {e}")

    def load_metadata(self, metadata_path):
        if not os.path.exists(metadata_path):
            self.video_dirs = []
            return
        with open(metadata_path, "r", encoding="utf-8") as f:
            self.video_dirs = json.load(f)
        self.sync_all_videos_with_disk()
        for entry in self.video_dirs:
            entry.setdefault("classification", {})
            entry["classification"].setdefault("species", [])
            entry["classification"].setdefault("counts", {})
            entry["classification"].setdefault("behaviors", [])
            entry.setdefault("metadata", {})
            entry["metadata"].setdefault("notes", "")
            entry.setdefault("ui", {})
            entry["ui"].setdefault("embed_metadata", False)
            entry["ui"].setdefault("xlsx", False)
            entry["ui"].setdefault("is_favorite", False)
            entry["ui"].setdefault("is_excluded", False)
            entry.setdefault("session_id", self.session_id)
            entry.setdefault("camtrap_db_session", False)

    def sync_all_videos_with_disk(self):
        """🔒 FIX BUG-003: Sincroniza frames con disco, verificando entries pending Y done"""
        if not self.video_dirs:
            return
        
        for entry in self.video_dirs:
            status = entry.get("status")
            
            # 🔒 FIX: Verificar también entries "done" si los archivos no son legibles
            if status not in ("pending", "done"):
                continue
            
            frames_folder = os.path.join(self.output_folder, "frames", entry.get("frames_folder", ""))
            if not os.path.exists(frames_folder):
                continue
            
            # 🔒 FIX: Para entries "done", verificar que los archivos sean legibles
            if status == "done":
                # Verificar que al menos un archivo de tops sea legible
                tops = entry.get("tops", [])
                if tops and all(self._verify_image_file(t) for t in tops if t):
                    continue  # Todo OK, no necesita sync
                # Si falla, caer al flujo de retry abajo
            
            # 🔒 FIX NUITKA: Retry con delays para manejar lag del filesystem
            max_retries = 3
            for retry in range(max_retries):
                try:
                    files_in_folder = os.listdir(frames_folder)
                    promedio_files = [f for f in files_in_folder if "promedio" in f.lower()]
                    top_files = sorted([f for f in files_in_folder if "top_" in f.lower()])
                    
                    # Verificar que los archivos sean realmente legibles
                    if promedio_files and top_files:
                        promedio_path = os.path.join(frames_folder, promedio_files[0])
                        top_path = os.path.join(frames_folder, top_files[0])
                        
                        try:
                            with open(promedio_path, 'rb') as f:
                                f.read(1)
                            with open(top_path, 'rb') as f:
                                f.read(1)
                            
                            # Archivos legibles, actualizar metadata
                            entry["status"] = "done"
                            if not entry.get("promedio"): 
                                entry["promedio"] = promedio_path
                            if not entry.get("tops"): 
                                entry["tops"] = [os.path.join(frames_folder, f) for f in top_files]
                            if entry.get("promedio"):
                                promedio_filename = os.path.basename(promedio_path)
                                mask_filename = promedio_filename.replace("_promedio", "_mask")
                                entry["mask"] = os.path.join(frames_folder, mask_filename)
                            if not entry.get("fecha_prefix") and promedio_files[0]:
                                name = os.path.splitext(promedio_files[0])[0]
                                if "_promedio" in name: 
                                    entry["fecha_prefix"] = name.replace("_promedio", "")
                            break  # Éxito, salir del loop de retry
                        except Exception:
                            if retry < max_retries - 1:
                                time.sleep(0.1 * (retry + 1))
                            continue
                except Exception:
                    if retry < max_retries - 1:
                        time.sleep(0.1 * (retry + 1))
                    continue

    def reload_current_video_from_disk(self):
        """🔒 FIX BUG-003: Recarga el video actual verificando que los archivos sean legibles"""
        try:
            if not (0 <= self.current_video_index < len(self.video_dirs)):
                return False
            entry = self.video_dirs[self.current_video_index]
            status = entry.get("status")
            
            # 🔒 FIX: Para entries "done", verificar que los archivos sean legibles
            if status == "done":
                tops = entry.get("tops", [])
                if tops and all(self._verify_image_file(t) for t in tops if t):
                    return True  # Ya está cargado y legible
                # Si falla la verificación, caer al flujo de retry abajo
            
            if status != "pending":
                return False  # No es pending ni done con problemas, no se puede cargar
            
            frames_folder = os.path.join(self.output_folder, "frames", entry.get("frames_folder", ""))
            if not os.path.exists(frames_folder):
                return False
            
            # 🔒 FIX NUITKA: Retry con delays y verificación de imágenes
            max_retries = 5
            for retry in range(max_retries):
                try:
                    files_in_folder = os.listdir(frames_folder)
                    promedio_files = [f for f in files_in_folder if "promedio" in f.lower()]
                    mask_files = [f for f in files_in_folder if "mask" in f.lower()]
                    top_files = sorted([f for f in files_in_folder if "top_" in f.lower()])
                    
                    if promedio_files and top_files and mask_files:
                        promedio_path = os.path.join(frames_folder, promedio_files[0])
                        mask_path = os.path.join(frames_folder, mask_files[0])
                        top_paths = [os.path.join(frames_folder, f) for f in top_files]
                        
                        # 🔒 FIX: Verificar que TODOS los archivos sean legibles
                        all_valid = True
                        for path in [promedio_path, mask_path] + top_paths:
                            if not self._verify_image_file(path):
                                all_valid = False
                                break
                        
                        if all_valid:
                            # Todos los archivos verificados, actualizar metadata
                            entry["status"] = "done"
                            entry["promedio"] = promedio_path
                            entry["mask"] = mask_path
                            entry["tops"] = top_paths
                            if not entry.get("fecha_prefix") and promedio_files[0]:
                                name = os.path.splitext(promedio_files[0])[0]
                                if "_promedio" in name:
                                    entry["fecha_prefix"] = name.replace("_promedio", "")
                            self.save_metadata()
                            print(f"✓ Frames loaded for video {self.current_video_index + 1}")
                            return True
                        else:
                            # Archivos incompletos, reintentar
                            if retry < max_retries - 1:
                                wait_time = 0.3 * (retry + 1)
                                print(f"⏳ Waiting for complete frames (attempt {retry + 1}/{max_retries})...")
                                time.sleep(wait_time)
                            continue
                except Exception as e:
                    if retry < max_retries - 1:
                        wait_time = 0.3 * (retry + 1)
                        time.sleep(wait_time)
                    continue
            
            print(f"⚠️ Could not load frames after {max_retries} attempts")
            return False
        except Exception:
            return False

    def get_current_frames(self):
        """🔒 FIX BUG-004: Evita duplicar frames en ráfagas de fotos"""
        if not (0 <= self.current_video_index < len(self.video_dirs)):
            return []
        video_meta = self.video_dirs[self.current_video_index]
        frames = []
        
        # Para ráfagas de fotos, solo cargar tops (no original_photos)
        is_photo_burst = video_meta.get("is_photo", False)
        
        if not is_photo_burst:
            # Para videos, cargar original_photos
            original_photos = video_meta.get("original_photos", [])
            for p in original_photos:
                if p and os.path.exists(p) and self._verify_image_file(p):
                    frames.append(p)
        
        # Cargar tops (para videos Y ráfagas de fotos)
        tops = video_meta.get("tops", [])
        for p in tops:
            if p and os.path.exists(p) and self._verify_image_file(p):
                frames.append(p)
        
        return frames


    def _verify_image_file(self, path, min_size=100):
        """🔒 OPTIMIZACIÓN: Verificación ligera (solo header, sin decodificar imagen completa).
        
        Antes: img.verify() + img.load() → decodificaba toda la imagen (~0.5-1s por imagen)
        Ahora: Solo lee los primeros bytes para verificar magic bytes (~0.001s por imagen)
        """
        try:
            # 1. Verificar existencia y tamaño mínimo
            if not os.path.exists(path):
                return False
            if os.path.getsize(path) < min_size:
                return False
            
            # 2. Verificar magic bytes del header (sin decodificar)
            with open(path, 'rb') as f:
                header = f.read(8)
            
            if len(header) < 3:
                return False
            
            # JPEG: FF D8 FF
            if header[:3] == b'\xff\xd8\xff':
                return True
            
            # PNG: 89 50 4E 47 0D 0A 1A 0A
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                return True
            
            # Si no tiene magic bytes conocidos, rechazar
            return False
        except Exception:
            return False

    
    def _update_tag_buttons(self, current_species, current_behaviors, current_counts):
        if hasattr(self, 'species_buttons'):
            for tag, btn in self.species_buttons.items():
                if btn.winfo_exists():
                    if tag in current_species:
                        count = current_counts.get(tag, 1)
                        btn.config(bg=self.species_active_bg, text=f"{tag} ({count})")
                    else:
                        btn.config(bg=self.species_inactive_bg, text=tag)
        if hasattr(self, 'behaviors'):
            for tag, btn in self.behaviors.items():
                if btn.winfo_exists():
                    btn.config(bg=self.behavior_active_bg if tag in current_behaviors else self.tag_inactive_bg)
    
    def _handle_optional_button_click(self, idx, event):
        """Handler para clicks en botones opcionales.
        🔒 FIX: Ya no permite renombrar desde el tagger (eso se hace desde ConfigManager).
        Los tags opcionales son categorías independientes, no tienen taxonID."""
        self._toggle_optional_tag(idx)
    
    def _toggle_optional_tag(self, idx):
        """Toggle un tag opcional on/off para el video actual.
        🔒 FIX: Ahora usa optional_tags (de la config del tagger) en lugar de custom_tags."""
        if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
            return
        if idx >= len(self.optional_tags):
            return
        video_meta = self.video_dirs[self.current_video_index]
        video_meta.setdefault("classification", {})
        optional_tags = video_meta["classification"].setdefault("optional_tags", [])
        tag_label = self.optional_tags[idx]
        # Toggle: add or remove
        if tag_label in optional_tags:
            optional_tags.remove(tag_label)
        else:
            optional_tags.append(tag_label)
        self.save_metadata()
        self._update_optional_buttons()

        
    def _update_optional_buttons(self):
        """Sincroniza el estado de los botones opcionales con los tags del video actual.
        🔒 FIX: Ahora usa optional_tags (de la config del tagger) en lugar de custom_tags."""
        if not self.video_dirs or not (0 <= self.current_video_index < len(self.video_dirs)):
            return
        video_meta = self.video_dirs[self.current_video_index]
        optional_tags = video_meta.get("classification", {}).get("optional_tags", [])
        if not hasattr(self, 'optional_buttons'):
            return
        for idx, btn in enumerate(self.optional_buttons):
            if not btn.winfo_exists():
                continue
            if idx >= len(self.optional_tags):
                continue
            tag_label = self.optional_tags[idx]
            if tag_label in optional_tags:
                btn.config(bg=self.tag_active_bg)
            else:
                btn.config(bg=self.tag_inactive_bg)

    def show_frame(self):
        try:
            # 1. Validación básica de datos
            if not self.video_dirs or self.current_video_index >= len(self.video_dirs):
                self._show_empty_state("Sin datos cargados")
                return
            video_meta = self.video_dirs[self.current_video_index]
            frames = self.get_current_frames()
            
            # 🔒 FIX BUG-003: Reintentar cargar frames si no están disponibles,
            # independientemente del status (pending O done con archivos ilegibles)
            if not frames:
                max_attempts = 3
                for attempt in range(max_attempts):
                    success = self.reload_current_video_from_disk()
                    if success:
                        frames = self.get_current_frames()
                        if frames:
                            break
                    if attempt < max_attempts - 1:
                        time.sleep(0.5)  # Wait before retry
            
            if not frames:
                # Mostrar mensaje informativo basado en el status
                status = video_meta.get("status", "unknown")
                if status == "pending":
                    self._show_empty_state("⏳ Procesando video...\nIntentando cargar frames...")
                else:
                    self._show_empty_state("❌ No hay frames disponibles")
                return
            
            if self.current_frame_index >= len(frames):
                self.current_frame_index = 0
            
            # 2. Carga de la imagen
            frame_path = frames[self.current_frame_index]
            # 🔒 FIX: OpenCV fails with Unicode paths on Windows, use PIL first
            img = None
            pil_img = None
            try:
                # Try loading with PIL first (better Unicode support)
                pil_img = Image.open(frame_path)
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
            except Exception as e:
                print(f"⚠️ PIL failed to load {os.path.basename(frame_path)}: {e}")
                # Fallback to OpenCV
                try:
                    img = cv2.imread(frame_path)
                    if img is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(img)
                except Exception as e2:
                    print(f"⚠️ OpenCV also failed: {e2}")
                    pil_img = None
            
            if pil_img is not None:
                # Aplicar ajustes de imagen (brillo, contraste, etc.)
                pil_img = self.apply_adjustments_from_pil(pil_img)
                
                # ==========================================================
                #  SOLUCIÓN AL PROBLEMA DE TAMAÑO (ESCALADO / FIT)
                # ==========================================================
                # Obtener tamaño actual del canvas (con fallback a dimensiones fijas si es 1)
                canvas_w = self.canvas.winfo_width()
                canvas_h = self.canvas.winfo_height()
                if canvas_w <= 1: canvas_w = 912
                if canvas_h <= 1: canvas_h = 513
                
                # Calcular escala para que quepa completa manteniendo relación de aspecto
                img_w, img_h = pil_img.size
                scale = min(canvas_w / img_w, canvas_h / img_h)
                # (Opcional) No agrandar imágenes pequeñas para evitar pixelado
                if scale > 1.0: scale = 1.0
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)
                
                # Redimensionar
                pil_img_resized = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
                
                # ==========================================================
                #  LÓGICA DE LA MÁSCARA (Compatible con ambas versiones)
                # ==========================================================
                show_mask = False
                # Versión Nueva (Modo Máscara)
                if hasattr(self, 'mask_mode'):
                    if self.mask_mode == 1: show_mask = True
                    elif self.mask_mode == 2: show_mask = self.blink_state
                # Versión Antigua (Legacy)
                else:
                    show_mask = self.show_mask or (self.blink_mode and self.blink_state)
                
                if show_mask:
                    mask_path = video_meta.get("mask")
                    if mask_path and os.path.exists(mask_path):
                        try:
                            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                            if mask is not None:
                                # Redimensionar máscara para que coincida con la imagen redimensionada
                                mask_resized = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
                                mask_norm = mask_resized.astype(np.float32) / 255.0
                                img_np = np.array(pil_img_resized).astype(np.float32)
                                overlay = np.zeros_like(img_np)
                                
                                # Determinar color de la máscara
                                color = (255, 0, 0) # Rojo por defecto
                                if hasattr(self, 'mask_colors') and hasattr(self, 'mask_color_index'):
                                    color = self.mask_colors[self.mask_color_index]
                                r, g, b = color
                                overlay[:, :, 0] = r
                                overlay[:, :, 1] = g
                                overlay[:, :, 2] = b
                                
                                alpha = mask_norm[:, :, None] * 0.6
                                img_np = (1 - alpha) * img_np + alpha * overlay
                                pil_img_final = Image.fromarray(img_np.astype(np.uint8))
                            else: pil_img_final = pil_img_resized
                        except Exception as e:
                            print(f"⚠️ Error al procesar máscara: {e}")
                            pil_img_final = pil_img_resized
                    else: pil_img_final = pil_img_resized
                else:
                    pil_img_final = pil_img_resized
                
                # 🔒 FIX BUG-007: Clear old PhotoImage to prevent memory leak
                # PhotoImage objects hold native resources that aren't automatically garbage collected
                if "current" in self.tk_imgs:
                    try:
                        old_img = self.tk_imgs["current"]
                        del self.tk_imgs["current"]
                        del old_img  # Explicit cleanup to release Tkinter resources
                    except Exception: pass
                
                # 3. Mostrar en Canvas (Centrada)
                tk_img = ImageTk.PhotoImage(pil_img_final)
                self.tk_imgs["current"] = tk_img
                self.canvas.delete("all")
                
                # Calcular posición central para que quede en medio del canvas
                x = (canvas_w - new_w) // 2
                y = (canvas_h - new_h) // 2
                self.canvas.create_image(x, y, anchor="nw", image=tk_img)
                
                # 🎨 Visual indicators: Favorite border and Excluded X
                is_favorite = video_meta.get("is_favorite", False)
                is_excluded = video_meta.get("is_excluded", False)
                
                # Draw favorite border (golden/yellow frame)
                if is_favorite:
                    border_width = 8
                    border_color = "#FFD700"  # Gold
                    self.canvas.create_rectangle(
                        x - border_width, y - border_width,
                        x + new_w + border_width, y + new_h + border_width,
                        outline=border_color, width=border_width
                    )
                
                # Draw excluded X (red cross)
                if is_excluded:
                    x_color = "#FF0000"  # Red
                    x_width = 10
                    # Diagonal from top-left to bottom-right
                    self.canvas.create_line(
                        x, y, x + new_w, y + new_h,
                        fill=x_color, width=x_width
                    )
                    # Diagonal from top-right to bottom-left
                    self.canvas.create_line(
                        x + new_w, y, x, y + new_h,
                        fill=x_color, width=x_width
                    )
            else:
                self._show_empty_state("Error al leer frame")
                return
            
            # 4. Actualizar Interfaz
            video_name = os.path.basename(video_meta.get("video_path", ""))
            self.video_label.config(text=video_name)
            self.video_counter_label.config(text=f"Video {self.current_video_index + 1}/{len(self.video_dirs)}")
            self.frame_counter_label.config(text=f"Frame {self.current_frame_index + 1}/{len(frames)}")
            
            # Botones y etiquetas
            classif = video_meta.get("classification", {})
            self._update_tag_buttons(classif.get("species", []), classif.get("behaviors", []), classif.get("counts", {}))
            self._update_optional_buttons()
            
            # Preview de clasificación
            species_list = classif.get("species", [])
            behavior_list = classif.get("behaviors", [])
            species_text = ", ".join(species_list) if species_list else "Ninguna"
            behavior_text = ", ".join(behavior_list) if behavior_list else "Ninguno"
            self.label_frame.config(state="normal")
            self.label_frame.delete("1.0", "end")
            self.label_frame.insert("1.0", f"Especies: {species_text}\nComportamientos: {behavior_text}")
            self.label_frame.config(state="disabled")
            
            # Metadatos Preview
            self._update_meta_preview(video_meta.get("metadata", {}))
            
            # Notas Preview
            self.notes_text.config(state="normal")
            self.notes_text.delete("1.0", "end")
            self.notes_text.insert("1.0", video_meta.get("metadata", {}).get("notes", ""))
            self.notes_text.config(state="disabled")
            
            # Favoritos / UI
            ui_state = video_meta.get("ui", {})
            self.favorite_button.config(text="★" if video_meta.get("is_favorite", False) else "☆")
            self.update_exclude_button()
            self.embed_metadata_var.set(ui_state.get("embed_metadata", False))
            self.xlsx_var.set(ui_state.get("xlsx", False))
            self._update_pending_button()
        
        except Exception as e:
            print(f"❌ Error crítico en show_frame: {e}")
            import traceback
            traceback.print_exc()
            self._show_empty_state("Error interno al renderizar")


    def _show_empty_state(self, message):
        self.label_frame.config(state="normal")
        self.label_frame.delete("1.0", "end")
        self.label_frame.insert("1.0", message)
        self.label_frame.config(state="disabled")
        
        self.canvas.delete("all")
        self.video_label.config(text="")
        self.video_counter_label.config(text="Video 0/0")
        self.frame_counter_label.config(text="Frame 0/0")

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
            self.count_var.set(1)
            self.canvas.focus_set()
            self.reload_current_video_from_disk()
            self.show_frame()
    def prev_video(self):
        if self.current_video_index > 0:
            self.current_video_index -= 1
            self.current_frame_index = 0
            self.count_var.set(1)
            self.canvas.focus_set()
            self.reload_current_video_from_disk()
            self.show_frame()

    def toggle_mask(self, event=None):
        self.show_mask = not self.show_mask
        self.show_frame()
    def toggle_blink_mode(self, event=None):
        self.blink_mode = not self.blink_mode

    def blink_mask(self):
        if self.mask_mode == 2:
            self.blink_state = not self.blink_state
            self.show_frame()
        self._blink_after_id = self.after(self.blink_interval, self.blink_mask)

    def handle_mask_key(self, event=None):
        """Espacio: cambia modo | Shift+Espacio: cambia color"""
        is_shift = event and (event.state & 0x1)
        if is_shift:
            self.mask_color_index = (self.mask_color_index + 1) % len(self.mask_colors)
            names = ["Rojo", "Magenta", "Cyan", "Amarillo", "Verde"]
            print(f"🎨 Color máscara: {names[self.mask_color_index]}")
        else:
            self.mask_mode = (self.mask_mode + 1) % 3
            modes = ["Ocultar", "Constante", "Titilante"]
            print(f"👁️ Máscara: {modes[self.mask_mode]}")
        self.show_frame()

    def _cancel_blink_timer(self):
        if hasattr(self, '_blink_after_id'):
            try: self.after_cancel(self._blink_after_id)
            except: pass

    def _run_camtrap_export(self):
        """Exportación automática y obligatoria en modo científico."""
        if not self.scientific_mode:
            return
        if not os.path.exists(self.metadata_path):
            print("⚠️ No existe metadata.json para exportar Camtrap DP.")
            return

        try:
            from export_camtrap import export_camtrap
            output_dir = os.path.join(self.output_folder, "sessions", self.session_id, "camtrap_dp")
            os.makedirs(output_dir, exist_ok=True)
            
            print("🔄 [MODO CIENTÍFICO] Generando archivos Camtrap DP...")
            export_camtrap(
                metadata_path=self.metadata_path,
                output_dir=output_dir,
                deployments_csv_provided=False,
                config=self.config_data
            )
            print("✅ [MODO CIENTÍFICO] Exportación completada en:", output_dir)
        except Exception as e:
            print(f"❌ [MODO CIENTÍFICO] Fallo al exportar Camtrap DP: {e}")
            import traceback
            traceback.print_exc()

    def _auto_refresh_pending(self):
        """🔒 FIX BUG-003: Verifica periódicamente que los frames sean legibles"""
        try:
            # 🔒 FIX: Verificar TODOS los videos, no solo los pending
            needs_refresh = False
            
            for i, v in enumerate(self.video_dirs):
                status = v.get("status")
                
                # Si está pending, intentar sync
                if status == "pending":
                    self.sync_all_videos_with_disk()
                    needs_refresh = True
                
                # Si está done, verificar que los archivos sean legibles
                elif status == "done":
                    tops = v.get("tops", [])
                    if tops and not all(self._verify_image_file(t) for t in tops if t):
                        # Archivos no legibles, intentar recargar
                        if i == self.current_video_index:
                            success = self.reload_current_video_from_disk()
                            if success:
                                needs_refresh = True
            
            # Si el video actual necesita refrescarse, actualizar display
            if needs_refresh and (0 <= self.current_video_index < len(self.video_dirs)):
                frames = self.get_current_frames()
                if frames:
                    self.show_frame()
            
            # 🔒 FIX: Continuar verificando cada 3 segundos (independiente de pending)
            self._auto_refresh_id = self.after(3000, self._auto_refresh_pending)
            
        except Exception as e:
            print(f"⚠️ Error in auto-refresh: {e}")
            # Continuar verificando de todas formas
            self._auto_refresh_id = self.after(3000, self._auto_refresh_pending)

    def _cancel_auto_refresh(self):
        """Cancel the auto-refresh timer"""
        if hasattr(self, '_auto_refresh_id') and self._auto_refresh_id:
            try:
                self.after_cancel(self._auto_refresh_id)
            except:
                pass
            self._auto_refresh_id = None
    
    def _auto_embed_metadata(self, videos_to_embed):
        """
        🔹 NUEVA: Embebe metadatos automáticamente en los videos seleccionados
        Usa los campos predeterminados del config sin mostrar GUI
        """
        try:
            config = load_config()
            
            # Campos predeterminados para embed
            fields_to_embed = config.get("MetadataSettings", {}).get(
                "fields_to_embed",
                ["session_id", "site", "camera", "operator", "species", "recorded_at"]
            )
            
            success_count = 0
            
            for video_meta in videos_to_embed:
                video_path = video_meta.get("file", {}).get("video_path") or video_meta.get("video_path")
                
                if not video_path or not os.path.exists(video_path):
                    continue
                
                # Construir diccionario de metadatos
                metadata_dict = {}
                
                # Helper para extraer valores
                def extract_value(entry, field):
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
                
                for field in fields_to_embed:
                    value = extract_value(video_meta, field)
                    if value and value != "":
                        metadata_dict[field] = value
                
                if metadata_dict:
                    if self._embed_with_ffmpeg_helper(video_path, metadata_dict):
                        success_count += 1
            
            print(f"✅ Metadatos incrustados en {success_count} videos automáticamente")
            
        except Exception as e:
            print(f"❌ Error en embed automático: {e}")
    
    def _embed_with_ffmpeg_helper(self, video_path, metadata_dict):
        """
        Helper para incrustar metadatos usando ffmpeg
        Versión simplificada de embed_metadata._embed_with_ffmpeg
        """
        try:
            temp_path = video_path + ".tmp.mp4"
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 🔒 FIX BUG-004: Cross-platform binary name
            ffmpeg_bin = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
            ffmpeg_path = os.path.join(base_dir, 'resources', 'ffmpeg', ffmpeg_bin)
            
            # Fallback a ffmpeg del sistema si no está en resources
            if not os.path.exists(ffmpeg_path):
                ffmpeg_path = ffmpeg_bin
            
            # Construir comando ffmpeg con metadatos
            cmd = [ffmpeg_path, '-i', video_path, '-c', 'copy']
            
            # Agregar metadatos
            for key, value in metadata_dict.items():
                cmd.extend(['-metadata', f'{key}={value}'])
            
            cmd.extend(['-y', temp_path])
            
            # Ejecutar ffmpeg
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode == 0:
                # Reemplazar original con archivo temporal
                import shutil
                shutil.move(temp_path, video_path)
                return True
            else:
                # Limpiar archivo temporal si falla
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                return False
                
        except Exception as e:
            print(f"⚠️ Error incrustando metadatos en {os.path.basename(video_path)}: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            return False
    
    def _auto_export_excel(self):
        """
        🔹 NUEVA: Exporta metadatos a Excel automáticamente
        Usa los campos predeterminados sin mostrar GUI
        """
        try:
            from export_utils import export_to_excel
            
            # Ejecutar export
            output_path = export_to_excel()
            
            if output_path:
                print(f"✅ Excel exportado automáticamente en: {output_path}")
            else:
                print("⚠️ No se pudo generar Excel automáticamente")
                
        except Exception as e:
            print(f"❌ Error en export automático: {e}")
    
    def destroy(self):
        if self.scientific_mode:
            self._run_camtrap_export()
        self._cancel_auto_refresh()
        self._cancel_blink_timer()
        
        # 🔹 FIX: Consolidar y actualizar resúmenes al cerrar sesión
        try:
            from config_utils import rebuild_consolidated_metadata, update_summaries_from_metadata
            rebuild_consolidated_metadata(self.config_data)
            update_summaries_from_metadata(self.config_data)
            print("✅ Metadata consolidada y resúmenes actualizados al cerrar.")
        except Exception as e:
            print(f"⚠️ Error consolidando metadata al cerrar: {e}")

        super().destroy()
        
        # 🔹 NUEVO: Abrir main al cerrar tagger
        try:
            from main import MainApp
            MainApp().mainloop()
        except Exception as e:
            print(f"⚠️ Error abriendo main: {e}")

    def _handle_canvas_click(self, event):
        """
        Handle left-click on canvas with 3x3 zone-based navigation.
        Zones: Left=prev frame, Right=next frame, Top=next video, Bottom=prev video
        Priority: Vertical (top/bottom) overrides horizontal in corners.
        """
        # Get canvas dimensions (fallback if not yet rendered)
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w <= 1:
            canvas_w = int(self.canvas.cget("width"))
        if canvas_h <= 1:
            canvas_h = int(self.canvas.cget("height"))
        
        # Calculate click position as percentages
        x_percent = event.x / canvas_w
        y_percent = event.y / canvas_h
        
        # Zone boundaries (33% and 66%)
        # Priority: Vertical zones (top/bottom) checked first to handle corners
        if y_percent < 0.33:
            # Top zone: Next video
            self.next_video()
        elif y_percent > 0.66:
            # Bottom zone: Previous video
            self.prev_video()
        elif x_percent < 0.33:
            # Left zone: Previous frame
            self.prev_frame()
        elif x_percent > 0.66:
            # Right zone: Next frame
            self.next_frame()
        # Center zone (33-66% both axes): No action
    
    def _handle_canvas_scroll(self, event):
        """
        Handle mouse wheel scrolling for video navigation with cross-platform support.
        Windows/macOS: event.delta (positive=up, negative=down)
        Linux: event.num (4=up, 5=down)
        Includes 100ms debounce to prevent rapid scroll skipping.
        """
        # Cancel pending scroll if already scheduled
        if self._scroll_debounce_id is not None:
            self.after_cancel(self._scroll_debounce_id)
            self._scroll_debounce_id = None
        
        # Determine scroll direction (cross-platform)
        direction = 0  # 1 = up/next, -1 = down/prev
        
        if hasattr(event, 'delta'):
            # Windows/macOS: event.delta
            direction = 1 if event.delta > 0 else -1
        elif hasattr(event, 'num'):
            # Linux X11: Button-4 (up) or Button-5 (down)
            direction = 1 if event.num == 4 else -1
        
        # Schedule the navigation action with 100ms debounce
        def do_scroll():
            if direction > 0:
                self.next_video()
            elif direction < 0:
                self.prev_video()
            self._scroll_debounce_id = None
        
        self._scroll_debounce_id = self.after(100, do_scroll)

    def play_video(self, event=None):
        video_meta = self.video_dirs[self.current_video_index]
        video_path = video_meta.get("video_path", "")
        if video_path and os.path.exists(video_path): open_video_default(video_path)
        else:
            frames = self.get_current_frames()
            if frames and self.current_frame_index < len(frames):
                current_img = frames[self.current_frame_index]
                if os.path.exists(current_img): open_video_default(current_img)

    def toggle_favorite(self):
        if not self.video_dirs: return
        video_meta = self.video_dirs[self.current_video_index]
        video_meta["is_favorite"] = not video_meta.get("is_favorite", False)
        self.save_metadata()
        self.update_favorite_button()
        self.show_frame()

    def update_favorite_button(self):
        if not hasattr(self, 'favorite_button') or not self.favorite_button.winfo_exists(): return
        is_fav = self.video_dirs[self.current_video_index].get("is_favorite", False) if self.video_dirs else False
        self.favorite_button.config(text="★" if is_fav else "☆")

    def toggle_exclude(self):
        if not self.video_dirs:
            return
        video_meta = self.video_dirs[self.current_video_index]
        
        # 1. Definir el nuevo estado explícitamente
        new_state = not video_meta.get("is_excluded", False)
        
        # 2. Sincronizar en ambas claves del metadata para evitar inconsistencias
        video_meta["is_excluded"] = new_state
        video_meta.setdefault("ui", {})["is_excluded"] = new_state
        
        # 3. Persistir y actualizar interfaz
        self.save_metadata()
        self.update_exclude_button()
        self.show_frame()
        self._update_pending_button()  # Refresca el contador de pendientes

    def update_exclude_button(self):
        if not hasattr(self, 'exclude_button') or not self.exclude_button.winfo_exists(): return
        is_excl = self.video_dirs[self.current_video_index].get("is_excluded", False) if self.video_dirs else False
        text = "🚫" if is_excl else "☐"
        bg_color = self.colors_cfg.get("exclude_button_active_bg", "#ffebee") if is_excl else self.colors_cfg.get("exclude_button_bg", "#ffffff")
        fg_color = self.colors_cfg.get("exclude_button_active_fg", "#d32f2f") if is_excl else self.colors_cfg.get("exclude_button_fg", "#000000")
        self.exclude_button.config(text=text, bg=bg_color, fg=fg_color)

    # --- Ajustes de Imagen ---
    def open_adjust_window(self):
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            self.adjust_window.lift()
            return
        win = tk.Toplevel(self)
        win.title("Ajustes de imagen")
        win_width, win_height = 360, 500
        win.withdraw()
        self.update_idletasks()
        main_x, main_y = self.winfo_x(), self.winfo_y()
        win_x, win_y = main_x + self.winfo_width() + 10, main_y
        if win_x + win_width > self.winfo_screenwidth(): win_x = self.winfo_screenwidth() - win_width - 10
        if win_y + win_height > self.winfo_screenheight(): win_y = self.winfo_screenheight() - win_height - 50
        win.geometry(f"{win_width}x{win_height}+{win_x}+{win_y}")
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
                         length=300, command=lambda val, k=key: self.update_adjustment(k, float(val)))
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
        self.image_adjustments.update({"brightness": 1.2, "contrast": 1.2, "sharpness": 1.5, "smoothness": 0.5, "denoise": 5.0, "flatfield": 0.1})
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            for key, slider in self.adjust_sliders.items(): slider.set(self.image_adjustments[key])
        self.show_frame()
    def reset_adjustments(self):
        self.image_adjustments.update(DEFAULT_ADJUSTMENTS)
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window):
            for key, slider in self.adjust_sliders.items(): slider.set(self.image_adjustments[key])
        self.show_frame()
    def save_adjusted_image(self):
        frames = self.get_current_frames()
        if not frames or self.current_frame_index >= len(frames): return
        frame_path = frames[self.current_frame_index]
        img = cv2.imread(frame_path)
        if img is None: return
        pil_img = self.apply_adjustments(img)
        base, ext = os.path.splitext(frame_path)
        adjusted_path = f"{base}_adjusted{ext}"
        pil_img.save(adjusted_path)
        print(f"Imagen ajustada guardada: {adjusted_path}")
        if self.adjust_window and tk.Toplevel.winfo_exists(self.adjust_window): self.adjust_window.destroy()
    def apply_adjustments(self, img):
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        return self.apply_adjustments_from_pil(pil_img)
    
    def apply_adjustments_from_pil(self, pil_img):
        """Apply image adjustments directly to a PIL image"""
        pil_img = ImageEnhance.Brightness(pil_img).enhance(self.image_adjustments["brightness"])
        pil_img = ImageEnhance.Contrast(pil_img).enhance(self.image_adjustments["contrast"])
        pil_img = ImageEnhance.Sharpness(pil_img).enhance(self.image_adjustments["sharpness"])
        if self.image_adjustments["smoothness"] > 0: 
            pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=self.image_adjustments["smoothness"]))
        if self.image_adjustments["flatfield"] > 0:
            arr = np.array(pil_img).astype(np.float32)
            arr = arr * (1 - self.image_adjustments["flatfield"]) + np.mean(arr) * self.image_adjustments["flatfield"]
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            pil_img = Image.fromarray(arr)
        if self.image_adjustments["denoise"] > 0:
            arr = np.array(pil_img)
            arr = cv2.fastNlMeansDenoisingColored(arr, None, h=self.image_adjustments["denoise"], hColor=self.image_adjustments["denoise"], templateWindowSize=7, searchWindowSize=21)
            pil_img = Image.fromarray(arr)
        return pil_img

    # --- Configuración Tagger ---
    def open_config_manager(self):
        """Abre el panel de gestión de configuraciones."""
        try:
            # ConfigManager solo necesita el padre. Internamente ya lee/actualiza 
            # self.parent.species_tags, etc. y llama a _rebuild_tag_buttons()
            ConfigManager(self)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el gestor de configuraciones:\n{e}", parent=self)

    def on_recent_config_selected(self, event=None):
        """Maneja la selección desde el combobox de forma segura."""
        idx = self.recent_combo.current()
        values = self.recent_combo['values']
        if idx < 0 or idx >= len(values):
            return
            
        selected_name = values[idx]
        config_path = self._config_registry.get(selected_name)
        
        if config_path and config_path != self.active_tagger_config_path:
            self._switch_config(config_path)

    def _scan_and_populate_dropdown(self):
        """Escanea configs disponibles y recientes, los unifica y llena el combobox."""
        self._config_registry = {}
        all_configs = []
        recent_paths_set = set()

        # 1. Recientes (prioridad alta)
        recent = get_recent_configs(self.config_data)
        for r in recent:
            name = f"[Reciente] {r['name']}"
            all_configs.append(name)
            self._config_registry[name] = r['path']
            recent_paths_set.add(r['path'])

        # 2. Disponibles (sin duplicar recientes)
        available = list_tagger_configs()
        for a in available:
            if a['path'] not in recent_paths_set:
                all_configs.append(a['name'])
                self._config_registry[a['name']] = a['path']

        # Actualizar UI
        self.recent_combo['values'] = all_configs
        if not all_configs:
            self.recent_combo.set("⚠️ Sin configuraciones")
            return

        # Seleccionar la activa o la primera disponible
        target_name = None
        for name, path in self._config_registry.items():
            if path == self.active_tagger_config_path:
                target_name = name
                break
                
        if target_name:
            self.recent_combo.set(target_name)
        else:
            self.recent_combo.current(0)

    def _switch_config(self, config_path):
        """Carga, valida y aplica una configuración en caliente sin reiniciar."""
        if not config_path or not os.path.exists(config_path):
            messagebox.showerror("Error", f"Ruta de configuración inválida:\n{config_path}", parent=self)
            return

        try:
            # Cargar y aplicar a app_config en memoria
            tagger_cfg = load_tagger_config(config_path)
            apply_tagger_config(tagger_cfg, self.config_data)

            # Actualizar listas internas del tagger
            gui = self.config_data.get("GUI_Tagger", {})
            self.species_tags = gui.get("species_tags", [])
            self.secondary_tags = gui.get("secondary_tags", [])
            self.behavior_tags = gui.get("behavior_tags", [])
            self.other_tags_list = gui.get("other_tags_list", [])
            # 🔒 NUEVO: Cargar optional_tags
            self.optional_tags = gui.get("optional_tags", [])
            self.taxon_map = gui.get("taxon_map", {})

            # Persistir historial en config.ini
            update_recent_configs(self.config_data, config_path)

            # Refrescar UI y frames
            self._rebuild_tag_buttons()
            self.show_frame()
            
            # Feedback visual discreto
            self.config_btn.config(fg="#2E7D32")
            self.after(800, lambda: self.config_btn.config(fg="black"))

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar la configuración:\n{e}", parent=self)

    def open_config_selector(self):
        win = tk.Toplevel(self)
        win.title("Configuraciones del Tagger")
        win.geometry("520x460")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=f"Config activa: {self.active_tagger_config_name or 'Por defecto'}",
                 font=("Arial", 10, "italic"), fg="#555").pack(pady=(8, 2))

        # 🔹 Filtros (solo en modo estándar)
        self._filter_frame = tk.Frame(win)
        if not self.scientific_mode:
            self._filter_frame.pack(pady=5)
            self.filter_sci_var = tk.BooleanVar(value=True)
            self.filter_std_var = tk.BooleanVar(value=True)
            tk.Checkbutton(self._filter_frame, text="Mostrar científicas", variable=self.filter_sci_var,
                           command=self._update_selector_listbox).pack(side="left", padx=10)
            tk.Checkbutton(self._filter_frame, text="Mostrar estándar", variable=self.filter_std_var,
                           command=self._update_selector_listbox).pack(side="left", padx=10)

        list_frame = tk.Frame(win)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.selector_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Arial", 11))
        self.selector_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.selector_listbox.yview)

        self._selector_configs = []
        self._update_selector_listbox()

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=8)

        def on_load():
            sel = self.selector_listbox.curselection()
            if not sel:
                messagebox.showwarning("Atención", "Seleccione una configuración.", parent=win)
                return
            cfg = self._selector_configs[sel[0]]
            if self.scientific_mode and not cfg.get("is_scientific", False):
                messagebox.showwarning("Modo Científico",
                    "Está cargando una configuración no marcada como científica.\n"
                    "Algunas columnas de taxonID o coordenadas podrían quedar vacías en Camtrap DP.", parent=win)
            self._apply_and_reload_config(cfg["path"], cfg["name"])
            win.destroy()

        tk.Button(btn_frame, text="Cargar", width=10, bg="#4CAF50", fg="black", command=on_load).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Nueva", width=10, bg="#2196F3", fg="black", 
                  command=lambda: [win.destroy(), self.open_config_editor()]).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Editar", width=10, bg="#FF9800", fg="black", 
                  command=self._edit_selected_config).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancelar", width=10, command=win.destroy).pack(side="left", padx=5)

    def _update_selector_listbox(self):
        if not hasattr(self, 'selector_listbox'): return
        self.selector_listbox.delete(0, "end")
        self._selector_configs = []
        configs_dir = get_tagger_configs_dir()
        if not os.path.exists(configs_dir): return

        for fname in sorted(os.listdir(configs_dir)):
            if not fname.endswith(".json"): continue
            fpath = os.path.join(configs_dir, fname)
            try:
                data = load_tagger_config(fpath)
                meta = data.get("_metadata", {})
                is_sci = meta.get("is_scientific", False)
                name = meta.get("name", fname)

                # 🔹 Lógica de filtrado
                if self.scientific_mode:
                    if not is_sci: continue
                else:
                    if is_sci and not getattr(self, 'filter_sci_var', tk.BooleanVar(value=True)).get(): continue
                    if not is_sci and not getattr(self, 'filter_std_var', tk.BooleanVar(value=True)).get(): continue

                icon = "🔬" if is_sci else "📝"
                self.selector_listbox.insert("end", f"{name}  {icon}")
                self._selector_configs.append({"path": fpath, "name": name, "is_scientific": is_sci})
            except Exception:
                pass

    def _edit_selected_config(self):
        sel = self.selector_listbox.curselection()
        if not sel:
            messagebox.showwarning("Atención", "Seleccione una configuración para editar.")
            return
        cfg = self._selector_configs[sel[0]]
        try:
            data = load_tagger_config(cfg["path"])
            self.open_config_editor(config_path=cfg["path"], config_data=data)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar:\n{e}")

    def _update_config_listbox(self):
        if not hasattr(self, 'config_listbox'): return
        self.config_listbox.delete(0, "end")
        self._all_configs = []
        configs_dir = get_tagger_configs_dir()
        if not os.path.exists(configs_dir): return

        for fname in sorted(os.listdir(configs_dir)):
            if not fname.endswith(".json"): continue
            fpath = os.path.join(configs_dir, fname)
            try:
                data = load_tagger_config(fpath)
                meta = data.get("_metadata", {})
                is_sci = meta.get("is_scientific", False)
                name = meta.get("name", fname)

                if self.scientific_mode:
                    if not is_sci: continue
                else:
                    if is_sci and not self.filter_sci_var.get(): continue
                    if not is_sci and not self.filter_std_var.get(): continue

                label = f"{name} {'🔬' if is_sci else '📝'}"
                self.config_listbox.insert("end", label)
                self._all_configs.append({"path": fpath, "name": name, "is_scientific": is_sci})
            except Exception:
                pass

    def _edit_selected_config(self):
        sel = self.config_listbox.curselection()
        if not sel:
            messagebox.showwarning("Atención", "Seleccione una configuración para editar.")
            return
        cfg = self._all_configs[sel[0]]
        try:
            data = load_tagger_config(cfg["path"])
            self.open_config_editor(config_path=cfg["path"], config_data=data)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar la config:\n{e}")

    def _open_config_creator(self):
        messagebox.showinfo("Módulo en desarrollo",
            "La creación de configuraciones se gestionará desde un módulo externo.\n"
            "Por ahora, edite la configuración por defecto o copie un JSON en 'config/tagger_configs/'.",
            parent=self)

    def _apply_and_reload_config(self, config_path, config_name):
        try:
            data = load_tagger_config(config_path)
            apply_tagger_config(data, self.config_data)
            # 🔹 CRÍTICO: Usar SOLO update_recent_configs
            update_recent_configs(self.config_data, config_path)
            gui_cfg = self.config_data.get("GUI_Tagger", {})
            self.species_tags = gui_cfg.get("species_tags", [])
            self.secondary_tags = gui_cfg.get("secondary_tags", [])
            self.behavior_tags = gui_cfg.get("behavior_tags", [])
            self.other_tags_list = gui_cfg.get("other_tags_list", [])
            # 🔒 NUEVO: Cargar optional_tags
            self.optional_tags = gui_cfg.get("optional_tags", [])
            self.taxon_map = gui_cfg.get("taxon_map", {})
            self.active_tagger_config_path = config_path
            self.active_tagger_config_name = config_name
            self._rebuild_tag_buttons()
            self.show_frame()
            messagebox.showinfo("Config cargada", f"Se aplicó: {config_name}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo aplicar la config:\n{e}")
            

    def _rebuild_tag_buttons(self):
        """Reconstruye todos los botones del tagger según las listas actuales.
        🔒 FIX: Todos los secundarios funcionan como tags + botón 'Otros ▼' separado."""
        # 1. Limpiar referencias internas
        self.main_buttons.clear()
        self.left_buttons.clear()
        self.species_buttons.clear()
        self.behaviors.clear()
        
        # 2. Reconstruir Principales (tag_frame_bottom)
        for w in self.tag_frame_bottom.winfo_children():
            w.destroy()
        
        c1 = self.colors_cfg.get("main_button_1_inactive", "#FFD700")
        c2 = self.colors_cfg.get("main_button_2_inactive", "#87CEEB")
        
        for i, tag in enumerate(self.species_tags[:2]):
            bg = c1 if i == 0 else c2
            b = tk.Button(self.tag_frame_bottom, text=tag, width=23, height=2, bg=bg)
            b.pack(side="left", padx=5)
            b.bind("<Button-1>", lambda e, t=tag: self.species_click(t, left=True, event=e))
            b.bind("<Button-3>", lambda e, t=tag: self.species_click(t, left=False, event=e))
            self.main_buttons.append(b)
            self.species_buttons[tag] = b
        
        # 3. Reconstruir Col3 (Comportamiento + Secundarios)
        for w in self.col3.winfo_children():
            w.destroy()
        
        # Botones comportamiento en col3
        tk.Label(self.col3, text="Comportamiento", font=("Arial", 9, "bold")).pack(pady=(5, 2))
        for tag in self.behavior_tags:
            b = tk.Button(self.col3, text=tag, width=12, bg=self.behavior_inactive_bg)
            b.pack(fill="x", pady=2, padx=5)
            b.bind("<Button-1>", lambda e, t=tag: self.behavior_click(t, event=e))
            self.behaviors[tag] = b
        
        tk.Frame(self.col3, height=2, bd=1, relief="groove").pack(fill="x", padx=5, pady=5)
        tk.Label(self.col3, text="Secundarios", font=("Arial", 9, "bold")).pack(pady=(2, 2))
        
        # 🔒 FIX: TODOS los secundarios funcionan como tags (sin el "primero especial")
        for tag in self.secondary_tags:
            b = tk.Button(self.col3, text=tag, width=12, bg=self.tag_inactive_bg)
            b.pack(fill="x", pady=2, padx=5)
            b.bind("<Button-1>", lambda e, t=tag: self.species_click(t, left=True, event=e))
            b.bind("<Button-3>", lambda e, t=tag: self.species_click(t, left=False, event=e))
            self.species_buttons[tag] = b
            self.left_buttons.append(b)
        
        # 🔒 NUEVO: Botón "Otros ▼" al final, solo si other_tags_list no está vacío
        if self.other_tags_list:
            b = tk.Button(self.col3, text="Otros ▼", width=12, bg=self.tag_inactive_bg)
            b.pack(fill="x", pady=2, padx=5)
            b.bind("<Button-1>", self.show_secondary_dropdown)
            self.left_buttons.append(b)
        
        # 🔒 NUEVO: Reconstruir Categorías Opcionales
        self._rebuild_optional_buttons()

    def _rebuild_optional_buttons(self):
        """Reconstruye los botones de Categorías Opcionales según la config actual.
        🔒 NUEVO: Se llama desde _rebuild_tag_buttons() y _switch_config()."""
        # 1. Destruir widgets anteriores si existen
        if hasattr(self, 'optional_tags_label') and self.optional_tags_label.winfo_exists():
            self.optional_tags_label.destroy()
        if hasattr(self, 'optional_tags_frame') and self.optional_tags_frame.winfo_exists():
            self.optional_tags_frame.destroy()
        
        # 2. Verificar que exista el contenedor padre
        if not hasattr(self, 'col4_bottom'):
            self.optional_buttons = []
            return
        
        # 3. Solo mostrar si hay optional_tags configurados
        if self.optional_tags:
            self.optional_tags_label = tk.Label(self.col4_bottom, text="Categorías Opcionales", 
                                                font=("Arial", 10, "bold"), bg="#e8eaf6")
            self.optional_tags_label.pack(anchor="w", padx=5, pady=(5, 2))
            
            self.optional_tags_frame = tk.Frame(self.col4_bottom, bg="#e8eaf6")
            self.optional_tags_frame.pack(fill="both", expand=True, padx=2, pady=2)
            
            self.optional_buttons = []
            for i, tag in enumerate(self.optional_tags[:6]):  # Máximo 6
                btn = tk.Button(self.optional_tags_frame, text=tag, bg=self.tag_inactive_bg, 
                            font=("Arial", 8), height=1)
                btn.pack(fill="x", pady=1, padx=2)
                btn.bind("<Button-1>", lambda e, idx=i: self._handle_optional_button_click(idx, e))
                self.optional_buttons.append(btn)
        else:
            self.optional_buttons = []

    def open_config_editor(self, config_path=None, config_data=None):
        is_new = config_path is None
        if config_data is None:
            config_data = get_template_tagger_config()
            config_data["GUI_Tagger"]["species_tags"] = list(self.species_tags)
            config_data["GUI_Tagger"]["secondary_tags"] = list(self.secondary_tags)
            config_data["GUI_Tagger"]["behavior_tags"] = list(self.behavior_tags)
            config_data["GUI_Tagger"]["other_tags_list"] = list(self.other_tags_list)
            # 🔒 NUEVO: Incluir optional_tags en el template
            config_data["GUI_Tagger"]["optional_tags"] = list(self.optional_tags)
            config_data["Taxon_Map"] = dict(self.taxon_map)
        win = tk.Toplevel(self)
        win.title("Nueva configuración" if is_new else "Editar configuración")
        win.geometry("820x720")
        win.transient(self)
        win.grab_set()
        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)
        tab_meta = ttk.Frame(notebook)
        notebook.add(tab_meta, text="Información")
        meta = config_data.get("_metadata", {})
        fields_meta = [("Nombre", "name"), ("Versión", "version"), ("Región", "region"), ("Descripción", "description")]
        meta_entries = {}
        for row_i, (label, key) in enumerate(fields_meta):
            tk.Label(tab_meta, text=label + ": ", font=("Arial", 11)).grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
            e = tk.Entry(tab_meta, width=50, font=("Arial", 11))
            e.grid(row=row_i, column=1, padx=8, pady=4, sticky="w")
            e.insert(0, meta.get(key, ""))
            meta_entries[key] = e
        # 🔹 CHECKBOX MODO CIENTÍFICO
        self._editor_is_sci_var = tk.BooleanVar(value=meta.get("is_scientific", False))
        tk.Checkbutton(tab_meta, text="Configuración Científica (requerida para Camtrap DP)", 
                    variable=self._editor_is_sci_var, font=("Arial", 10, "bold")
        ).grid(row=len(fields_meta), column=0, columnspan=2, sticky="w", padx=8, pady=10)
        tab_tags = ttk.Frame(notebook)
        notebook.add(tab_tags, text="Tags")
        gui_t = config_data.get("GUI_Tagger", {})
        tag_fields = [("Especies principales", "species_tags"), ("Tags secundarios", "secondary_tags"), 
                    ("Comportamientos", "behavior_tags"), ("Lista 'Otros'", "other_tags_list"),
                    ("Categorías opcionales", "optional_tags")]  # 🔒 NUEVO
        tag_texts = {}
        for row_i, (label, key) in enumerate(tag_fields):
            tk.Label(tab_tags, text=label + ": ", font=("Arial", 10)).grid(row=row_i, column=0, sticky="ne", padx=8, pady=4)
            t = tk.Text(tab_tags, width=30, height=5, font=("Arial", 10))
            t.grid(row=row_i, column=1, padx=8, pady=4, sticky="w")
            t.insert("1.0", "\n".join(gui_t.get(key, [])))
            tag_texts[key] = t
        tab_taxon = ttk.Frame(notebook)
        notebook.add(tab_taxon, text="Taxon Map")
        self._build_taxon_map_tab(tab_taxon, config_data)
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=8)
        def on_save():
            name = meta_entries["name"].get().strip()
            if not name:
                messagebox.showwarning("Atención", "El nombre es obligatorio.", parent=win)
                return
            for key, t in tag_texts.items():
                config_data["GUI_Tagger"][key] = [x.strip() for x in t.get("1.0", "end").strip().splitlines() if x.strip()]
            for key, e in meta_entries.items():
                config_data["_metadata"][key] = e.get().strip()
            # 🔹 Guardar flag científico
            config_data["_metadata"]["is_scientific"] = self._editor_is_sci_var.get()
            nonlocal config_path
            if is_new or not config_path:
                safe_name = name.lower().replace(" ", "_").replace("/", "-")
                config_path = os.path.join(get_tagger_configs_dir(), f"{safe_name}.json")
            try:
                save_tagger_config(config_path, config_data)
                messagebox.showinfo("Guardado", f"Configuración guardada:\n{config_path}", parent=win)
                win.destroy()
                if messagebox.askyesno("Cargar", "¿Aplicar esta configuración ahora?"):
                    self._apply_and_reload_config(config_path, name)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=win)
        tk.Button(btn_frame, text="Guardar", width=12, bg="#4CAF50", fg="black", command=on_save).pack(side="left", padx=8)
        tk.Button(btn_frame, text="Cancelar", width=12, command=win.destroy).pack(side="left", padx=8)
        
    
        def on_save():
            name = meta_entries["name"].get().strip()
            if not name:
                messagebox.showwarning("Atención", "El nombre es obligatorio.", parent=win)
                return
            for key, t in tag_texts.items():
                config_data["GUI_Tagger"][key] = [x.strip() for x in t.get("1.0", "end").strip().splitlines() if x.strip()]
            for key, e in meta_entries.items():
                config_data["_metadata"][key] = e.get().strip()
            
            # 🔹 Guardar flag científico
            config_data["_metadata"]["is_scientific"] = self._editor_is_sci_var.get()

            nonlocal config_path
            if is_new or not config_path:
                safe_name = name.lower().replace(" ", "_").replace("/", "-")
                config_path = os.path.join(get_tagger_configs_dir(), f"{safe_name}.json")
            try:
                save_tagger_config(config_path, config_data)
                messagebox.showinfo("Guardado", f"Configuración guardada:\n{config_path}", parent=win)
                win.destroy()
                if messagebox.askyesno("Cargar", "¿Aplicar esta configuración ahora?"):
                    self._apply_and_reload_config(config_path, name)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=win)

        tk.Button(btn_frame, text="Guardar", width=12, bg="#4CAF50", fg="black", command=on_save).pack(side="left", padx=8)
        tk.Button(btn_frame, text="Cancelar", width=12, command=win.destroy).pack(side="left", padx=8)

    def _build_taxon_map_tab(self, parent, config_data):
        taxon_map = config_data.setdefault("Taxon_Map", {})

        # --- Panel superior: buscador ---
        search_frame = tk.LabelFrame(parent, text="Buscar taxón", font=("Arial", 10, "bold"))
        search_frame.pack(fill="x", padx=8, pady=5)

        search_row = tk.Frame(search_frame)
        search_row.pack(fill="x", padx=5, pady=4)

        tk.Label(search_row, text="Búsqueda: ").pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_row, textvariable=search_var, width=30)
        search_entry.pack(side="left", padx=5)

        status_var = tk.StringVar(value="")
        status_lbl = tk.Label(search_frame, textvariable=status_var, fg="#555", font=("Arial", 9, "italic"))
        status_lbl.pack(anchor="w", padx=5)

        results_frame = tk.Frame(search_frame)
        results_frame.pack(fill="x", padx=5, pady=3)

        res_scroll = tk.Scrollbar(results_frame)
        res_scroll.pack(side="right", fill="y")

        results_listbox = tk.Listbox(results_frame, height=5, yscrollcommand=res_scroll.set, font=("Arial", 10))
        results_listbox.pack(fill="x", side="left", expand=True)
        res_scroll.config(command=results_listbox.yview)

        _search_results = []

        def update_ui(results, source_name="Local"):
            _search_results.clear()
            _search_results.extend(results)
            results_listbox.delete(0, "end")
            if not results:
                status_var.set(f"No se encontraron resultados en {source_name}.")
                return
            for r in results:
                label = f"{r.get('vernacularName','')} | {r.get('scientificName','')} | ID:{r.get('taxonID','')}"
                results_listbox.insert("end", label)
            status_var.set(f"{len(results)} resultado(s) de {source_name}.")

        def do_search_local():
            q = search_var.get().strip()
            if not q: return
            # Búsqueda directa en el CSV
            results = self._search_local_csv(q)
            update_ui(results, "species_list.csv")

        def do_search_gbif():
            q = search_var.get().strip()
            if not q: return
            status_var.set("Buscando en GBIF (puede tardar)...")
            parent.update_idletasks()
            def _bg():
                try:
                    from config_utils import search_taxa_gbif
                    results = search_taxa_gbif(q)
                    parent.after(0, lambda: update_ui(results, "GBIF"))
                except Exception:
                    # Fallback automático a local si falla GBIF
                    parent.after(0, lambda: status_var.set("Error GBIF. Buscando en local..."))
                    parent.after(0, lambda: do_search_local_fallback(q))
            threading.Thread(target=_bg, daemon=True).start()

        def do_search_local_fallback(q):
            results = self._search_local_csv(q)
            parent.after(0, lambda: update_ui(results, "Local (Fallback)"))

        btn_search_row = tk.Frame(search_frame)
        btn_search_row.pack(fill="x", padx=5, pady=(0, 5))
        tk.Button(btn_search_row, text="Buscar Local", command=do_search_local, bg="#e0e0e0", fg="black").pack(side="left", padx=3)
        tk.Button(btn_search_row, text="Buscar GBIF", command=do_search_gbif, bg="#bbdefb", fg="black").pack(side="left", padx=3)

        search_entry.bind("<Return>", lambda e: do_search_gbif()) # Enter intenta GBIF, si falla usa local

        # Campo para nombre del tag a asignar
        assign_frame = tk.Frame(search_frame)
        assign_frame.pack(fill="x", padx=5, pady=3)

        tk.Label(assign_frame, text="Asignar a tag: ").pack(side="left")
        tag_assign_var = tk.StringVar()
        tag_assign_entry = tk.Entry(assign_frame, textvariable=tag_assign_var, width=20)
        tag_assign_entry.pack(side="left", padx=5)

        # --- Panel inferior: Taxon Map actual ---
        map_frame = tk.LabelFrame(parent, text="Taxon Map activo", font=("Arial", 10, "bold"))
        map_frame.pack(fill="both", expand=True, padx=8, pady=5)

        map_scroll = tk.Scrollbar(map_frame)
        map_scroll.pack(side="right", fill="y")

        map_listbox = tk.Listbox(map_frame, yscrollcommand=map_scroll.set, font=("Arial", 10))
        map_listbox.pack(fill="both", expand=True)
        map_scroll.config(command=map_listbox.yview)

        def refresh_map_listbox():
            map_listbox.delete(0, "end")
            for tag, info in taxon_map.items():
                map_listbox.insert("end", f"{tag}  →  taxonID: {info.get('taxonID', '')}")

        refresh_map_listbox()

        def on_assign():
            sel = results_listbox.curselection()
            if not sel:
                messagebox.showwarning("Atención", "Seleccione un resultado.", parent=parent)
                return
            tag_name = tag_assign_var.get().strip()
            if not tag_name:
                messagebox.showwarning("Atención", "Ingrese el tag a asignar.", parent=parent)
                return
            result = _search_results[sel[0]]
            taxon_map[tag_name] = {
                "taxonID": result.get("taxonID", ""),
                "scientificName": result.get("scientificName", ""),
                "vernacularName": result.get("vernacularName", "")
            }
        
            config_data["Taxon_Map"] = taxon_map
            refresh_map_listbox()
            tag_assign_var.set("")

        def on_remove():
            sel = map_listbox.curselection()
            if not sel: return
            item_text = map_listbox.get(sel[0])
            tag_name = item_text.split("→")[0].strip()
            taxon_map.pop(tag_name, None)
            config_data["Taxon_Map"] = taxon_map
            refresh_map_listbox()

        map_btn_frame = tk.Frame(parent)
        map_btn_frame.pack(pady=3)
        tk.Button(map_btn_frame, text="Asignar taxón", bg="#4CAF50", fg="black", command=on_assign).pack(side="left", padx=5)
        tk.Button(map_btn_frame, text="Quitar entrada", bg="#f44336", fg="black", command=on_remove).pack(side="left", padx=5)

    def _get_tag_type(self, tag):
        if tag in self.species_tags: return "species"
        if tag in self.secondary_tags: return "secondary"
        if tag in self.behavior_tags: return "behavior"
        return "unknown"

    def _sync_renamed_tag(self, old_tag, new_tag, tag_type):
        """Actualiza explícitamente la lista interna y el taxon_map en memoria."""
        if tag_type == "species": target_list = self.species_tags
        elif tag_type == "secondary": target_list = self.secondary_tags
        elif tag_type == "behavior": target_list = self.behavior_tags
        else: return

        if old_tag in target_list:
            idx = target_list.index(old_tag)
            target_list[idx] = new_tag

        if old_tag in self.taxon_map:
            self.taxon_map[new_tag] = self.taxon_map.pop(old_tag)


    def _mark_changed(self):
        if not self._has_unsaved_changes:
            self._has_unsaved_changes = True
            # Aquí va la lógica para mostrar tu botón 💾 Guardar Config
            if hasattr(self, 'save_config_btn'):
                self.save_config_btn.pack(fill="x", pady=2, padx=5)
            if hasattr(self, 'config_btn'):
                self.config_btn.config(fg="#d32f2f")

    def _clear_changes_flag(self):
        self._has_unsaved_changes = False
        self.save_config_btn.pack_forget()
        self.config_btn.config(fg="black")

    def _prompt_save_config(self):
        win = tk.Toplevel(self)
        win.title("💾 Guardar Configuración")
        win.geometry("400x220")
        win.transient(self)
        win.grab_set()

        current_name = self.active_tagger_config_name or "Actual"
        tk.Label(win, text=f"Config activa: {current_name}", font=("Arial", 10, "bold")).pack(pady=8)

        mode_var = tk.StringVar(value="new")
        tk.Radiobutton(win, text="🆕 Crear nueva configuración", variable=mode_var, value="new").pack(anchor="w", padx=20)
        tk.Radiobutton(win, text="📝 Sobreescribir configuración actual", variable=mode_var, value="overwrite").pack(anchor="w", padx=20)

        name_frame = tk.Frame(win)
        name_frame.pack(pady=8, fill="x", padx=20)
        tk.Label(name_frame, text="Nombre: ").pack(side="left")
        name_var = tk.StringVar(value=f"{current_name}_edit")
        name_entry = tk.Entry(name_frame, textvariable=name_var, width=30)
        name_entry.pack(side="left", fill="x", expand=True, padx=5)

        def on_save():
            mode = mode_var.get()
            target_name = name_var.get().strip()
            if not target_name:
                messagebox.showwarning("Atención", "Ingresa un nombre válido.", parent=win)
                return

            if mode == "overwrite" and self.active_tagger_config_path:
                if not messagebox.askyesno("Confirmar", f"¿Sobreescribir {current_name}?\nEsta acción no se puede deshacer.", parent=win):
                    return
                self._execute_save(overwrite=True)
            else:
                self._execute_save(new_name=target_name)
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Guardar", bg="#4CAF50", fg="white", command=on_save).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="left", padx=10)

    def _execute_save(self, new_name=None, overwrite=False):
        try:
            from config_utils import save_tagger_config, update_recent_configs, get_tagger_configs_dir
            # Construir dict desde estado actual
            config_dict = {
                "_metadata": {
                    "name": new_name or self.active_tagger_config_name,
                    "version": "1.0",
                    "country_id": self.config_data.get("_metadata", {}).get("country_id", ""),
                    "linked_region_id": self.config_data.get("_metadata", {}).get("linked_region_id", ""),
                    "is_scientific": self.config_data.get("_metadata", {}).get("is_scientific", False),
                    "created": self.config_data.get("_metadata", {}).get("created", datetime.now().strftime("%Y-%m-%d")),
                    "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M")
                },
                "GUI_Tagger": {
                    "species_tags": self.species_tags,
                    "secondary_tags": self.secondary_tags,
                    "behavior_tags": self.behavior_tags,
                    "other_tags_list": self.other_tags_list,
                    "optional_tags": self.optional_tags,  # 🔒 NUEVO
                    "colors": self.colors_cfg,
                    "labels": self.labels_cfg,
                    "buttons": self.buttons_cfg
                },
                "Taxon_Map": self.taxon_map
            }
            if overwrite:
                target_path = self.active_tagger_config_path
            else:
                safe_name = new_name.lower().replace(" ", "_").replace("/", "-")
                target_path = os.path.join(get_tagger_configs_dir(), f"{safe_name}.json")
                # Evitar colisión
                counter = 1
                while os.path.exists(target_path):
                    target_path = os.path.join(get_tagger_configs_dir(), f"{safe_name}_{counter}.json")
                    counter += 1
            # Guardar en disco
            save_tagger_config(target_path, config_dict)
            update_recent_configs(self.config_data, target_path)
            # Actualizar UI y estado
            self.active_tagger_config_path = target_path
            self.active_tagger_config_name = config_dict["_metadata"]["name"]
            self._clear_changes_flag()
            # Refrescar dropdown del tagger (si usas la lógica de la Etapa 1)
            if hasattr(self, '_scan_and_populate_dropdown'):
                self._scan_and_populate_dropdown()
            messagebox.showinfo("Éxito", f"Configuración guardada:\n{os.path.basename(target_path)}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self)

            
def run_gui_tagger():
    app = DynamicTagger()
    app.mainloop()

if __name__ == "__main__":
    run_gui_tagger()
