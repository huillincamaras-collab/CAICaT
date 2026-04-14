import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
import csv
from config_utils import (
    load_config, save_config,
    search_taxa_local, search_taxa_gbif,
    get_tagger_configs_dir, get_species_csv_path
)
from procesamiento import FPS_EXTRACT, BUFFER_N, TOP_K, DOWNSAMPLE_MAX, JPEG_QUALITY, MASK_QUALITY
from main import MainApp

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

        # Notebook principal
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self.tabs = {}
        self.create_general_tab()
        self.create_gui_tagger_tab()
        self.create_main_tab()
        self.create_gui_inicial_tab()

        # Botones de acción global
        action_frame = tk.Frame(self)
        action_frame.pack(pady=10)
        tk.Button(action_frame, text="Guardar y Salir", font=self.font_large, 
                  command=self.save_all, bg="#4CAF50", fg="white").pack(side="left", padx=15)
        tk.Button(action_frame, text="Cancelar", font=self.font_large, command=self.destroy).pack(side="left", padx=15)

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

        # --- Campos básicos ---
        tk.Label(scroll_frame, text="Título de la Ventana:", font=self.font_large).grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.gui_tag_title = tk.Entry(scroll_frame, width=40, font=self.font_large)
        self.gui_tag_title.grid(row=0, column=1, padx=5, pady=5)
        self.gui_tag_title.insert(0, gui_tag.get("title", ""))

        tk.Label(scroll_frame, text="Geometría (AnchoxAlto):", font=self.font_large).grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.gui_tag_geom = tk.Entry(scroll_frame, width=40, font=self.font_large)
        self.gui_tag_geom.grid(row=1, column=1, padx=5, pady=5)
        self.gui_tag_geom.insert(0, gui_tag.get("geometry", ""))

        tk.Label(scroll_frame, text="Tags de Especies (principal):", font=self.font_large).grid(row=2, column=0, sticky="ne", padx=5, pady=5)
        self.species_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.species_tags_text.grid(row=2, column=1, padx=5, pady=5)
        self.species_tags_text.insert("1.0", ", ".join(gui_tag.get("species_tags", [])))

        tk.Label(scroll_frame, text="Tags Secundarios:", font=self.font_large).grid(row=3, column=0, sticky="ne", padx=5, pady=5)
        self.secondary_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.secondary_tags_text.grid(row=3, column=1, padx=5, pady=5)
        self.secondary_tags_text.insert("1.0", ", ".join(gui_tag.get("secondary_tags", [])))

        tk.Label(scroll_frame, text="Tags de Comportamiento:", font=self.font_large).grid(row=4, column=0, sticky="ne", padx=5, pady=5)
        self.behavior_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.behavior_tags_text.grid(row=4, column=1, padx=5, pady=5)
        self.behavior_tags_text.insert("1.0", ", ".join(gui_tag.get("behavior_tags", [])))

        tk.Label(scroll_frame, text="Lista 'Otros' (Desplegable):", font=self.font_large).grid(row=5, column=0, sticky="ne", padx=5, pady=5)
        self.other_tags_text = tk.Text(scroll_frame, width=40, height=3, font=self.font_large)
        self.other_tags_text.grid(row=5, column=1, padx=5, pady=5)
        self.other_tags_text.insert("1.0", ", ".join(gui_tag.get("other_tags_list", [])))

        # --- Separador ---
        ttk.Separator(scroll_frame, orient="horizontal").grid(row=6, column=0, columnspan=3, sticky="ew", pady=15)

        # --- Buscador de taxones integrado ---
        taxon_lbl = tk.Label(scroll_frame, text="Gestión de Taxones (species_list.csv)", font=("Arial", 12, "bold"))
        taxon_lbl.grid(row=7, column=0, columnspan=3, sticky="w", padx=5, pady=(0, 5))

        self._build_taxon_searcher(scroll_frame, start_row=8)

    def _build_taxon_searcher(self, parent, start_row):
        """Buscador de taxones embebido en el tab GUI Tagger del Setup."""
        search_frame = tk.LabelFrame(parent, text="Buscar y Agregar al CSV Local", font=("Arial", 11))
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
        tk.Button(btn_row, text="Buscar Local", command=self._do_search_local, bg="#e0e0e0").pack(side="left", padx=3)
        tk.Button(btn_row, text="Buscar GBIF (Online)", command=self._do_search_gbif, bg="#bbdefb").pack(side="left", padx=3)
        search_entry.bind("<Return>", lambda e: self._do_search_local())

        # Asignar al CSV
        assign_frame = tk.Frame(search_frame)
        assign_frame.pack(fill="x", padx=5, pady=3)
        tk.Label(assign_frame, text="Acción:", font=("Arial", 10)).pack(side="left")
        tk.Button(assign_frame, text="Agregar Seleccionado al CSV",
                  bg="#4CAF50", fg="white",
                  command=self._add_selected_taxon_to_csv).pack(side="left", padx=5)

    def _do_search_local(self):
        q = self._taxon_search_var.get().strip()
        if not q: return
        results = search_taxa_local(q)
        self._taxon_search_results = results
        self._taxon_results_listbox.delete(0, "end")
        for r in results:
            label = f"{r.get('vernacularName','')} | {r.get('scientificName','')} | ID:{r.get('taxonID','')}"
            self._taxon_results_listbox.insert("end", label)
        self._taxon_status_var.set(f"{len(results)} resultado(s) encontrados localmente.")

    def _do_search_gbif(self):
        q = self._taxon_search_var.get().strip()
        if not q: return
        self._taxon_status_var.set("Buscando en GBIF (puede tardar unos segundos)...")
        self.update_idletasks()

        def _bg():
            try:
                results = search_taxa_gbif(q)
                self.after(0, lambda: self._show_gbif_results(results))
            except Exception as e:
                self.after(0, lambda: self._taxon_status_var.set(f"Error en GBIF: {e}"))

        threading.Thread(target=_bg, daemon=True).start()

    def _show_gbif_results(self, results):
        self._taxon_search_results = results
        self._taxon_results_listbox.delete(0, "end")
        for r in results:
            label = f"{r.get('vernacularName','')} | {r.get('scientificName','')} | ID:{r.get('taxonID','')}"
            self._taxon_results_listbox.insert("end", label)
        self._taxon_status_var.set(f"{len(results)} resultado(s) de GBIF.")

    def _add_selected_taxon_to_csv(self):
        sel = self._taxon_results_listbox.curselection()
        if not sel:
            messagebox.showwarning("Atención", "Seleccione un resultado de la lista primero.")
            return
        
        result = self._taxon_search_results[sel[0]]
        csv_path = get_species_csv_path()
        os.makedirs(os.path.dirname(csv_path), exist_ok=True) 

        # Verificar duplicado por taxonID
        try:
            if os.path.exists(csv_path):
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("taxonID", "").strip() == str(result.get("taxonID", "")).strip():
                            messagebox.showwarning("Atención", f"El taxonID {result['taxonID']} ya existe en el CSV.")
                            return
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el CSV:\n{e}")
            return

        try:
            file_exists = os.path.isfile(csv_path)
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                fieldnames = ["taxonID", "scientificName", "vernacularName", "taxonRank", "kingdom", "family"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "taxonID": result.get("taxonID", ""),
                    "scientificName": result.get("scientificName", ""),
                    "vernacularName": result.get("vernacularName", ""),
                    "taxonRank": result.get("taxonRank", ""),
                    "kingdom": result.get("kingdom", ""),
                    "family": result.get("family", "")
                })
            messagebox.showinfo("Éxito", f"'{result.get('scientificName','')}' agregado correctamente al CSV.")
            self._taxon_search_var.set("") # Limpiar búsqueda
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo escribir en el CSV:\n{e}")

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
            
            # Parsear labels y buttons de GUI Inicial
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

            # 4. GUI Tagger (Preservando claves internas como taxon_map y last_configs)
            gui_tag = self.config_data.get("GUI_Tagger", {})
            gui_tag["title"] = self.gui_tag_title.get()
            gui_tag["geometry"] = self.gui_tag_geom.get()
            
            # Parsear listas de tags
            gui_tag["species_tags"] = [x.strip() for x in self.species_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["secondary_tags"] = [x.strip() for x in self.secondary_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["behavior_tags"] = [x.strip() for x in self.behavior_tags_text.get("1.0", "end").split(",") if x.strip()]
            gui_tag["other_tags_list"] = [x.strip() for x in self.other_tags_text.get("1.0", "end").split(",") if x.strip()]
            
            self.config_data["GUI_Tagger"] = gui_tag

            # 5. Metadata Settings
            meta = self.config_data.get("MetadataSettings", {})
            meta["fields_to_embed"] = [x.strip() for x in self.fields_embed_text.get("1.0", "end").split(",") if x.strip()]
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

            # Guardar archivo
            save_config(self.config_data)
            messagebox.showinfo("Guardado", "Configuración guardada correctamente.\nSe aplicará al reiniciar la aplicación.")
            self.destroy()
            # Volver al menú principal
            MainApp().mainloop()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la configuración:\n{e}")

if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()