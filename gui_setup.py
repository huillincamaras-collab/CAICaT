import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
import csv
from config_utils import (
    load_config, save_config,
    load_country_species, add_species_to_master, get_available_countries,
    get_tagger_configs_dir
)
from procesamiento import FPS_EXTRACT, BUFFER_N, TOP_K, DOWNSAMPLE_MAX, JPEG_QUALITY, MASK_QUALITY


class SetupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CAICAT - Configuración del Sistema")
        self.geometry("950x750")
        self.font_large = ("Arial", 11)

        try:
            self.config_data = load_config()
        except Exception as e:
            messagebox.showerror("Error Crítico", f"No se pudo cargar config.ini:\n{e}")
            self.destroy()
            return

        # --- País activo para gestión de taxones ---
        self.current_country_id = self._detect_active_country()
        self.available_countries = get_available_countries()

        # Notebook principal
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        self.tabs = {}
        self.create_general_tab()
        self.create_gui_tagger_tab()
        self.create_main_tab()
        self.create_gui_inicial_tab()
        self.create_inabio_tab()  # 🆕 NUEVO TAB

        # Botones de acción global
        action_frame = tk.Frame(self)
        action_frame.pack(pady=10)
        tk.Button(action_frame, text="Guardar y Salir", font=self.font_large,
                  command=self.save_all, bg="#4CAF50", fg="white").pack(side="left", padx=15)
        tk.Button(action_frame, text="Cancelar", font=self.font_large, command=self.destroy).pack(side="left", padx=15)

    # -------------------------
    # Helpers: detección de país activo
    # -------------------------
    def _detect_active_country(self):
        """Detecta el country_id de la config activa o devuelve 'ecuador' por defecto."""
        gui_tagger = self.config_data.get("GUI_Tagger", {})
        country_id = gui_tagger.get("country_id", "")
        if country_id:
            return country_id
        # Intentar detectar desde configs recientes
        recent = self.config_data.get("General", {}).get("last_used_configs", [])
        if recent:
            try:
                import json
                with open(recent[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                cid = data.get("_metadata", {}).get("country_id", "")
                if cid:
                    return cid
            except Exception:
                pass
        return "ecuador"

    def _get_country_name(self, country_id):
        """Retorna el nombre legible de un país."""
        for c in self.available_countries:
            if c["country_id"] == country_id:
                return c["name"]
        return country_id.title()

    def _on_country_change(self, event=None):
        """Actualiza el país activo cuando el usuario cambia el selector."""
        selected = self.country_var.get()
        # El formato del combobox es "Nombre (id)"
        if " (" in selected and selected.endswith(")"):
            country_id = selected.split(" (")[-1][:-1]
        else:
            country_id = selected.lower()
        self.current_country_id = country_id
        self._update_country_status()

    def _update_country_status(self):
        """Actualiza el label de estado del país activo."""
        name = self._get_country_name(self.current_country_id)
        species_list = load_country_species(self.current_country_id)
        count = len(species_list) if species_list else 0
        self._country_status_var.set(
            f"País activo: {name} ({count} especies en el master)"
        )

    # ------------------------
    # Tab General
    # ------------------------
    def create_general_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="General & Paths")
        self.tabs['General'] = tab
        gen = self.config_data.get("General", {})
        meta = self.config_data.get("MetadataSettings", {})

        general_frame = tk.LabelFrame(tab, text="Rutas y Archivos", font=self.font_large)
        general_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(general_frame, text="Carpeta de Salida (Output):", font=self.font_large).grid(row=0, column=0, sticky="e", pady=5)
        self.output_entry = tk.Entry(general_frame, width=60, font=self.font_large)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5)
        self.output_entry.insert(0, gen.get("output_folder", ""))
        tk.Label(general_frame, text="Archivo JSON Principal:", font=self.font_large).grid(row=1, column=0, sticky="e", pady=5)
        self.json_entry = tk.Entry(general_frame, width=60, font=self.font_large)
        self.json_entry.grid(row=1, column=1, padx=5, pady=5)
        self.json_entry.insert(0, gen.get("json_file", ""))

        proc_frame = tk.LabelFrame(tab, text="Parámetros de Procesamiento", font=self.font_large)
        proc_frame.pack(fill="x", padx=10, pady=10)
        vars_proc = {
            "FPS_EXTRACT": FPS_EXTRACT,
            "BUFFER_N": BUFFER_N,
            "TOP_K": TOP_K,
            "DOWNSAMPLE_MAX": DOWNSAMPLE_MAX,
            "JPEG_QUALITY": JPEG_QUALITY,
            "MASK_QUALITY": MASK_QUALITY
        }
        self.proc_entries = {}
        for i, (k, v) in enumerate(vars_proc.items()):
            tk.Label(proc_frame, text=f"{k}:", font=self.font_large).grid(row=i, column=0, sticky="e", pady=2)
            e = tk.Entry(proc_frame, width=10, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=2)
            e.insert(0, str(v))
            self.proc_entries[k] = e

        meta_frame = tk.LabelFrame(tab, text="Configuración de Metadatos", font=self.font_large)
        meta_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(meta_frame, text="Campos para Embed (separados por coma):", font=self.font_large).grid(row=0, column=0, sticky="ne", pady=5)
        self.fields_embed_text = tk.Text(meta_frame, width=60, height=3, font=self.font_large)
        self.fields_embed_text.grid(row=0, column=1, padx=5, pady=2)
        self.fields_embed_text.insert("1.0", ", ".join(meta.get("fields_to_embed", [])))

        # --- Editor de ExcelFieldsDefault ---
        tk.Label(meta_frame, text="Campos Default Excel (separados por coma):", font=self.font_large).grid(row=1, column=0, sticky="ne", pady=5)
        self.excel_fields_text = tk.Text(meta_frame, width=60, height=3, font=self.font_large)
        self.excel_fields_text.grid(row=1, column=1, padx=5, pady=2)
        self.excel_fields_text.insert("1.0", ", ".join(meta.get("ExcelFieldsDefault", [])))

    # ------------------------
    # Tab GUI Tagger
    # ------------------------
    def create_gui_tagger_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="GUI Tagger")
        self.tabs['GUI_Tagger'] = tab
        gui_tag = self.config_data.get("GUI_Tagger", {})

        # Scroll container
        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- Selector de país activo ---
        country_frame = tk.LabelFrame(scroll_frame, text=" País Activo (para gestión de taxones)", font=("Arial", 11, "bold"))
        country_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        tk.Label(country_frame, text="País:", font=self.font_large).grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.country_var = tk.StringVar(value=f"{self._get_country_name(self.current_country_id)} ({self.current_country_id})")
        country_names = [f"{c['name']} ({c['country_id']})" for c in self.available_countries]
        if not country_names:
            country_names = [f"{self._get_country_name(self.current_country_id)} ({self.current_country_id})"]
        self.country_combo = ttk.Combobox(country_frame, textvariable=self.country_var, values=country_names, state="readonly", width=40)
        self.country_combo.grid(row=0, column=1, padx=5, pady=5)
        self.country_combo.bind("<<ComboboxSelected>>", self._on_country_change)

        self._country_status_var = tk.StringVar(value="")
        tk.Label(country_frame, textvariable=self._country_status_var, fg="#1976d2", font=("Arial", 9)).grid(row=1, column=0, columnspan=2, padx=5, pady=2)
        self._update_country_status()

        # --- Campos básicos ---
        tk.Label(scroll_frame, text="Título de la Ventana:", font=self.font_large).grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.gui_tag_title = tk.Entry(scroll_frame, width=40, font=self.font_large)
        self.gui_tag_title.grid(row=1, column=1, padx=5, pady=5)
        self.gui_tag_title.insert(0, gui_tag.get("title", ""))

        tk.Label(scroll_frame, text="Geometría (AnchoxAlto):", font=self.font_large).grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.gui_tag_geom = tk.Entry(scroll_frame, width=40, font=self.font_large)
        self.gui_tag_geom.grid(row=2, column=1, padx=5, pady=5)
        self.gui_tag_geom.insert(0, gui_tag.get("geometry", ""))

        tk.Label(scroll_frame, text="Tags de Especies (principal):", font=self.font_large).grid(row=3, column=0, sticky="ne", padx=5, pady=5)
        self.species_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.species_tags_text.grid(row=3, column=1, padx=5, pady=5)
        self.species_tags_text.insert("1.0", ", ".join(gui_tag.get("species_tags", [])))

        tk.Label(scroll_frame, text="Tags Secundarios:", font=self.font_large).grid(row=4, column=0, sticky="ne", padx=5, pady=5)
        self.secondary_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.secondary_tags_text.grid(row=4, column=1, padx=5, pady=5)
        self.secondary_tags_text.insert("1.0", ", ".join(gui_tag.get("secondary_tags", [])))

        tk.Label(scroll_frame, text="Tags de Comportamiento:", font=self.font_large).grid(row=5, column=0, sticky="ne", padx=5, pady=5)
        self.behavior_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.behavior_tags_text.grid(row=5, column=1, padx=5, pady=5)
        self.behavior_tags_text.insert("1.0", ", ".join(gui_tag.get("behavior_tags", [])))

        tk.Label(scroll_frame, text="Lista 'Otros' (Desplegable):", font=self.font_large).grid(row=6, column=0, sticky="ne", padx=5, pady=5)
        self.other_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.other_tags_text.grid(row=6, column=1, padx=5, pady=5)
        self.other_tags_text.insert("1.0", ", ".join(gui_tag.get("other_tags_list", [])))

        # --- Separador ---
        ttk.Separator(scroll_frame, orient="horizontal").grid(row=7, column=0, columnspan=3, sticky="ew", pady=15)

        # --- Buscador de taxones (apunta al master del país) ---
        taxon_lbl = tk.Label(scroll_frame, text="Gestión de Taxones (Master del País)", font=("Arial", 12, "bold"))
        taxon_lbl.grid(row=8, column=0, columnspan=3, sticky="w", padx=5, pady=(0, 5))
        self._build_taxon_searcher(scroll_frame, start_row=9)

    def _build_taxon_searcher(self, parent, start_row):
        """Buscador de taxones embebido en el tab GUI Tagger del Setup."""
        search_frame = tk.LabelFrame(parent, text="Buscar y Agregar al Master del País", font=("Arial", 11))
        search_frame.grid(row=start_row, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

        # Fila de búsqueda
        row0 = tk.Frame(search_frame)
        row0.pack(fill="x", padx=5, pady=4)
        tk.Label(row0, text="Término de búsqueda:", font=("Arial", 11)).pack(side="left")
        self._taxon_search_var = tk.StringVar()
        search_entry = tk.Entry(row0, textvariable=self._taxon_search_var, width=30, font=("Arial", 11))
        search_entry.pack(side="left", padx=5)

        self._taxon_status_var = tk.StringVar(value="")
        tk.Label(search_frame, textvariable=self._taxon_status_var, fg="#555",
                 font=("Arial", 9, "italic")).pack(anchor="w", padx=5)

        # Listbox de resultados
        res_frame = tk.Frame(search_frame)
        res_frame.pack(fill="x", padx=5, pady=2)
        res_scroll = tk.Scrollbar(res_frame)
        res_scroll.pack(side="right", fill="y")
        self._taxon_results_listbox = tk.Listbox(res_frame, height=5, yscrollcommand=res_scroll.set,
                                                  font=("Arial", 10))
        self._taxon_results_listbox.pack(fill="x", side="left", expand=True)
        res_scroll.config(command=self._taxon_results_listbox.yview)
        self._taxon_search_results = []

        # Botones de búsqueda
        btn_row = tk.Frame(search_frame)
        btn_row.pack(fill="x", padx=5, pady=(0, 4))
        tk.Button(btn_row, text="Buscar en Master Local", command=self._do_search_local, bg="#e0e0e0").pack(side="left", padx=3)
        tk.Button(btn_row, text="Buscar GBIF (Online)", command=self._do_search_gbif, bg="#bbdefb").pack(side="left", padx=3)
        search_entry.bind("<Return>", lambda e: self._do_search_local())

        # Asignar al master
        assign_frame = tk.Frame(search_frame)
        assign_frame.pack(fill="x", padx=5, pady=3)
        tk.Label(assign_frame, text="Acción:", font=("Arial", 10)).pack(side="left")
        tk.Button(assign_frame, text="Agregar Seleccionado al Master",
                  bg="#4CAF50", fg="white",
                  command=self._add_selected_taxon_to_master).pack(side="left", padx=5)

    def _do_search_local(self):
        """Busca en el master del país activo."""
        q = self._taxon_search_var.get().strip()
        if not q:
            return

        species_list = load_country_species(self.current_country_id)
        if not species_list:
            self._taxon_status_var.set(f"⚠️ No hay especies en el master de '{self.current_country_id}'")
            self._taxon_results_listbox.delete(0, "end")
            self._taxon_search_results = []
            return

        q_lower = q.lower()
        results = []
        for sp in species_list:
            sci = sp.get("scientificName", "").lower()
            common = sp.get("commonName", sp.get("vernacularName", "")).lower()
            family = sp.get("family", "").lower()
            searchable = f"{sci} {common} {family}"
            if q_lower in searchable:
                results.append(sp)
                if len(results) >= 50:
                    break

        self._taxon_search_results = results
        self._taxon_results_listbox.delete(0, "end")
        for r in results:
            label = f"{r.get('commonName', r.get('vernacularName', ''))} | {r.get('scientificName', '')} | GBIF:{r.get('taxonID_GBIF', r.get('taxonID', ''))}"
            self._taxon_results_listbox.insert("end", label)

        self._taxon_status_var.set(f"{len(results)} resultado(s) en master de '{self.current_country_id}'.")

    def _do_search_gbif(self):
        """Busca en GBIF (online). Los resultados se podrán agregar al master del país."""
        q = self._taxon_search_var.get().strip()
        if not q:
            return
        self._taxon_status_var.set("Buscando en GBIF (puede tardar unos segundos)...")
        self.update_idletasks()

        def _bg():
            try:
                from config_utils import search_taxa_gbif
                results = search_taxa_gbif(q)
                self.after(0, lambda: self._show_gbif_results(results))
            except Exception as e:
                self.after(0, lambda: self._taxon_status_var.set(f"Error en GBIF: {e}"))

        threading.Thread(target=_bg, daemon=True).start()

    def _show_gbif_results(self, results):
        """Muestra resultados de GBIF en el listbox."""
        self._taxon_search_results = results
        self._taxon_results_listbox.delete(0, "end")
        for r in results:
            label = f"{r.get('vernacularName', '')} | {r.get('scientificName', '')} | GBIF:{r.get('taxonID', '')}"
            self._taxon_results_listbox.insert("end", label)
        self._taxon_status_var.set(f"{len(results)} resultado(s) de GBIF. Seleccione uno para agregar al master.")

    def _add_selected_taxon_to_master(self):
        """Agrega la especie seleccionada al master del país activo."""
        sel = self._taxon_results_listbox.curselection()
        if not sel:
            messagebox.showwarning("Atención", "Seleccione un resultado de la lista primero.")
            return

        result = self._taxon_search_results[sel[0]]
        country_id = self.current_country_id

        species_data = {
            "scientificName": result.get("scientificName", ""),
            "commonName": result.get("vernacularName", result.get("commonName", "")),
            "taxonID_GBIF": str(result.get("taxonID", result.get("taxonID_GBIF", ""))),
            "taxonID_iNaturalist": result.get("taxonID_iNaturalist", ""),
            "taxonRank": result.get("taxonRank", result.get("rank", "species")),
            "kingdom": result.get("kingdom", "Animalia"),
            "family": result.get("family", ""),
            "order": result.get("order", ""),
            "class": result.get("class", ""),
            "genus": result.get("genus", ""),
            "category": "species"
        }

        if not species_data["scientificName"]:
            messagebox.showerror("Error", "La especie seleccionada no tiene nombre científico.")
            return

        success = add_species_to_master(country_id, species_data)

        if success:
            messagebox.showinfo(
                "Éxito",
                f"'{species_data['scientificName']}' agregada al master de '{country_id}'.\n\n"
                f"GBIF ID: {species_data['taxonID_GBIF']}"
            )
            self._taxon_search_var.set("")
            self._do_search_local()
            self._update_country_status()
        else:
            messagebox.showwarning(
                "Duplicado",
                f"La especie '{species_data['scientificName']}' ya existe en el master de '{country_id}'."
            )

    # ------------------------
    # Tab Main Buttons
    # ------------------------
    def create_main_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Menú Principal")
        self.tabs['Main'] = tab
        labels = self.config_data.get("Labels", {})
        self.main_entries = {}
        for i, (key, val) in enumerate(labels.items()):
            tk.Label(tab, text=f"Texto Botón '{key}':", font=self.font_large).grid(row=i, column=0, sticky="e", pady=5)
            e = tk.Entry(tab, width=40, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=5)
            e.insert(0, val)
            self.main_entries[key] = e

    # ------------------------
    # Tab GUI Inicial
    # ------------------------
    def create_gui_inicial_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Pantalla Inicial")
        self.tabs['GUI_Inicial'] = tab
        gui_ini = self.config_data.get("GUI_Inicial", {})
        tk.Label(tab, text="Título:", font=self.font_large).grid(row=0, column=0, sticky="e", pady=5)
        self.gui_ini_title = tk.Entry(tab, width=40, font=self.font_large)
        self.gui_ini_title.grid(row=0, column=1, padx=5, pady=5)
        self.gui_ini_title.insert(0, gui_ini.get("title", ""))
        tk.Label(tab, text="Geometría:", font=self.font_large).grid(row=1, column=0, sticky="e", pady=5)
        self.gui_ini_geom = tk.Entry(tab, width=40, font=self.font_large)
        self.gui_ini_geom.grid(row=1, column=1, padx=5, pady=5)
        self.gui_ini_geom.insert(0, gui_ini.get("geometry", ""))
        tk.Label(tab, text="Etiquetas de Campos (key,value):", font=self.font_large).grid(row=2, column=0, sticky="ne", pady=5)
        self.gui_ini_labels = tk.Text(tab, width=40, height=6, font=self.font_large)
        self.gui_ini_labels.grid(row=2, column=1, padx=5, pady=5)
        labels_text = "\n".join([f"{k},{v}" for k, v in gui_ini.get("labels", {}).items()])
        self.gui_ini_labels.insert("1.0", labels_text)
        tk.Label(tab, text="Etiquetas de Botones (key,value):", font=self.font_large).grid(row=3, column=0, sticky="ne", pady=5)
        self.gui_ini_buttons = tk.Text(tab, width=40, height=4, font=self.font_large)
        self.gui_ini_buttons.grid(row=3, column=1, padx=5, pady=5)
        buttons_text = "\n".join([f"{k},{v}" for k, v in gui_ini.get("buttons", {}).items()])
        self.gui_ini_buttons.insert("1.0", buttons_text)

    # ------------------------
    # 🆕 Tab INABIO (Punto 2)
    # ------------------------
    def create_inabio_tab(self):
        """Tab para configurar los campos de exportación a INABIO (Darwin Core)."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="INABIO / Darwin Core")
        self.tabs['INABIO'] = tab

        inabio = self.config_data.get("INABIO", {})

        # Scroll container
        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Descripción
        desc_frame = tk.Frame(scroll_frame, bg="#e3f2fd")
        desc_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(desc_frame, text="📋 Configuración de exportación a INABIO (Darwin Core)",
                 font=("Arial", 12, "bold"), bg="#e3f2fd").pack(anchor="w", padx=10, pady=5)
        tk.Label(desc_frame, text="Estos campos se usarán al exportar datos al formato INABIO.\n"
                                  "Los valores por defecto son los estándar para Ecuador.",
                 font=("Arial", 10), bg="#e3f2fd", justify="left").pack(anchor="w", padx=10, pady=(0, 5))

        # Campos institucionales
        inst_frame = tk.LabelFrame(scroll_frame, text="Institución", font=self.font_large)
        inst_frame.pack(fill="x", padx=10, pady=10)

        self.inabio_entries = {}
        inst_fields = [
            ("institutionCode", "Código de Institución:", "Ej: INABIOEC"),
            ("collectionCode", "Código de Colección:", "Ej: CAMTRAP"),
            ("ownerInstitutionCode", "Código de Institución Dueña:", "Ej: INABIO"),
        ]
        for i, (key, label, hint) in enumerate(inst_fields):
            tk.Label(inst_frame, text=label, font=self.font_large).grid(row=i, column=0, sticky="e", pady=5, padx=5)
            e = tk.Entry(inst_frame, width=40, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=5)
            e.insert(0, inabio.get(key, ""))
            self.inabio_entries[key] = e
            tk.Label(inst_frame, text=hint, font=("Arial", 9), fg="gray").grid(row=i, column=2, sticky="w", padx=5)

        # Campos geográficos y de registro
        geo_frame = tk.LabelFrame(scroll_frame, text="Geografía y Registro", font=self.font_large)
        geo_frame.pack(fill="x", padx=10, pady=10)

        geo_fields = [
            ("country", "País:", "Ej: Ecuador"),
            ("basisOfRecord", "Tipo de Registro:", "HumanObservation / MachineObservation / PreservedSpecimen"),
            ("language", "Idioma:", "es"),
        ]
        for i, (key, label, hint) in enumerate(geo_fields):
            tk.Label(geo_frame, text=label, font=self.font_large).grid(row=i, column=0, sticky="e", pady=5, padx=5)
            e = tk.Entry(geo_frame, width=40, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=5)
            e.insert(0, inabio.get(key, ""))
            self.inabio_entries[key] = e
            tk.Label(geo_frame, text=hint, font=("Arial", 9), fg="gray").grid(row=i, column=2, sticky="w", padx=5)

        # Campos de derechos
        rights_frame = tk.LabelFrame(scroll_frame, text="Derechos y Licencia", font=self.font_large)
        rights_frame.pack(fill="x", padx=10, pady=10)

        rights_fields = [
            ("rights", "Licencia:", "Ej: CC-BY-4.0"),
            ("rightsHolder", "Titular de Derechos:", "Ej: CAICAT Project"),
            ("accessRights", "URL de Derechos:", "Ej: https://creativecommons.org/licenses/by/4.0/"),
        ]
        for i, (key, label, hint) in enumerate(rights_fields):
            tk.Label(rights_frame, text=label, font=self.font_large).grid(row=i, column=0, sticky="e", pady=5, padx=5)
            e = tk.Entry(rights_frame, width=40, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=5)
            e.insert(0, inabio.get(key, ""))
            self.inabio_entries[key] = e
            tk.Label(rights_frame, text=hint, font=("Arial", 9), fg="gray").grid(row=i, column=2, sticky="w", padx=5)

        # Botón de restaurar defaults
        btn_frame = tk.Frame(scroll_frame)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Restaurar valores por defecto",
                  command=self._restore_inabio_defaults, bg="#ff9800", fg="white").pack(side="left", padx=5)

    def _restore_inabio_defaults(self):
        """Restaura los valores por defecto de INABIO."""
        from config_utils import get_default_config
        defaults = get_default_config().get("INABIO", {})
        for key, entry in self.inabio_entries.items():
            entry.delete(0, "end")
            entry.insert(0, defaults.get(key, ""))
        messagebox.showinfo("Restaurado", "Valores por defecto restaurados.\nGuarde los cambios para aplicar.")

    # ------------------------
    # Guardar cambios
    # ------------------------
    def save_all(self):
        try:
            # 1. General
            self.config_data["General"]["output_folder"] = self.output_entry.get()
            self.config_data["General"]["json_file"] = self.json_entry.get()

            # 2. Labels Main
            for key, entry in self.main_entries.items():
                self.config_data["Labels"][key] = entry.get()

            # 3. GUI Inicial
            gui_ini = self.config_data["GUI_Inicial"]
            gui_ini["title"] = self.gui_ini_title.get()
            gui_ini["geometry"] = self.gui_ini_geom.get()
            gui_ini_labels = {}
            for line in self.gui_ini_labels.get("1.0", "end").splitlines():
                if "," in line:
                    k, v = line.split(",", 1)
                    gui_ini_labels[k.strip()] = v.strip()
            gui_ini["labels"] = gui_ini_labels
            gui_ini_buttons = {}
            for line in self.gui_ini_buttons.get("1.0", "end").splitlines():
                if "," in line:
                    k, v = line.split(",", 1)
                    gui_ini_buttons[k.strip()] = v.strip()
            gui_ini["buttons"] = gui_ini_buttons

            # 4. GUI Tagger
            gui_tag = self.config_data.get("GUI_Tagger", {})
            gui_tag["title"] = self.gui_tag_title.get()
            gui_tag["geometry"] = self.gui_tag_geom.get()
            gui_tag["species_tags"] = [x.strip() for x in self.species_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["secondary_tags"] = [x.strip() for x in self.secondary_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["behavior_tags"] = [x.strip() for x in self.behavior_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["other_tags_list"] = [x.strip() for x in self.other_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["country_id"] = self.current_country_id
            self.config_data["GUI_Tagger"] = gui_tag

            # 5. Metadata Settings (incluye ExcelFieldsDefault)
            meta = self.config_data.get("MetadataSettings", {})
            meta["fields_to_embed"] = [x.strip() for x in self.fields_embed_text.get("1.0", "end").split(",") if x.strip()]
            meta["ExcelFieldsDefault"] = [x.strip() for x in self.excel_fields_text.get("1.0", "end").split(",") if x.strip()]
            self.config_data["MetadataSettings"] = meta

            # 6. Processing
            proc = self.config_data.get("Processing", {})
            for k, entry in self.proc_entries.items():
                try:
                    val = int(entry.get())
                except ValueError:
                    try:
                        val = float(entry.get())
                    except ValueError:
                        val = entry.get()
                proc[k] = val
            self.config_data["Processing"] = proc

            # 7.  INABIO
            inabio_data = {}
            for key, entry in self.inabio_entries.items():
                inabio_data[key] = entry.get().strip()
            self.config_data["INABIO"] = inabio_data

            # Guardar archivo
            save_config(self.config_data)
            messagebox.showinfo("Guardado", "Configuración guardada correctamente.\nSe aplicará al reiniciar la aplicación.")
            self.destroy()
            from main import MainApp
            MainApp().mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la configuración:\n{e}")


if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()