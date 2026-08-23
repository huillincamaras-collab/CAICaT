"""
export_inabio.py - Exportación a formato INABIO (Darwin Core completo)
Incluye diálogos GUI para configurar localidades por sitio.
"""
import os
import csv
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from config_utils import load_config, resolve_taxon_id, resolve_human_activity


# =============================================================================
# CAMPOS DARWIN CORE (Todos los campos del ejemplo INABIO)
# =============================================================================
DWC_FIELDS = [
    "id", "institutionCode", "collectionCode", "ownerInstitutionCode", "collectionID",
    "basisOfRecord", "occurrenceID", "catalogNumber", "otherCatalogNumbers",
    "higherClassification", "kingdom", "phylum", "class", "order", "family",
    "scientificName", "taxonID", "scientificNameAuthorship", "genus", "subgenus",
    "specificEpithet", "verbatimTaxonRank", "infraspecificEpithet", "taxonRank",
    "identifiedBy", "dateIdentified", "identificationReferences", "identificationRemarks",
    "taxonRemarks", "identificationQualifier", "typeStatus", "recordedBy", "recordNumber",
    "eventDate", "year", "month", "day", "startDayOfYear", "endDayOfYear",
    "verbatimEventDate", "occurrenceRemarks", "habitat", "fieldNumber", "eventID",
    "informationWithheld", "dataGeneralizations", "dynamicProperties",
    "associatedOccurrences", "associatedSequences", "associatedTaxa",
    "reproductiveCondition", "establishmentMeans", "lifeStage", "sex",
    "individualCount", "preparations", "locationID", "continent", "waterBody",
    "islandGroup", "island", "country", "stateProvince", "county", "municipality",
    "locality", "locationRemarks", "decimalLatitude", "decimalLongitude",
    "geodeticDatum", "coordinateUncertaintyInMeters", "verbatimCoordinates",
    "georeferencedBy", "georeferenceProtocol", "georeferenceSources",
    "georeferenceVerificationStatus", "georeferenceRemarks",
    "minimumElevationInMeters", "maximumElevationInMeters",
    "minimumDepthInMeters", "maximumDepthInMeters", "verbatimDepth", "verbatimElevation",
    "disposition", "language", "recordEnteredBy", "modified", "rights",
    "rightsHolder", "accessRights", "recordID", "references"
]


