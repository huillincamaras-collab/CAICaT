import tkinter as tk
from tkinter import ttk, messagebox
from config_utils import load_config, save_config
from procesamiento import FPS_EXTRACT, BUFFER_N, TOP_K, DOWNSAMPLE_MAX, JPEG_QUALITY, MASK_QUALITY

# Para abrir MainApp al guardar
from main import MainApp

class SetupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Caicat2.0 - Configuración")
        self.geometry("900x700")
        self.font_large = ("Arial", 12)
        self.config_data = load_config()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Crear tabs
        self.tabs = {}
        self.create_gui_tagger_tab()
        self.create_general_tab()
        self.create_main_tab()
        self.create_gui_inicial_tab()

        # Botones de acción
        action_frame = tk.Frame(self)
        action_frame.pack(pady=10)
        tk.Button(action_frame, text="Guardar cambios", font=self.font_large, command=self.save_all).pack(side="left", padx=10)
        tk.Button(action_frame, text="Reset a original", font=self.font_large, command=self.reset_all).pack(side="left", padx=10)

    # ------------------------
    # Tab General (Fusiona General, Procesamiento, Metadata)
    # ------------------------
    def create_general_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="General")
        self.tabs['General'] = tab

        gen = self.config_data.get("General", {})
        meta = self.config_data.get("MetadataSettings", {})

        # --- General Paths ---
        general_frame = tk.LabelFrame(tab, text="General Paths", font=self.font_large)
        general_frame.pack(fill="x", padx=5, pady=5)

        tk.Label(general_frame, text="Output Folder:", font=self.font_large).grid(row=0, column=0, sticky="e")
        self.output_entry = tk.Entry(general_frame, width=60, font=self.font_large)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5)
        self.output_entry.insert(0, gen.get("output_folder",""))

        tk.Label(general_frame, text="JSON File:", font=self.font_large).grid(row=1, column=0, sticky="e")
        self.json_entry = tk.Entry(general_frame, width=60, font=self.font_large)
        self.json_entry.grid(row=1, column=1, padx=5, pady=5)
        self.json_entry.insert(0, gen.get("json_file",""))

        # --- Procesamiento ---
        proc_frame = tk.LabelFrame(tab, text="Procesamiento", font=self.font_large)
        proc_frame.pack(fill="x", padx=5, pady=5)

        vars_proc = {
            "FPS_EXTRACT": FPS_EXTRACT,
            "BUFFER_N": BUFFER_N,
            "TOP_K": TOP_K,
            "DOWNSAMPLE_MAX": DOWNSAMPLE_MAX,
            "JPEG_QUALITY": JPEG_QUALITY,
            "MASK_QUALITY": MASK_QUALITY
        }

        self.proc_entries = {}
        for i,(k,v) in enumerate(vars_proc.items()):
            tk.Label(proc_frame, text=k+":", font=self.font_large).grid(row=i, column=0, sticky="e")
            e = tk.Entry(proc_frame, width=10, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=2)
            e.insert(0,str(v))
            self.proc_entries[k] = e

        # --- Metadata ---
        meta_frame = tk.LabelFrame(tab, text="Metadata", font=self.font_large)
        meta_frame.pack(fill="x", padx=5, pady=5)

        tk.Label(meta_frame, text="Fields to Embed (comma separated):", font=self.font_large).grid(row=0,column=0, sticky="ne")
        self.fields_embed_text = tk.Text(meta_frame, width=60, height=4, font=self.font_large)
        self.fields_embed_text.grid(row=0,column=1, padx=5,pady=2)
        self.fields_embed_text.insert("1.0", ",".join(meta.get("fields_to_embed",[])))

        tk.Label(meta_frame, text="Excel Default Fields (comma separated):", font=self.font_large).grid(row=1,column=0, sticky="ne")
        self.excel_fields_text = tk.Text(meta_frame, width=60, height=4, font=self.font_large)
        self.excel_fields_text.grid(row=1,column=1, padx=5,pady=2)
        self.excel_fields_text.insert("1.0", ",".join(meta.get("ExcelFieldsDefault",[])))

    # ------------------------
    # Tab GUI Tagger (primero)
    # ------------------------
    def create_gui_tagger_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="GUI Tagger")
        self.tabs['GUI_Tagger'] = tab

        gui_tag = self.config_data.get("GUI_Tagger", {})

        tk.Label(tab, text="Title:", font=self.font_large).grid(row=0, column=0, sticky="e")
        self.gui_tag_title = tk.Entry(tab, width=40, font=self.font_large)
        self.gui_tag_title.grid(row=0, column=1, padx=5, pady=2)
        self.gui_tag_title.insert(0, gui_tag.get("title",""))

        tk.Label(tab, text="Geometry:", font=self.font_large).grid(row=1, column=0, sticky="e")
        self.gui_tag_geom = tk.Entry(tab, width=40, font=self.font_large)
        self.gui_tag_geom.grid(row=1, column=1, padx=5, pady=2)
        self.gui_tag_geom.insert(0, gui_tag.get("geometry",""))

        tk.Label(tab, text="Species Tags (comma separated):", font=self.font_large).grid(row=2, column=0, sticky="ne")
        self.species_tags_text = tk.Text(tab, width=40, height=4, font=self.font_large)
        self.species_tags_text.grid(row=2, column=1, padx=5, pady=2)
        self.species_tags_text.insert("1.0", ",".join(gui_tag.get("species_tags",[])))

        tk.Label(tab, text="Secondary Tags (comma separated):", font=self.font_large).grid(row=3, column=0, sticky="ne")
        self.secondary_tags_text = tk.Text(tab, width=40, height=4, font=self.font_large)
        self.secondary_tags_text.grid(row=3, column=1, padx=5, pady=2)
        self.secondary_tags_text.insert("1.0", ",".join(gui_tag.get("secondary_tags",[])))

        tk.Label(tab, text="Behavior Tags (comma separated):", font=self.font_large).grid(row=4, column=0, sticky="ne")
        self.behavior_tags_text = tk.Text(tab, width=40, height=4, font=self.font_large)
        self.behavior_tags_text.grid(row=4, column=1, padx=5, pady=2)
        self.behavior_tags_text.insert("1.0", ",".join(gui_tag.get("behavior_tags",[])))

        # Checkbox para Modo Camtrap DB
        self.camtrap_mode_var = tk.BooleanVar(value=gui_tag.get("camtrap_mode", False)) # Leer estado actual
        self.camtrap_mode_checkbox = tk.Checkbutton(tab, text="Modo Camtrap DB", variable=self.camtrap_mode_var,
                                                   font=self.font_large, command=self._toggle_camtrap_mode_fields)
        self.camtrap_mode_checkbox.grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        # Frame para campos de edición de CSV (oculto por defecto)
        self.csv_edit_frame = tk.Frame(tab)
        self.csv_edit_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        self.csv_edit_frame.grid_remove() # Ocultar inicialmente

        # Campos para agregar especie
        tk.Label(self.csv_edit_frame, text="Agregar Especie (CSV):", font=self.font_large).grid(row=0, column=0, sticky="e")
        self.add_species_entry = tk.Entry(self.csv_edit_frame, width=60, font=self.font_large)
        self.add_species_entry.grid(row=0, column=1, padx=5, pady=2)
        tk.Button(self.csv_edit_frame, text="Agregar a species_list.csv", command=self._add_species_to_csv,
                  font=self.font_large).grid(row=0, column=2, padx=5, pady=2)

        # Campos para agregar sitio
        tk.Label(self.csv_edit_frame, text="Agregar Sitio (CSV):", font=self.font_large).grid(row=1, column=0, sticky="e")
        self.add_site_entry = tk.Entry(self.csv_edit_frame, width=60, font=self.font_large)
        self.add_site_entry.grid(row=1, column=1, padx=5, pady=2)
        tk.Button(self.csv_edit_frame, text="Agregar a sites_list.csv", command=self._add_site_to_csv,
                  font=self.font_large).grid(row=1, column=2, padx=5, pady=2)

        # Inicializar visibilidad
        if self.camtrap_mode_var.get():
            self.csv_edit_frame.grid()
     

    # ------------------------
    # Tab Main Buttons
    # ------------------------
    def create_main_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Main Buttons")
        self.tabs['Main'] = tab

        labels = self.config_data.get("Labels", {})
        self.main_entries = {}
        for i, (key, val) in enumerate(labels.items()):
            tk.Label(tab, text=f"{key}:", font=self.font_large).grid(row=i, column=0, sticky="e")
            e = tk.Entry(tab, width=40, font=self.font_large)
            e.grid(row=i, column=1, padx=5, pady=2)
            e.insert(0, val)
            self.main_entries[key] = e

    # ------------------------
    # Tab GUI Inicial
    # ------------------------
    def create_gui_inicial_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="GUI Inicial")
        self.tabs['GUI_Inicial'] = tab

        gui_ini = self.config_data.get("GUI_Inicial", {})
        tk.Label(tab, text="Title:", font=self.font_large).grid(row=0, column=0, sticky="e")
        self.gui_ini_title = tk.Entry(tab, width=40, font=self.font_large)
        self.gui_ini_title.grid(row=0, column=1, padx=5, pady=2)
        self.gui_ini_title.insert(0, gui_ini.get("title",""))

        tk.Label(tab, text="Geometry:", font=self.font_large).grid(row=1, column=0, sticky="e")
        self.gui_ini_geom = tk.Entry(tab, width=40, font=self.font_large)
        self.gui_ini_geom.grid(row=1, column=1, padx=5, pady=2)
        self.gui_ini_geom.insert(0, gui_ini.get("geometry",""))

        tk.Label(tab, text="Labels (comma separated):", font=self.font_large).grid(row=2, column=0, sticky="ne")
        self.gui_ini_labels = tk.Text(tab, width=40, height=6, font=self.font_large)
        self.gui_ini_labels.grid(row=2, column=1, padx=5, pady=2)
        labels_text = "\n".join([f"{k},{v}" for k,v in gui_ini.get("labels",{}).items()])
        self.gui_ini_labels.insert("1.0", labels_text)

        tk.Label(tab, text="Buttons (comma separated):", font=self.font_large).grid(row=3, column=0, sticky="ne")
        self.gui_ini_buttons = tk.Text(tab, width=40, height=4, font=self.font_large)
        self.gui_ini_buttons.grid(row=3, column=1, padx=5, pady=2)
        buttons_text = "\n".join([f"{k},{v}" for k,v in gui_ini.get("buttons",{}).items()])
        self.gui_ini_buttons.insert("1.0", buttons_text)

    # ------------------------
    # Guardar cambios
    # ------------------------
    def save_all(self):
        try:
            # General
            self.config_data["General"]["output_folder"] = self.output_entry.get()
            self.config_data["General"]["json_file"] = self.json_entry.get()

            # Main buttons
            for key, entry in self.main_entries.items():
                self.config_data["Labels"][key] = entry.get()

            # GUI Inicial
            gui_ini = self.config_data["GUI_Inicial"]
            gui_ini["title"] = self.gui_ini_title.get()
            gui_ini["geometry"] = self.gui_ini_geom.get()
            gui_ini_labels = {}
            for line in self.gui_ini_labels.get("1.0","end").splitlines():
                if "," in line:
                    k,v = line.split(",",1)
                    gui_ini_labels[k.strip()] = v.strip()
            gui_ini["labels"] = gui_ini_labels
            gui_ini_buttons = {}
            for line in self.gui_ini_buttons.get("1.0","end").splitlines():
                if "," in line:
                    k,v = line.split(",",1)
                    gui_ini_buttons[k.strip()] = v.strip()
            gui_ini["buttons"] = gui_ini_buttons

            # GUI Tagger
            gui_tag = self.config_data["GUI_Tagger"]
            gui_tag["title"] = self.gui_tag_title.get()
            gui_tag["geometry"] = self.gui_tag_geom.get()
            # --- MODIFICAR ESTA PARTE ---
            # Leer tags de los campos de texto
            species_tags = [x.strip() for x in self.species_tags_text.get("1.0","end").split(",") if x.strip()]
            secondary_tags = [x.strip() for x in self.secondary_tags_text.get("1.0","end").split(",") if x.strip()]
            behavior_tags = [x.strip() for x in self.behavior_tags_text.get("1.0","end").split(",") if x.strip()]

            # Validar si está en modo Camtrap DB
            if self.camtrap_mode_var.get():
                # Cargar especies válidas desde el CSV
                import os
                import csv
                species_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "species_list.csv")
                valid_species = set()
                try:
                    with open(species_csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            valid_species.add(row.get('scientificName', '').strip())
                            valid_species.add(row.get('vernacularName', '').strip())
                except FileNotFoundError:
                    messagebox.showerror("Error", f"Archivo no encontrado: {species_csv_path}")
                    return # No guardar si no se puede validar
                except Exception as e:
                    messagebox.showerror("Error", f"Error leyendo {species_csv_path}: {e}")
                    return

                # Validar cada tag contra el conjunto de especies válidas
                invalid_species = []
                for tag in species_tags:
                    if tag not in valid_species:
                        invalid_species.append(tag)

                if invalid_species:
                    messagebox.showerror("Error", f"Los siguientes tags no están en species_list.csv: {', '.join(invalid_species)}")
                    return # No guardar si hay tags inválidos

                # Si la validación pasa, guardar y activar el flag
                gui_tag["species_tags"] = species_tags
                gui_tag["secondary_tags"] = secondary_tags
                gui_tag["behavior_tags"] = behavior_tags
                gui_tag["camtrap_mode"] = True

            else: # Modo estándar
                # Guardar tags como siempre y desactivar el flag
                gui_tag["species_tags"] = species_tags
                gui_tag["secondary_tags"] = secondary_tags
                gui_tag["behavior_tags"] = behavior_tags
                gui_tag["camtrap_mode"] = False

            # --- FIN MODIFICACIÓN ---

            # Metadata
            meta = self.config_data.get("MetadataSettings",{})
            meta["fields_to_embed"] = [x.strip() for x in self.fields_embed_text.get("1.0","end").split(",") if x.strip()]
            meta["ExcelFieldsDefault"] = [x.strip() for x in self.excel_fields_text.get("1.0","end").split(",") if x.strip()]

            # Procesamiento
            for k, entry in self.proc_entries.items():
                try:
                    val = int(entry.get())
                except ValueError:
                    val = entry.get()
                globals()[k] = val

            save_config(self.config_data)
            messagebox.showinfo("Info", "Configuración guardada correctamente.")

            # Abrir MainApp
            self.destroy()
            MainApp().mainloop()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la configuración: {e}")
    # ------------------------
    # Reset global
    # ------------------------
    def reset_all(self):
        try:
            self.config_data = load_config()  # recarga desde disco (original)
            self.destroy()
            SetupApp().mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo resetear:\n{e}")

    # ------------------------
    # Funciones auxiliares para Modo Camtrap DB
    # ------------------------
    def _toggle_camtrap_mode_fields(self):
        """Muestra u oculta los campos de edición de CSV según el estado del checkbox."""
        if self.camtrap_mode_var.get():
            self.csv_edit_frame.grid()
        else:
            self.csv_edit_frame.grid_remove()

    def _add_species_to_csv(self):
        """Agrega una nueva especie al archivo species_list.csv."""
        import os
        import csv
        species_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "species_list.csv")
        csv_dir = os.path.dirname(species_csv_path)
        os.makedirs(csv_dir, exist_ok=True) # Crear carpeta si no existe

        entry_text = self.add_species_entry.get().strip()
        if not entry_text:
            messagebox.showwarning("Advertencia", "Ingrese datos para agregar.")
            return

        # Asumimos que el formato es: scientificName,vernacularName,taxonID (puede estar vacío)
        parts = entry_text.split(',')
        if len(parts) < 2:
             messagebox.showerror("Error", "Formato inválido. Use: scientificName,vernacularName[,taxonID]")
             return

        new_row = {
            'scientificName': parts[0].strip(),
            'vernacularName': parts[1].strip(),
            'taxonID': parts[2].strip() if len(parts) > 2 else ''
        }

        # Verificar si ya existe
        exists = False
        try:
            with open(species_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row.get('scientificName', '').strip() == new_row['scientificName'] or
                        row.get('vernacularName', '').strip() == new_row['vernacularName']):
                        exists = True
                        break
        except FileNotFoundError:
            # Archivo no existe, se creará
            pass
        except Exception as e:
            messagebox.showerror("Error", f"Error leyendo {species_csv_path}: {e}")
            return

        if exists:
            messagebox.showwarning("Advertencia", f"La especie '{new_row['scientificName']}' o '{new_row['vernacularName']}' ya existe en el archivo.")
            return

        # Escribir nueva fila
        try:
            file_exists = os.path.isfile(species_csv_path)
            with open(species_csv_path, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['scientificName', 'vernacularName', 'taxonID']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(new_row)
            messagebox.showinfo("Info", f"Especie '{new_row['scientificName']}' agregada a {species_csv_path}")
            self.add_species_entry.delete(0, tk.END) # Limpiar campo
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo escribir en {species_csv_path}: {e}")

    def _add_site_to_csv(self):
        """Agrega un nuevo sitio al archivo sites_list.csv."""
        import os
        import csv
        sites_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "sites_list.csv")
        csv_dir = os.path.dirname(sites_csv_path)
        os.makedirs(csv_dir, exist_ok=True) # Crear carpeta si no existe

        entry_text = self.add_site_entry.get().strip()
        if not entry_text:
            messagebox.showwarning("Advertencia", "Ingrese datos para agregar.")
            return

        # Asumimos que el formato es: siteID,latitude,longitude
        parts = entry_text.split(',')
        if len(parts) < 3:
             messagebox.showerror("Error", "Formato inválido. Use: siteID,latitude,longitude")
             return

        new_row = {
            'siteID': parts[0].strip(),
            'decimalLatitude': parts[1].strip(),
            'decimalLongitude': parts[2].strip()
        }

        # Verificar si ya existe
        try:
            with open(sites_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('siteID', '').strip() == new_row['siteID']:
                        exists = True
                        break
        except FileNotFoundError:
            # Archivo no existe, se creará
            pass
        except Exception as e:
            messagebox.showerror("Error", f"Error leyendo {sites_csv_path}: {e}")
            return

        if exists:
            messagebox.showwarning("Advertencia", f"El sitio '{new_row['siteID']}' ya existe en el archivo.")
            return

        # Escribir nueva fila
        try:
            file_exists = os.path.isfile(sites_csv_path)
            with open(sites_csv_path, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['siteID', 'decimalLatitude', 'decimalLongitude']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(new_row)
            messagebox.showinfo("Info", f"Sitio '{new_row['siteID']}' agregado a {sites_csv_path}")
            self.add_site_entry.delete(0, tk.END) # Limpiar campo
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo escribir en {sites_csv_path}: {e}")




if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()
