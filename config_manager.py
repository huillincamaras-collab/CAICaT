"""
config_manager.py - Panel Unificado: Selector + Editor/Creación (Versión Centralizada)
Rutas estrictas: config/paises/ → config/regions/ → config/tagger_configs/
TaxonIDs centralizados en species_master_{country}.json + taxon_master_global.json
Soporta múltiples sistemas: GBIF + iNaturalist/INABIO
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import os
import json
from datetime import datetime
import requests
import time
import threading
from config_utils import (
    resolve_taxon_id,
    resolve_all_taxon_ids,
    resolve_human_activity,
    load_country_species,
    load_global_master,
    add_species_to_master
)


# ================= CLASE 1: SELECTOR JERÁRQUICO =================
class ConfigManager(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("⚙️ Seleccionar Configuración")
        self.geometry("980x720")  # 🔒 FIX: Más ancho para 5 columnas
        self.resizable(False, True)
        self.configure(bg="#f4f4f4")
        
        # FIX LINUX/UBUNTU
        self.update_idletasks()
        self.wait_visibility()
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        
        # RUTAS EXACTAS Y ESTRICTAS
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.paises_dir = os.path.join(self.base_dir, "config", "paises")
        self.regions_dir = os.path.join(self.base_dir, "config", "regions")
        self.configs_dir = os.path.join(self.base_dir, "config", "tagger_configs")
        self.countries, self.regions, self.configs = [], [], []
        self.current_country_id = self.current_region_id = self.current_config_path = None
        self.current_config_data = None
        self._build_ui()
        self._load_countries()
    
    def _build_ui(self):
        """Construye la interfaz del panel de configuración con CINCO columnas de texto."""
        # SELECTORES JERÁRQUICOS (País, Región, Config)
        for label, var_name, cmd in [
            ("País:", "country_var", self._on_country_change),
            ("Región:", "region_var", self._on_region_change),
            ("Config:", "config_var", self._on_config_change)
        ]:
            f = tk.Frame(self, bg="#f4f4f4")
            f.pack(fill="x", padx=15, pady=6)
            tk.Label(f, text=label, width=8, bg="#f4f4f4", font=("Arial", 9, "bold")).pack(side="left")
            var = tk.StringVar()
            combo = ttk.Combobox(f, textvariable=var, state="readonly", font=("Arial", 9))
            combo.pack(side="left", fill="x", expand=True)
            combo.bind("<<ComboboxSelected>>", cmd)
            setattr(self, var_name, var)
            setattr(self, f"{var_name}_combo", combo)
        
        # 🔒 FIX: CINCO COLUMNAS DE TEXTO (antes 4)
        tk.Label(self, text="📋 Tags de la configuración seleccionada:",
                 font=("Arial", 9, "bold"), bg="#f4f4f4").pack(anchor="w", padx=15, pady=(10, 2))
        
        # Contenedor para las cinco columnas
        columns_container = tk.Frame(self, bg="#f4f4f4")
        columns_container.pack(fill="both", expand=True, padx=15, pady=5)
        
        # 🔒 FIX: Configurar grid para 5 columnas iguales
        for i in range(5):
            columns_container.columnconfigure(i, weight=1, uniform="column")
        columns_container.rowconfigure(0, weight=1)
        
        # COLUMNA 1: ESPECIES PRINCIPALES
        col1_frame = tk.LabelFrame(columns_container, text="🦌 Especies Principales",
                                   font=("Arial", 9, "bold"), bg="#e8f5e9", bd=2)
        col1_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.species_text = tk.Text(col1_frame, wrap="word", font=("Arial", 9),
                                    bg="#e8f5e9", relief="flat", height=10)
        self.species_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.species_text.config(state="disabled")
        
        # COLUMNA 2: TAGS SECUNDARIOS
        col2_frame = tk.LabelFrame(columns_container, text="🔍 Tags Secundarios",
                                   font=("Arial", 9, "bold"), bg="#fff3e0", bd=2)
        col2_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.secondary_text = tk.Text(col2_frame, wrap="word", font=("Arial", 9),
                                      bg="#fff3e0", relief="flat", height=10)
        self.secondary_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.secondary_text.config(state="disabled")
        
        # COLUMNA 3: COMPORTAMIENTOS
        col3_frame = tk.LabelFrame(columns_container, text="🎭 Comportamientos",
                                   font=("Arial", 9, "bold"), bg="#e3f2fd", bd=2)
        col3_frame.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        self.behavior_text = tk.Text(col3_frame, wrap="word", font=("Arial", 9),
                                     bg="#e3f2fd", relief="flat", height=10)
        self.behavior_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.behavior_text.config(state="disabled")
        
        # COLUMNA 4: OTROS (other_tags_list)
        col4_frame = tk.LabelFrame(columns_container, text="🐾 Otros (desplegable)",
                                   font=("Arial", 9, "bold"), bg="#f3e5f5", bd=2)
        col4_frame.grid(row=0, column=3, sticky="nsew", padx=2, pady=2)
        self.others_text = tk.Text(col4_frame, wrap="word", font=("Arial", 9),
                                   bg="#f3e5f5", relief="flat", height=10)
        self.others_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.others_text.config(state="disabled")
        
        # 🔒 NUEVO: COLUMNA 5: OPCIONALES (optional_tags)
        col5_frame = tk.LabelFrame(columns_container, text="🏷️ Opcionales (máx 6)",
                                   font=("Arial", 9, "bold"), bg="#fff9c4", bd=2)
        col5_frame.grid(row=0, column=4, sticky="nsew", padx=2, pady=2)
        self.optional_text = tk.Text(col5_frame, wrap="word", font=("Arial", 9),
                                     bg="#fff9c4", relief="flat", height=10)
        self.optional_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.optional_text.config(state="disabled")
        
        # BOTONES DE ACCIÓN
        btn_frame = tk.Frame(self, bg="#f4f4f4")
        btn_frame.pack(fill="x", padx=15, pady=12)
        tk.Button(btn_frame, text="✅ Seleccionar", bg="#4CAF50", fg="white",
                  font=("Arial", 9, "bold"), command=self._apply_config).pack(side="left", fill="x", expand=True, padx=2)
        tk.Button(btn_frame, text="✏️ Editar / ➕ Crear", bg="#2196F3", fg="white",
                  font=("Arial", 9, "bold"), command=self._open_editor).pack(side="left", fill="x", expand=True, padx=2)
        tk.Button(btn_frame, text="❌ Cancelar", bg="#9e9e9e", fg="white",
                  command=self.destroy).pack(side="left", fill="x", expand=True, padx=2)
    
    def _load_countries(self):
        self.countries = []
        if not os.path.exists(self.paises_dir):
            return messagebox.showwarning("Ruta no encontrada", f"No existe: {self.paises_dir}", parent=self)
        for filename in os.listdir(self.paises_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.paises_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("metadata") or data.get("_metadata") or {}
                country_name = meta.get("country_name")
                country_id = meta.get("country_id", filename.replace(".json", ""))
                if country_name:
                    self.countries.append({"id": country_id, "name": country_name})
            except Exception as e:
                print(f"⚠️ Error leyendo {filename}: {e}")
        self.countries.sort(key=lambda x: x["name"])
        self.country_var_combo["values"] = [c["name"] for c in self.countries]
        if self.countries:
            self.country_var_combo.current(0)
            self._on_country_change()
    
    def _on_country_change(self, event=None):
        idx = self.country_var_combo.current()
        if idx < 0:
            return
        self.current_country_id = self.countries[idx]["id"]
        self.regions, self.configs = [], []
        self.config_var_combo.set("")
        self._clear_table()
        if not os.path.exists(self.regions_dir):
            return
        for f in os.listdir(self.regions_dir):
            if not f.endswith(".json"):
                continue
            try:
                path = os.path.join(self.regions_dir, f)
                with open(path, "r", encoding="utf-8") as fp:
                    meta = json.load(fp).get("metadata") or {}
                if meta.get("country_id") == self.current_country_id:
                    rid = meta.get("region_id", f.replace(".json", ""))
                    self.regions.append({"id": rid, "name": meta.get("region_name", rid)})
            except Exception:
                continue
        self.regions.sort(key=lambda x: x["name"])
        self.region_var_combo["values"] = [r["name"] for r in self.regions]
        if self.regions:
            self.region_var_combo.current(0)
            self._on_region_change()
        else:
            self.region_var_combo.set("Sin regiones")
    
    def _on_region_change(self, event=None):
        idx = self.region_var_combo.current()
        if idx < 0:
            return
        self.current_region_id = self.regions[idx]["id"]
        self.configs = []
        self.config_var_combo.set("")
        self._clear_table()
        if not os.path.exists(self.configs_dir):
            return
        for f in os.listdir(self.configs_dir):
            if not f.endswith(".json"):
                continue
            try:
                path = os.path.join(self.configs_dir, f)
                with open(path, "r", encoding="utf-8") as fp:
                    meta = json.load(fp).get("_metadata") or {}
                if meta.get("country_id") == self.current_country_id and meta.get("linked_region_id") == self.current_region_id:
                    self.configs.append({"name": meta.get("name", f.replace(".json", "")), "path": path})
            except Exception:
                continue
        self.configs.sort(key=lambda x: x["name"])
        self.config_var_combo["values"] = [c["name"] for c in self.configs]
        if self.configs:
            self.config_var_combo.current(0)
            self._on_config_change()
        else:
            self.config_var_combo.set("Sin configs")
    
    def _on_config_change(self, event=None):
        idx = self.config_var_combo.current()
        if idx >= 0 and self.configs:
            self.current_config_path = self.configs[idx]["path"]
            try:
                with open(self.current_config_path, "r", encoding="utf-8") as f:
                    self.current_config_data = json.load(f)
                self._update_table(self.current_config_data)
            except Exception:
                pass
    
    def _update_table(self, cfg):
        """Actualiza las CINCO columnas de texto con las etiquetas limpias."""
        gui = cfg.get("GUI_Tagger", {})
        
        # === COLUMNA 1: Especies Principales ===
        species_tags = gui.get("species_tags", [])
        self.species_text.config(state="normal")
        self.species_text.delete("1.0", "end")
        if species_tags:
            self.species_text.insert("1.0", "\n".join(f"• {tag}" for tag in species_tags))
        else:
            self.species_text.insert("1.0", "Sin tags principales")
        self.species_text.config(state="disabled")
        
        # === COLUMNA 2: Tags Secundarios ===
        secondary_tags = gui.get("secondary_tags", [])
        self.secondary_text.config(state="normal")
        self.secondary_text.delete("1.0", "end")
        if secondary_tags:
            self.secondary_text.insert("1.0", "\n".join(f"• {tag}" for tag in secondary_tags))
        else:
            self.secondary_text.insert("1.0", "Sin tags secundarios")
        self.secondary_text.config(state="disabled")
        
        # === COLUMNA 3: Comportamientos ===
        behavior_tags = gui.get("behavior_tags", [])
        self.behavior_text.config(state="normal")
        self.behavior_text.delete("1.0", "end")
        if behavior_tags:
            self.behavior_text.insert("1.0", "\n".join(f"• {tag}" for tag in behavior_tags))
        else:
            self.behavior_text.insert("1.0", "Sin comportamientos")
        self.behavior_text.config(state="disabled")
        
        # === COLUMNA 4: Otros (other_tags_list) ===
        other_tags = gui.get("other_tags_list", [])
        self.others_text.config(state="normal")
        self.others_text.delete("1.0", "end")
        if other_tags:
            self.others_text.insert("1.0", "\n".join(f"• {tag}" for tag in other_tags))
        else:
            self.others_text.insert("1.0", "Sin tags 'Otros'")
        self.others_text.config(state="disabled")
        
        # 🔒 NUEVO: === COLUMNA 5: Opcionales (optional_tags) ===
        optional_tags = gui.get("optional_tags", [])
        self.optional_text.config(state="normal")
        self.optional_text.delete("1.0", "end")
        if optional_tags:
            self.optional_text.insert("1.0", "\n".join(f"• {tag}" for tag in optional_tags))
        else:
            self.optional_text.insert("1.0", "Sin tags opcionales")
        self.optional_text.config(state="disabled")
    
    def _clear_table(self):
        """Limpia las CINCO columnas de texto cuando no hay configuración seleccionada."""
        # 🔒 FIX: Incluye self.optional_text
        for text_widget in [self.species_text, self.secondary_text, self.behavior_text, 
                            self.others_text, self.optional_text]:
            text_widget.config(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", "Seleccione una configuración")
            text_widget.config(state="disabled")
    
    def _apply_config(self):
        if not self.current_config_data:
            return messagebox.showwarning("Atención", "Seleccione una configuración primero.", parent=self)
        try:
            gui = self.current_config_data.get("GUI_Tagger", {})
            self.parent.species_tags = gui.get("species_tags", [])
            self.parent.secondary_tags = gui.get("secondary_tags", [])
            self.parent.behavior_tags = gui.get("behavior_tags", [])
            self.parent.other_tags_list = gui.get("other_tags_list", [])
            # 🔒 NUEVO: Aplicar optional_tags
            self.parent.optional_tags = gui.get("optional_tags", [])
            self.parent.taxon_map = self.current_config_data.get("Taxon_Map", {})
            if hasattr(self.parent, "_rebuild_tag_buttons"):
                self.parent._rebuild_tag_buttons()
            messagebox.showinfo("✅ Éxito", "Configuración aplicada.", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo aplicar:\n{e}", parent=self)
    
    def _open_editor(self):
        if not self.current_country_id or not self.current_region_id:
            return messagebox.showwarning("Atención", "Seleccione País y Región primero.", parent=self)
        ConfigEditor(self, self.current_country_id, self.current_region_id, 
                     self.current_config_path, self.current_config_data)


# ================= CLASE 2: EDITOR / CREADOR =================
class ConfigEditor(tk.Toplevel):
    def __init__(self, parent, country_id, region_id, config_path, config_data=None):
        super().__init__(parent)
        self.parent = parent
        self.country_id = country_id
        self.region_id = region_id
        self.config_path = config_path
        self.config_data = config_data or {}
        self.original_name = self.config_data.get("_metadata", {}).get("name", "") if self.config_data else ""
        self.is_editing = bool(config_data)
        self.region_species = []
        self.country_species = []
        self._search_debounce_id = None
        
        self.title("✏️ Editar Configuración" if self.is_editing else "➕ Nueva Configuración")
        self.geometry("780x600")
        self.transient(parent)
        self.update_idletasks()
        self.wait_visibility()
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        
        self._build_ui()
        self._load_region_species()
        if self.is_editing:
            self._load_config_to_tree()
        else:
            self._load_defaults()
    
    def _build_ui(self):
        top = tk.Frame(self, bg="#f0f0f0")
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Nombre Config:", bg="#f0f0f0").pack(side="left")
        self.name_var = tk.StringVar(value=self.original_name if self.original_name else f"{self.country_id}_{self.region_id}_Nueva")
        tk.Entry(top, textvariable=self.name_var, width=35).pack(side="left", padx=5)
        self.sci_var = tk.BooleanVar(value=self.config_data.get("_metadata", {}).get("is_scientific", False))
        tk.Checkbutton(top, text="🔬 Modo Científico", variable=self.sci_var, bg="#f0f0f0").pack(side="left", padx=10)
        tk.Button(top, text="🆕 Nueva Config", bg="#FF9800", fg="white", command=self._load_defaults).pack(side="right", padx=2)
        tk.Label(self, text="Mapeo de Botones (Doble clic para editar)", font=("Arial", 9, "bold")).pack(anchor="w", padx=15, pady=(5, 0))
        cols = ("tipo", "tag", "spec", "tid")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=16)
        for c, w, t in [("tipo", 100, "Tipo"), ("tag", 130, "Etiqueta"), ("spec", 220, "Especie"), ("tid", 140, "TaxonID (GBIF|iNat)")]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self._on_double_click)
        
        # 🔒 FIX: Botones específicos por tipo (los Principales solo se editan, no se agregan)
        ctrl = tk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=5)
        tk.Button(ctrl, text="+ Secundario", bg="#fff3e0",
                  command=lambda: self._add_row("Secundario", "", "", "")).pack(side="left", padx=2)
        tk.Button(ctrl, text="+ Comportamiento", bg="#e3f2fd",
                  command=lambda: self._add_row("Comportamiento", "", "", "")).pack(side="left", padx=2)
        tk.Button(ctrl, text="+ Otro", bg="#f3e5f5",
                  command=lambda: self._add_row("Otro", "", "", "")).pack(side="left", padx=2)
        tk.Button(ctrl, text="+ Opcional", bg="#fff9c4",
                  command=lambda: self._add_row("Opcional", "", "", "")).pack(side="left", padx=2)
        tk.Button(ctrl, text="🗑️ Quitar", command=self._delete_row).pack(side="left", padx=2)
        
        btn = tk.Frame(self)
        btn.pack(fill="x", padx=10, pady=10)
        tk.Button(btn, text="💾 Guardar", bg="#4CAF50", fg="white", command=self._save_config).pack(side="left", fill="x", expand=True, padx=2)
        tk.Button(btn, text="❌ Cancelar", command=self.destroy).pack(side="left", fill="x", expand=True, padx=2)
    
    def _add_row(self, tipo="Principal", tag="", spec="", tid=""):
        self.tree.insert("", "end", values=(tipo, tag, spec, tid))
    
    def _delete_row(self):
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel)
    
    def _load_region_species(self):
        """Carga species_names de la región y resuelve datos completos desde species_master."""
        self.region_species = []
        if not self.region_id or not os.path.exists(self.parent.regions_dir):
            return
        region_file = None
        for f in os.listdir(self.parent.regions_dir):
            if not f.endswith(".json"):
                continue
            try:
                path = os.path.join(self.parent.regions_dir, f)
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                meta = data.get("metadata") or {}
                if meta.get("region_id") == self.region_id and meta.get("country_id") == self.country_id:
                    region_file = path
                    species_names = data.get("species_names", [])
                    break
            except Exception:
                continue
        if not region_file:
            return
        master_species = load_country_species(self.country_id)
        master_index = {sp.get("scientificName", "").lower().strip(): sp for sp in master_species}
        for sci_name in species_names:
            sci_lower = sci_name.lower().strip()
            if sci_lower in master_index:
                sp_data = master_index[sci_lower].copy()
                sp_data["source"] = "region"
                self.region_species.append(sp_data)
            else:
                self.region_species.append({
                    "scientificName": sci_name,
                    "taxonID_GBIF": "",
                    "taxonID_iNaturalist": "",
                    "commonName": "",
                    "source": "region"
                })
    
    def _load_country_species(self):
        """Carga especies del species_master del país (con ambos IDs)."""
        if self.country_species:
            return self.country_species
        self.country_species = load_country_species(self.country_id)
        for sp in self.country_species:
            sp["source"] = "country"
        return self.country_species
    
    def _load_defaults(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        defaults = [
            ("Principal", "Principal_1"), ("Principal", "Principal_2"),
            ("Secundario", "Otros"), ("Secundario", "Secundario_2"), ("Secundario", "Secundario_3"),
            ("Comportamiento", "Comportamiento_1"), ("Comportamiento", "Comportamiento_2"),
            ("Otro", "Extra_1"), ("Otro", "Extra_2")
            # 🔒 FIX: Sin opcionales por defecto (el usuario agrega los que quiera)
        ]
        for tipo, tag in defaults:
            self._add_row(tipo, tag, "", "")
        if not self.original_name:
            self.name_var.set(f"{self.country_id}_{self.region_id}_Nueva")
    
    def _load_config_to_tree(self):
        """Carga la config al treeview, resolviendo IDs desde master."""
        for i in self.tree.get_children():
            self.tree.delete(i)
        gui = self.config_data.get("GUI_Tagger", {})
        taxon_map = self.config_data.get("Taxon_Map", {})
        resolved_map = resolve_all_taxon_ids(taxon_map, self.country_id) if self.country_id else {}
        
        for t in gui.get("species_tags", []):
            sci = taxon_map.get(t, {}).get("scientificName", "")
            resolved = resolved_map.get(t, {})
            tid_gbif = resolved.get("taxonID_GBIF", "")
            tid_inat = resolved.get("taxonID_iNaturalist", "")
            tid_display = f"{tid_gbif}|{tid_inat}" if tid_gbif or tid_inat else ""
            self._add_row("Principal", t, sci, tid_display)
        
        for t in gui.get("secondary_tags", []):
            sci = taxon_map.get(t, {}).get("scientificName", "")
            resolved = resolved_map.get(t, {})
            tid_gbif = resolved.get("taxonID_GBIF", "")
            tid_inat = resolved.get("taxonID_iNaturalist", "")
            tid_display = f"{tid_gbif}|{tid_inat}" if tid_gbif or tid_inat else ""
            self._add_row("Secundario", t, sci, tid_display)
        
        for t in gui.get("behavior_tags", []):
            self._add_row("Comportamiento", t, "", "")
        
        for t in gui.get("other_tags_list", []):
            sci = taxon_map.get(t, {}).get("scientificName", "")
            resolved = resolved_map.get(t, {})
            tid_gbif = resolved.get("taxonID_GBIF", "")
            tid_inat = resolved.get("taxonID_iNaturalist", "")
            tid_display = f"{tid_gbif}|{tid_inat}" if tid_gbif or tid_inat else ""
            self._add_row("Otro", t, sci, tid_display)
        
        # 🔒 NUEVO: Opcionales (sin IDs, categorías independientes)
        for t in gui.get("optional_tags", []):
            self._add_row("Opcional", t, "", "")
    
    def _on_double_click(self, event):
        sel = self.tree.identify_row(event.y)
        if not sel:
            return
        vals = self.tree.item(sel, "values")
        tipo = vals[0]
        # 🔒 FIX: Los opcionales se editan como etiquetas simples (sin taxonID)
        if tipo in ("Principal", "Secundario", "Otro"):
            self._open_species_editor(sel, vals)
        else:
            self._open_simple_editor(sel, vals)
    
    def _open_species_editor(self, sel, vals):
        """Editor de especies con campos GBIF e iNaturalist (IDs en solo lectura)."""
        win = tk.Toplevel(self)
        win.title("Editar Especie")
        win.geometry("480x650")
        win.transient(self)
        win.update_idletasks()
        win.wait_visibility()
        try:
            win.grab_set()
        except tk.TclError:
            pass
        
        tipo_var = tk.StringVar(value=vals[0])
        tag_var = tk.StringVar(value=vals[1])
        spec_var = tk.StringVar(value=vals[2])
        
        tid_display = vals[3] if len(vals) > 3 else ""
        if "|" in tid_display:
            tid_gbif_str, tid_inat_str = tid_display.split("|", 1)
        else:
            tid_gbif_str = tid_display
            tid_inat_str = ""
        tid_gbif_var = tk.StringVar(value=tid_gbif_str)
        tid_inat_var = tk.StringVar(value=tid_inat_str)
        
        visible_var = tk.BooleanVar(value=not vals[1].startswith("-"))
        if not visible_var.get():
            tag_var.set(vals[1].lstrip("-"))
        
        tk.Label(win, text="🔎 Buscar (≥2 caracteres):", font=("Arial", 9)).pack(pady=(5, 0))
        search_var = tk.StringVar()
        search_entry = tk.Entry(win, textvariable=search_var, width=42)
        search_entry.pack(pady=2)
        search_entry.focus_set()
        lst = tk.Listbox(win, height=8, font=("Courier", 9))
        lst.pack(fill="x", padx=10, pady=2)
        search_var.trace("w", lambda *a: self._on_search_change(
            search_var.get().strip(), lst, spec_var, tag_var, tid_gbif_var, tid_inat_var, win
        ))
        
        fields = [
            ("Tipo:", tipo_var, "readonly"),
            ("Etiqueta:", tag_var, "normal"),
            ("Especie:", spec_var, "normal"),
        ]
        for lbl, var, state in fields:
            row = tk.Frame(win)
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text=lbl, width=10, anchor="e").pack(side="left")
            tk.Entry(row, textvariable=var, width=30, state=state).pack(side="left", padx=2)
        
        tk.Label(win, text="─── Identificadores (auto-resueltos) ───",
                 font=("Arial", 8, "italic"), fg="#666").pack(pady=(8, 2))
        id_fields = [
            ("GBIF ID:", tid_gbif_var),
            ("iNaturalist:", tid_inat_var),
        ]
        for lbl, var in id_fields:
            row = tk.Frame(win)
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text=lbl, width=10, anchor="e", fg="#1565c0").pack(side="left")
            tk.Entry(row, textvariable=var, width=20, state="readonly",
                     readonlybackground="#e3f2fd").pack(side="left", padx=2)
        
        tk.Checkbutton(win, text="👁️ Botón Visible", variable=visible_var,
                       font=("Arial", 9)).pack(anchor="w", padx=10, pady=4)
        
        def save():
            final_tag = tag_var.get().strip()
            if not visible_var.get() and final_tag:
                final_tag = f"-{final_tag}"
            combined_tid = f"{tid_gbif_var.get()}|{tid_inat_var.get()}"
            self.tree.item(sel, values=[tipo_var.get(), final_tag, spec_var.get(), combined_tid])
            win.destroy()
        
        tk.Button(win, text="✅ Guardar", bg="#4CAF50", fg="white", command=save).pack(pady=10)
        lst.bind("<<ListboxSelect>>", lambda e: self._apply_selection(
            lst._cache, lst.curselection(), spec_var, tag_var, tid_gbif_var, tid_inat_var, win
        ))
    
    def _open_simple_editor(self, sel, vals):
        win = tk.Toplevel(self)
        win.title("Editar Etiqueta")
        win.geometry("320x220")
        win.transient(self)
        win.update_idletasks()
        win.wait_visibility()
        try:
            win.grab_set()
        except tk.TclError:
            pass
        
        tipo_var = tk.StringVar(value=vals[0])
        tag_var = tk.StringVar(value=vals[1])
        visible_var = tk.BooleanVar(value=not vals[1].startswith("-"))
        if not visible_var.get():
            tag_var.set(vals[1].lstrip("-"))
        
        tk.Label(win, text="Tipo:", font=("Arial", 9)).pack(anchor="w", padx=10, pady=(10, 2))
        tk.Entry(win, textvariable=tipo_var, state="readonly", width=20).pack(fill="x", padx=10, pady=2)
        tk.Label(win, text="Etiqueta:", font=("Arial", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Entry(win, textvariable=tag_var, width=20).pack(fill="x", padx=10, pady=2)
        tk.Checkbutton(win, text="👁️ Botón Visible", variable=visible_var, font=("Arial", 9)).pack(anchor="w", padx=10, pady=8)
        
        def save():
            final_tag = tag_var.get().strip()
            if not visible_var.get() and final_tag:
                final_tag = f"-{final_tag}"
            self.tree.item(sel, values=[tipo_var.get(), final_tag, "", ""])
            win.destroy()
        
        tk.Button(win, text="✅ Guardar", bg="#4CAF50", fg="white", command=save).pack(pady=10)
    
    def _on_search_change(self, query, lst, spec_var, tag_var, tid_gbif_var, tid_inat_var, win):
        """Búsqueda en cascada: región → país → GBIF → iNaturalist."""
        if self._search_debounce_id:
            self.after_cancel(self._search_debounce_id)
        lst.delete(0, tk.END)
        if len(query) < 2 or not query.strip():
            lst._cache = []
            return
        spec_var.set("")
        tid_gbif_var.set("")
        tid_inat_var.set("")
        tag_var.set("")
        q = query.lower()
        
        def match_strict(text):
            if not text:
                return False
            t = text.lower()
            return t.startswith(q) or any(w.startswith(q) for w in t.split())
        
        local_matches = []
        for sp in self.region_species:
            if (match_strict(sp.get("scientificName", "")) or
                match_strict(sp.get("commonName", sp.get("vernacularName", ""))) or
                str(sp.get("taxonID_GBIF", "")).startswith(q) or
                str(sp.get("taxonID_iNaturalist", "")).startswith(q)):
                sp_copy = sp.copy()
                sp_copy["source"] = "region"
                local_matches.append(sp_copy)
        
        if not local_matches:
            for sp in self._load_country_species():
                if (match_strict(sp.get("scientificName", "")) or
                    match_strict(sp.get("commonName", sp.get("vernacularName", ""))) or
                    str(sp.get("taxonID_GBIF", "")).startswith(q) or
                    str(sp.get("taxonID_iNaturalist", "")).startswith(q)):
                    sp_copy = sp.copy()
                    sp_copy["source"] = "country"
                    local_matches.append(sp_copy)
        
        lst._cache = local_matches
        for sp in local_matches:
            lst.insert(tk.END, self._format_sp_entry(sp))
        
        if not local_matches:
            self._search_debounce_id = self.after(600, lambda: self._search_online_async(q, lst))
    
    def _search_online_async(self, q, lst):
        """Busca en GBIF e iNaturalist en paralelo (thread separado)."""
        def gbif_thread():
            matches = self._search_gbif_online(q)
            for m in matches:
                m["source"] = "gbif"
            self.after(0, lambda: self._merge_online_results(matches, lst, "GBIF"))
        
        def inat_thread():
            matches = self._search_inaturalist_online(q)
            for m in matches:
                m["source"] = "inat"
            self.after(0, lambda: self._merge_online_results(matches, lst, "iNaturalist"))
        
        threading.Thread(target=gbif_thread, daemon=True).start()
        threading.Thread(target=inat_thread, daemon=True).start()
        self._search_debounce_id = None
    
    def _merge_online_results(self, new_matches, lst, source_name):
        """Agrega resultados online al listbox sin duplicar."""
        existing_ids = {s.get("taxonID_GBIF") for s in lst._cache if s.get("taxonID_GBIF")}
        existing_inat = {s.get("taxonID_iNaturalist") for s in lst._cache if s.get("taxonID_iNaturalist")}
        added = 0
        for m in new_matches:
            gbif_id = m.get("taxonID_GBIF", "")
            inat_id = m.get("taxonID_iNaturalist", "")
            if gbif_id and gbif_id in existing_ids:
                continue
            if inat_id and inat_id in existing_inat:
                continue
            lst._cache.append(m)
            lst.insert(tk.END, self._format_sp_entry(m))
            added += 1
        if added > 0:
            print(f"✅ {source_name}: {added} resultados agregados")
    
    def _format_sp_entry(self, sp):
        """Formatea entrada para el listbox mostrando fuente y ambos IDs."""
        source = sp.get("source", "local").upper()
        common = sp.get("commonName", sp.get("vernacularName", ""))
        sci = sp.get("scientificName", "N/A")
        tid_gbif = sp.get("taxonID_GBIF", "")
        tid_inat = sp.get("taxonID_iNaturalist", "")
        ids_parts = []
        if tid_gbif:
            ids_parts.append(f"GBIF:{tid_gbif}")
        if tid_inat:
            ids_parts.append(f"iNat:{tid_inat}")
        ids_str = " | ".join(ids_parts) if ids_parts else "sin ID"
        return f"[{source:<6}] {common:<22} | {sci:<28} | {ids_str}"
    
    def _apply_selection(self, results, idx, spec_var, tag_var, tid_gbif_var, tid_inat_var, win):
        """Aplica la selección al formulario, guardando ambos IDs."""
        if not results or not idx:
            return
        chosen = results[idx[0]]
        sci = chosen.get("scientificName", "")
        tid_gbif = str(chosen.get("taxonID_GBIF", ""))
        tid_inat = str(chosen.get("taxonID_iNaturalist", ""))
        if "gbif.org/species/" in tid_gbif:
            tid_gbif = tid_gbif.split("/")[-1]
        source = chosen.get("source", "region")
        if source in ("gbif", "inat"):
            src_label = "GBIF" if source == "gbif" else "iNaturalist"
            if not messagebox.askyesno(
                f"Origen: {src_label}",
                f"'{sci}' proviene de {src_label}.\n"
                f"¿Agregar al species_master de {self.country_id}?",
                parent=win
            ):
                return
            self._update_master_with_both_ids(chosen)
            if chosen not in self.country_species:
                self.country_species.append(chosen)
            if chosen not in self.region_species:
                self.region_species.append(chosen)
        spec_var.set(sci)
        tid_gbif_var.set(tid_gbif)
        tid_inat_var.set(tid_inat)
        common = (chosen.get("commonName") or chosen.get("vernacularName") or "").strip()
        tag_var.set(common if common else (sci.split()[0].capitalize() if sci else ""))
    
    def _update_master_with_both_ids(self, sp):
        """Agrega/actualiza especie en species_master con ambos IDs."""
        sci = sp.get("scientificName")
        if not sci:
            return
        entry = {
            "scientificName": sci,
            "taxonID_GBIF": str(sp.get("taxonID_GBIF", "")),
            "taxonID_iNaturalist": str(sp.get("taxonID_iNaturalist", "")),
            "commonName": sp.get("commonName", sp.get("vernacularName", "")),
            "family": sp.get("family", ""),
            "order": sp.get("order", ""),
            "class": sp.get("class", ""),
            "rank": sp.get("rank", "species")
        }
        add_species_to_master(self.country_id, entry)
    
    def _update_local_jsons(self, sp):
        """Actualiza SOLO el species_master del país (regiones solo tienen nombres)."""
        sci = sp.get("scientificName")
        if not sci:
            return
        self._update_master_with_both_ids(sp)
        region_path = None
        for f in os.listdir(self.parent.regions_dir):
            if not f.endswith(".json"):
                continue
            try:
                path = os.path.join(self.parent.regions_dir, f)
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                meta = data.get("metadata") or {}
                if meta.get("region_id") == self.region_id and meta.get("country_id") == self.country_id:
                    region_path = path
                    break
            except Exception:
                continue
        if region_path:
            try:
                with open(region_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                species_names = data.get("species_names", [])
                if sci not in species_names:
                    species_names.append(sci)
                    data["species_names"] = species_names
                    with open(region_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"✅ Nombre '{sci}' agregado a región")
            except Exception as e:
                print(f"⚠️ Error actualizando región: {e}")
    
    def _search_gbif_online(self, query):
        """Busca taxones en GBIF API."""
        if not hasattr(self, '_gbif_cache'):
            self._gbif_cache = {}
        if query in self._gbif_cache:
            return self._gbif_cache[query]
        try:
            url = f"https://api.gbif.org/v1/species/search?q={query}&verbose=false&limit=30&rank=SPECIES"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            matches = []
            q = query.lower()
            def match_gbif(t):
                return t and (t.lower().startswith(q) or any(w.startswith(q) for w in t.lower().split()))
            for sp in data.get("results", []):
                sci = sp.get("canonicalName", sp.get("scientificName", ""))
                com = sp.get("vernacularName", "")
                if match_gbif(sci) or match_gbif(com):
                    matches.append({
                        "scientificName": sci,
                        "taxonID_GBIF": str(sp.get("key", "")),
                        "taxonID_iNaturalist": "",
                        "commonName": com,
                        "family": sp.get("family", ""),
                        "order": sp.get("order", ""),
                        "class": sp.get("class", ""),
                        "rank": "species"
                    })
            self._gbif_cache[query] = matches
            time.sleep(0.2)
            return matches
        except Exception as e:
            print(f"⚠️ GBIF falló: {e}")
            return []
    
    def _search_inaturalist_online(self, query):
        """Busca taxones en iNaturalist API (compatible con INABIO Ecuador)."""
        if not hasattr(self, '_inat_cache'):
            self._inat_cache = {}
        if query in self._inat_cache:
            return self._inat_cache[query]
        try:
            url = f"https://api.inaturalist.org/v1/taxa?q={query}&per_page=30&is_active=true"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            matches = []
            q = query.lower()
            def match_inat(t):
                return t and (t.lower().startswith(q) or any(w.startswith(q) for w in t.lower().split()))
            for taxon in data.get("results", []):
                sci = taxon.get("name", "")
                common_names = taxon.get("preferred_common_name", "") or ""
                if isinstance(common_names, list):
                    common_names = common_names[0] if common_names else ""
                if match_inat(sci) or match_inat(common_names):
                    matches.append({
                        "scientificName": sci,
                        "taxonID_iNaturalist": str(taxon.get("id", "")),
                        "taxonID_GBIF": str(taxon.get("gbif_id", "") or ""),
                        "commonName": common_names,
                        "rank": taxon.get("rank", ""),
                        "rank_level": taxon.get("rank_level", 0)
                    })
            self._inat_cache[query] = matches
            time.sleep(0.2)
            return matches
        except Exception as e:
            print(f"⚠️ iNaturalist falló: {e}")
            return []
    
    def _save_config(self):
        """Guarda la config con Taxon_Map simplificado (solo scientificName).
        🔒 FIX: Valida máximo 2 Principales y máximo 6 Opcionales."""
        name = self.name_var.get().strip()
        if not name:
            return messagebox.showwarning("Error", "Nombre obligatorio.", parent=self.parent)
        rows = [self.tree.item(i, "values") for i in self.tree.get_children()]
        
        # 🔒 FIX: Validar máximo 2 botones principales
        principal_count = sum(1 for tipo, tag, spec, tid_display in rows 
                             if tipo == "Principal" and tag and not tag.startswith("-"))
        if principal_count > 2:
            messagebox.showerror(
                "Error de configuración",
                f"Solo se permiten 2 botones principales.\n\n"
                f"Tienes {principal_count} filas de tipo 'Principal'.\n\n"
                f"Cambiar los extras a tipo 'Secundario' o quítalos.",
                parent=self.parent
            )
            return
        
        # 🔒 NUEVO: Validar máximo 6 opcionales
        optional_count = sum(1 for tipo, tag, spec, tid_display in rows 
                            if tipo == "Opcional" and tag and not tag.startswith("-"))
        if optional_count > 6:
            messagebox.showerror(
                "Error de configuración",
                f"Solo se permiten 6 botones opcionales como máximo.\n\n"
                f"Tienes {optional_count} filas de tipo 'Opcional'.\n\n"
                f"Quita los extras para continuar.",
                parent=self.parent
            )
            return
        
        species, secondary, behavior, other, optional = [], [], [], [], []
        taxon_map = {}
        for tipo, tag, spec, tid_display in rows:
            if not tag:
                continue
            if tag.startswith("-"):
                continue  # Filtrar ocultos
            tag_clean = tag.lstrip("-")
            if tipo == "Principal":
                species.append(tag_clean)
            elif tipo == "Secundario":
                secondary.append(tag_clean)
            elif tipo == "Comportamiento":
                behavior.append(tag_clean)
            elif tipo == "Otro":
                other.append(tag_clean)
            elif tipo == "Opcional":
                optional.append(tag_clean)
            # Taxon_Map solo guarda scientificName (IDs se resuelven al exportar)
            if tipo in ("Principal", "Secundario", "Otro") and spec:
                taxon_map[tag_clean] = {"scientificName": spec}
        
        final_data = {
            "_metadata": {
                "name": name,
                "version": "2.0",
                "country_id": self.country_id,
                "linked_region_id": self.region_id,
                "is_scientific": self.sci_var.get(),
                "created": datetime.now().strftime("%Y-%m-%d"),
                "last_modified": datetime.now().strftime("%Y-%m-%d")
            },
            "GUI_Tagger": {
                "species_tags": species,
                "secondary_tags": secondary,
                "behavior_tags": behavior,
                "other_tags_list": other,
                "optional_tags": optional  # 🔒 NUEVO
            },
            "Taxon_Map": taxon_map
        }
        safe = name.lower().replace(" ", "_").replace("/", "-")
        path = os.path.join(self.parent.configs_dir, f"{safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        self.parent.current_config_path = path
        self.parent.current_config_data = final_data
        self.parent._update_table(final_data)
        self.destroy()
        if self.parent.winfo_exists() and hasattr(self.parent, '_apply_config'):
            self.parent._apply_config()