# =============================================================================
# HELPERS
# =============================================================================
def get_sites_list_path():
    """Retorna la ruta a config/sites_list.csv."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "sites_list.csv")


def load_sites_list():
    """Carga datos administrativos de sitios desde CSV."""
    path = get_sites_list_path()
    if not os.path.exists(path):
        return {}
    sites = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                site_id = row.get("siteID", "").strip()
                if site_id:
                    sites[site_id] = {
                        "stateProvince": row.get("stateProvince", ""),
                        "county": row.get("county", ""),
                        "locality": row.get("locality", "")
                    }
    except Exception as e:
        print(f"[export_inabio] Error leyendo sites_list.csv: {e}")
    return sites


def save_sites_list(sites_data):
    """Guarda datos administrativos de sitios en CSV."""
    path = get_sites_list_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["siteID", "stateProvince", "county", "locality"])
            writer.writeheader()
            for site_id, data in sites_data.items():
                writer.writerow({
                    "siteID": site_id,
                    "stateProvince": data.get("stateProvince", ""),
                    "county": data.get("county", ""),
                    "locality": data.get("locality", "")
                })
        print(f"[export_inabio] sites_list.csv actualizado: {path}")
    except Exception as e:
        print(f"[export_inabio] Error guardando sites_list.csv: {e}")


def detect_unique_sites(metadata):
    """Extrae sitios únicos de los metadatos."""
    sites = set()
    for entry in metadata:
        site = entry.get("metadata", {}).get("site", "")
        if site:
            sites.add(site)
    return sorted(list(sites))


def parse_date_parts(event_date_str):
    """Extrae year, month, day de un string ISO 8601."""
    if not event_date_str:
        return "", "", ""
    try:
        dt_str = event_date_str.replace("Z", "").replace("+00:00", "")
        if "T" in dt_str:
            dt_str = dt_str.split("T")[0]
        parts = dt_str.split("-")
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
    except Exception:
        pass
    return "", "", ""


# =============================================================================
# DIÁLOGOS GUI
# =============================================================================
class InabioLocalityDialog(tk.Toplevel):
    """Diálogo para configurar localidades antes de exportar a INABIO."""
    
    def __init__(self, parent, metadata):
        super().__init__(parent)
        self.title("📍 Configuración de Localidades para INABIO")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()
        
        self.metadata = metadata
        self.result = None  # {site: {stateProvince, county, locality}}
        
        self.sites = detect_unique_sites(metadata)
        self.existing_sites = load_sites_list()
        
        self._build_main_ui()
    
    def _build_main_ui(self):
        """Paso 1: Selección de modo."""
        for widget in self.winfo_children():
            widget.destroy()
        
        tk.Label(self, text="¿Cómo desea asignar las localidades?", 
                 font=("Arial", 12, "bold")).pack(pady=15)
        
        self.mode_var = tk.StringVar(value="single")
        
        tk.Radiobutton(self, text="Una localidad para todos los datos", 
                       variable=self.mode_var, value="single",
                       font=("Arial", 10)).pack(anchor="w", padx=20, pady=5)
        
        tk.Radiobutton(self, text=f"Múltiples localidades ({len(self.sites)} sitios detectados)", 
                       variable=self.mode_var, value="multi",
                       font=("Arial", 10)).pack(anchor="w", padx=20, pady=5)
        
        self.reuse_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Reutilizar datos de sites_list.csv si existe", 
                       variable=self.reuse_var, font=("Arial", 9)).pack(anchor="w", padx=20, pady=10)
        
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Continuar", command=self._on_continue, 
                  bg="#4CAF50", fg="white").pack(side="left", padx=10)
    
    def _on_continue(self):
        mode = self.mode_var.get()
        if mode == "single":
            self._show_single_dialog()
        else:
            self._show_multi_dialog()
    
    def _show_single_dialog(self):
        """Paso 2A: Diálogo para localidad única."""
        for widget in self.winfo_children():
            widget.destroy()
        
        tk.Label(self, text="Ingrese la localidad única:", 
                 font=("Arial", 12, "bold")).pack(pady=15)
        
        fields = [
            ("Provincia:", "stateProvince"),
            ("Cantón:", "county"),
            ("Localidad:", "locality")
        ]
        
        self.entries = {}
        for label, key in fields:
            row = tk.Frame(self)
            row.pack(fill="x", padx=20, pady=5)
            tk.Label(row, text=label, width=12, anchor="e").pack(side="left")
            entry = tk.Entry(row, width=30)
            entry.pack(side="left", padx=5)
            self.entries[key] = entry
        
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="Atrás", command=self._build_main_ui).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Exportar", command=self._on_single_export, 
                  bg="#4CAF50", fg="white").pack(side="left", padx=10)
    
    def _on_single_export(self):
        locality_data = {key: entry.get().strip() for key, entry in self.entries.items()}
        # Aplicar a todos los sitios
        self.result = {site: locality_data.copy() for site in self.sites}
        self.destroy()
    
    def _show_multi_dialog(self):
        """Paso 2B: Diálogo para múltiples localidades."""
        for widget in self.winfo_children():
            widget.destroy()
        
        tk.Label(self, text="Asigne localidad a cada sitio:", 
                 font=("Arial", 12, "bold")).pack(pady=10)
        
        # Frame scrollable
        container = tk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.multi_frame = tk.Frame(canvas)
        self.multi_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.multi_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Headers
        headers = ["Sitio", "Provincia", "Cantón", "Localidad"]
        for i, h in enumerate(headers):
            tk.Label(self.multi_frame, text=h, font=("Arial", 9, "bold"), width=15 if i > 0 else 12).grid(row=0, column=i, padx=2, pady=2)
        
        # Entries
        self.multi_entries = {}
        for row_idx, site in enumerate(self.sites, 1):
            tk.Label(self.multi_frame, text=site, width=12, anchor="w").grid(row=row_idx, column=0, padx=2, pady=2)
            self.multi_entries[site] = {}
            existing = self.existing_sites.get(site, {}) if self.reuse_var.get() else {}
            for col_idx, key in enumerate(["stateProvince", "county", "locality"], 1):
                entry = tk.Entry(self.multi_frame, width=15)
                entry.insert(0, existing.get(key, ""))
                entry.grid(row=row_idx, column=col_idx, padx=2, pady=2)
                self.multi_entries[site][key] = entry
        
        # Checkbox para guardar
        self.save_csv_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Guardar en sites_list.csv para futuras exportaciones", 
                       variable=self.save_csv_var).pack(pady=5)
        
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Atrás", command=self._build_main_ui).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Exportar", command=self._on_multi_export, 
                  bg="#4CAF50", fg="white").pack(side="left", padx=10)
    
    def _on_multi_export(self):
        self.result = {}
        for site, entries in self.multi_entries.items():
            self.result[site] = {key: entry.get().strip() for key, entry in entries.items()}
        
        if self.save_csv_var.get():
            save_sites_list(self.result)
        
        self.destroy()


# =============================================================================
# EXPORTACIÓN PRINCIPAL
# =============================================================================
def export_to_inabio(metadata_path, output_path, locality_map, config=None):
    """
    Exporta metadata a formato INABIO (Darwin Core completo).
    
    Args:
        metadata_path: Ruta al JSON consolidado
        output_path: Ruta de salida del CSV
        locality_map: {site: {stateProvince, county, locality}}
        config: Config dict
    """
    if config is None:
        config = load_config()
    
    inabio_cfg = config.get("INABIO", {})
    
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    # Obtener country_id para resolver taxonIDs
    country_id = "ecuador"  # Default
    for entry in metadata:
        cid = entry.get("_metadata", {}).get("country_id", "")
        if cid:
            country_id = cid
            break
    
    rows = []
    for entry in metadata:
        if entry.get("ui", {}).get("is_excluded", False):
            continue
        
        site = entry.get("metadata", {}).get("site", "")
        locality_data = locality_map.get(site, {})
        deployment = entry.get("deployment", {})
        classification = entry.get("classification", {})
        species_list = classification.get("species", [])
        counts = classification.get("counts", {})
        behaviors = classification.get("behaviors", [])
        operator = entry.get("metadata", {}).get("operator", "")
        recorded_at = entry.get("metadata", {}).get("recorded_at", "")
        video_hash = entry.get("video_hash", "")
        
        year, month, day = parse_date_parts(recorded_at)
        
        if not species_list:
            # Saltar blanks (INABIO usualmente no exporta blanks)
            continue
        
        for sp in species_list:
            resolved = resolve_taxon_id(sp, country_id)
            taxon_id_inaturalist = resolved.get("taxonID_iNaturalist", "")
            taxon_id_gbif = resolved.get("taxonID_GBIF", "")
            sci_name = resolved.get("scientificName", sp)
            vern_name = resolved.get("commonName", "")
            taxon_rank = resolved.get("rank", "species")
            kingdom = resolved.get("kingdom", "Animalia")
            phylum = resolved.get("phylum", "")
            class_name = resolved.get("class", "")
            order_name = resolved.get("order", "")
            family_name = resolved.get("family", "")
            genus_name = resolved.get("genus", "")
            
            row = {field: "" for field in DWC_FIELDS}
            
            # Identificación
            row["id"] = f"{video_hash}_{sp}"
            row["occurrenceID"] = f"{video_hash}_{sp}"
            row["catalogNumber"] = video_hash
            row["recordID"] = f"{video_hash}_{sp}"
            
            # Institución
            row["institutionCode"] = inabio_cfg.get("institutionCode", "INABIOEC")
            row["collectionCode"] = inabio_cfg.get("collectionCode", "CAMTRAP")
            row["ownerInstitutionCode"] = inabio_cfg.get("ownerInstitutionCode", "INABIO")
            row["basisOfRecord"] = inabio_cfg.get("basisOfRecord", "HumanObservation")
            
            # Taxonomía
            row["scientificName"] = sci_name
            
            # 🔒 FALLBACK: Si no hay iNaturalist, usar GBIF
            if taxon_id_inaturalist:
                row["taxonID"] = taxon_id_inaturalist
            else:
                row["taxonID"] = taxon_id_gbif  # Fallback a GBIF
                print(f"[export_inabio] ⚠️ Fallback a GBIF para {sci_name} (iNaturalist vacío)")
            
            row["taxonRank"] = taxon_rank
            
            # Incluir ambos IDs en identificationReferences
            id_refs = []
            if taxon_id_inaturalist:
                id_refs.append(f"iNaturalist:{taxon_id_inaturalist}")
            if taxon_id_gbif:
                id_refs.append(f"GBIF:{taxon_id_gbif}")
            row["identificationReferences"] = " | ".join(id_refs) if id_refs else ""
            row["kingdom"] = kingdom
            row["phylum"] = phylum
            row["class"] = class_name
            row["order"] = order_name
            row["family"] = family_name
            row["genus"] = genus_name
            row["identifiedBy"] = operator
            row["dateIdentified"] = recorded_at
            
            # Evento
            row["recordedBy"] = operator
            row["eventDate"] = recorded_at
            row["year"] = year
            row["month"] = month
            row["day"] = day
            row["individualCount"] = counts.get(sp, 1)
            row["occurrenceRemarks"] = ", ".join(behaviors) if behaviors else ""
            
            # Ubicación
            row["decimalLatitude"] = deployment.get("latitude", "")
            row["decimalLongitude"] = deployment.get("longitude", "")
            row["geodeticDatum"] = "WGS84"
            row["coordinateUncertaintyInMeters"] = "50"
            row["stateProvince"] = locality_data.get("stateProvince", "")
            row["county"] = locality_data.get("county", "")
            row["locality"] = locality_data.get("locality", "")
            row["country"] = inabio_cfg.get("country", "Ecuador")
            row["locationID"] = site
            
            # Metadata
            row["modified"] = datetime.now().isoformat()
            row["language"] = inabio_cfg.get("language", "es")
            row["rights"] = inabio_cfg.get("rights", "CC-BY-4.0")
            row["rightsHolder"] = inabio_cfg.get("rightsHolder", "CAICAT Project")
            row["accessRights"] = inabio_cfg.get("accessRights", "https://creativecommons.org/licenses/by/4.0/")
            
            rows.append(row)
    
    # Escribir CSV
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=DWC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"[export_inabio] Exportación INABIO completada: {output_path} ({len(rows)} registros)")
    return output_path


# =============================================================================
# FUNCIÓN DE ENTRADA DESDE GUI
# =============================================================================
def export_inabio_gui(parent, metadata_path, config=None):
    """Abre el diálogo de localidades y exporta a INABIO."""
    if config is None:
        config = load_config()
    
    # Cargar metadata PRIMERO
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    # Crear diálogo pasando metadata directamente
    dialog = InabioLocalityDialog(parent, metadata)
    
    parent.wait_window(dialog)
    
    if dialog.result is None:
        return None  # Cancelado
    
    # Seleccionar archivo de salida
    output_folder = config.get("General", {}).get("output_folder", "")
    output_path = filedialog.asksaveasfilename(
        initialdir=output_folder,
        defaultextension=".csv",
        initialfile="export_inabio.csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        title="Guardar exportación INABIO"
    )
    
    if not output_path:
        return None
    
    try:
        result = export_to_inabio(metadata_path, output_path, dialog.result, config)
        messagebox.showinfo("Éxito", f"Exportación INABIO completada:\n{output_path}\n\n{len(dialog.result)} sitios configurados.")
        return result
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo exportar a INABIO:\n{e}")
        return None