"""
gui_batch_metadata.py - GUI para asignar metadata a carpetas procesadas en modo batch
Permite asignar site/subsite/camera/operator por carpeta, con opción de operador general.
Muestra información de videos/fotos por carpeta.
Incluye validación flexible y botón para descartar lote.
"""
import tkinter as tk
from tkinter import messagebox, ttk
import json
import os
from config_utils import generate_session_id, load_config
from procesamiento_batch import (
    apply_metadata_to_batch, 
    create_batch_session_metadata,
    discard_batch
)


class BatchMetadataGUI(tk.Tk):
    def __init__(self, manifest_path):
        super().__init__()
        
        self.manifest_path = manifest_path
        self.config_data = load_config()
        
        # Cargar manifest
        with open(manifest_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        
        self.title("📦 Asignar Metadata al Lote")
        self.geometry("900x700")
        
        self.folder_entries = {}
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#2196f3", height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header, 
            text="📦 Asignar Metadata por Carpeta", 
            bg="#2196f3", 
            fg="white",
            font=("Arial", 14, "bold")
        ).pack(pady=15)
        
        # Info del batch
        info_frame = tk.Frame(self)
        info_frame.pack(fill="x", padx=10, pady=10)
        
        batch_id = self.manifest.get("batch_id", "")
        folder_count = len(self.manifest.get("folders", {}))
        
        # Contar videos y fotos totales
        total_videos = 0
        total_photos = 0
        total_errors = 0
        for folder_info in self.manifest.get("folders", {}).values():
            total_videos += folder_info.get("video_count", 0)
            total_photos += folder_info.get("photo_count", 0)
            total_errors += len(folder_info.get("error_files", []))
        
        info_text = f"Lote: {batch_id} | Carpetas: {folder_count} | Videos: {total_videos} | Fotos: {total_photos}"
        if total_errors > 0:
            info_text += f" | ⚠️ Errores: {total_errors}"
        
        tk.Label(
            info_frame,
            text=info_text,
            font=("Arial", 10, "bold")
        ).pack(anchor="w")
        
        tk.Label(
            info_frame,
            text="Asigne metadata a cada carpeta. Los valores se aplicarán a todos los archivos dentro de cada carpeta.",
            font=("Arial", 9),
            fg="gray"
        ).pack(anchor="w", pady=(5, 0))
        
        # Operador general
        operator_frame = tk.LabelFrame(
            self,
            text="Operador General (opcional)",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10
        )
        operator_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(
            operator_frame,
            text="Si ingresa un operador aquí, se aplicará a todas las carpetas:",
            font=("Arial", 9),
            fg="gray"
        ).pack(anchor="w", pady=(0, 5))
        
        self.general_operator_var = tk.StringVar()
        operator_entry = tk.Entry(operator_frame, textvariable=self.general_operator_var, width=30)
        operator_entry.pack(anchor="w")
        
        tk.Button(
            operator_frame,
            text="✓ Aplicar operador general a todas las carpetas",
            command=self._apply_general_operator,
            font=("Arial", 9),
            bg="#4CAF50",
            fg="white"
        ).pack(anchor="w", pady=(5, 0))
        
        # Scrollable frame para carpetas
        container = tk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.folders_frame = tk.Frame(canvas)
        
        self.folders_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.folders_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Crear inputs para cada carpeta
        for idx, (folder_key, folder_info) in enumerate(self.manifest.get("folders", {}).items()):
            self._create_folder_input(idx, folder_key, folder_info)
        
        # Botones
        button_frame = tk.Frame(self)
        button_frame.pack(pady=15)
        
        # 🔒 Botón Descartar Lote
        tk.Button(
            button_frame,
            text="🗑️ Descartar Lote",
            command=self._discard_batch,
            bg="#f44336",
            fg="white",
            width=15
        ).pack(side="left", padx=5)
        
        tk.Button(
            button_frame,
            text="Cancelar",
            command=self.destroy,
            width=15
        ).pack(side="left", padx=5)
        
        tk.Button(
            button_frame,
            text="✓ Generar sesión y abrir tagger",
            command=self.apply_and_continue,
            bg="#4CAF50",
            fg="white",
            width=25,
            font=("Arial", 10, "bold")
        ).pack(side="left", padx=5)
    
    def _create_folder_input(self, index, folder_key, folder_info):
        """Crea un bloque de inputs para una carpeta."""
        # 🔒 Indicador de estado
        status = folder_info.get("status", "pending")
        error_count = len(folder_info.get("error_files", []))
        
        status_icon = {
            "pending": "⏳",
            "processing": "⏳",
            "completed": "✅",
            "completed_with_errors": "⚠️",
            "error": "❌"
        }.get(status, "⏳")
        
        # Frame contenedor
        folder_frame = tk.LabelFrame(
            self.folders_frame,
            text=f"{status_icon} 📁 {folder_info.get('relative_path', folder_key)}",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10
        )
        folder_frame.pack(fill="x", padx=5, pady=5)
        
        # Info de la carpeta
        video_count = folder_info.get("video_count", 0)
        photo_count = folder_info.get("photo_count", 0)
        info_text = f"🎥 Videos: {video_count} | 📷 Fotos: {photo_count} | Total: {video_count + photo_count}"
        
        if error_count > 0:
            info_text += f" | ❌ Errores: {error_count}"
        
        tk.Label(
            folder_frame,
            text=info_text,
            font=("Arial", 9),
            fg="gray"
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        
        # Inputs
        fields = [
            ("site", "Sitio:"),
            ("subsite", "Subsitio:"),
            ("camera", "Cámara:"),
            ("operator", "Operador:")
        ]
        
        entries = {}
        for row, (field, label) in enumerate(fields, start=1):
            tk.Label(
                folder_frame,
                text=label,
                font=("Arial", 9)
            ).grid(row=row, column=0, sticky="e", padx=(0, 5), pady=2)
            
            entry = tk.Entry(folder_frame, width=25)
            entry.grid(row=row, column=1, sticky="w", pady=2)
            
            # Pre-cargar si ya existe
            existing_value = folder_info.get("metadata", {}).get(field, "")
            if existing_value:
                entry.insert(0, existing_value)
            
            entries[field] = entry
        
        self.folder_entries[folder_key] = entries
    
    def _apply_general_operator(self):
        """Aplica el operador general a todas las carpetas."""
        operator = self.general_operator_var.get().strip()
        if not operator:
            messagebox.showwarning(
                "Campo vacío",
                "Ingrese un operador en el campo general.",
                parent=self
            )
            return
        
        # Aplicar a todas las carpetas
        for folder_key, entries in self.folder_entries.items():
            entries["operator"].delete(0, tk.END)
            entries["operator"].insert(0, operator)
        
        messagebox.showinfo(
            "Aplicado",
            f"Operador '{operator}' aplicado a todas las carpetas.",
            parent=self
        )
    
    def _discard_batch(self):
        """Descarta completamente el lote."""
        result = messagebox.askyesno(
            "Descartar Lote",
            "¿Está seguro de que desea descartar este lote?\n\n"
            "Se eliminarán:\n"
            "• Todos los archivos procesados\n"
            "• La sesión de etiquetado\n"
            "• El manifest del lote\n\n"
            "Esta acción no se puede deshacer.",
            parent=self
        )
        
        if not result:
            return
        
        output_folder = self.config_data["General"]["output_folder"]
        success = discard_batch(output_folder)
        
        if success:
            messagebox.showinfo(
                "Lote descartado",
                "El lote ha sido descartado correctamente.",
                parent=self
            )
            self.destroy()
        else:
            messagebox.showerror(
                "Error",
                "No se pudo descartar el lote.",
                parent=self
            )
    
    def apply_and_continue(self):
        """Aplica la metadata y prepara para abrir el tagger."""
        # 🔒 VALIDACIÓN FLEXIBLE: Solo advertencia, no error
        missing_folders = []
        folder_metadata = {}
        
        for folder_key, entries in self.folder_entries.items():
            metadata = {}
            has_missing = False
            
            for field, entry in entries.items():
                value = entry.get().strip()
                if not value:
                    has_missing = True
                metadata[field] = value
            
            if has_missing:
                missing_folders.append(folder_key)
            
            folder_metadata[folder_key] = metadata
        
        # Advertencia si hay campos vacíos (pero permitir continuar)
        if missing_folders:
            result = messagebox.askyesno(
                "Campos incompletos",
                f"Las siguientes carpetas tienen campos vacíos:\n\n" +
                "\n".join(f"• {f}" for f in missing_folders[:5]) +
                ("\n..." if len(missing_folders) > 5 else "") +
                "\n\n¿Desea continuar de todos modos?\n"
                "(Los campos vacíos se exportarán como vacíos)",
                parent=self
            )
            if not result:
                return
        
        # Aplicar metadata al manifest
        try:
            apply_metadata_to_batch(self.manifest_path, folder_metadata)
            
            # Crear session_id
            session_id = generate_session_id(self.config_data)
            
            # Crear metadata.json para el tagger
            output_folder = self.config_data["General"]["output_folder"]
            metadata_path = create_batch_session_metadata(
                self.manifest_path,
                output_folder,
                session_id
            )
            
            # Contar archivos totales (solo los procesados correctamente)
            total_files = sum(
                len([f for f in folder_info.get("files", []) if f.get("status") == "done"])
                for folder_info in self.manifest.get("folders", {}).values()
            )
            
            # Contar errores
            total_errors = sum(
                len(folder_info.get("error_files", []))
                for folder_info in self.manifest.get("folders", {}).values()
            )
            
            success_msg = f"Metadata aplicada correctamente.\n\n"
            success_msg += f"Se abrirá el tagger para etiquetar {total_files} archivos."
            
            if total_errors > 0:
                success_msg += f"\n\n⚠️ {total_errors} archivos tuvieron errores durante el procesamiento."
            
            messagebox.showinfo(
                "Éxito",
                success_msg,
                parent=self
            )
            
            # Abrir tagger
            self.destroy()
            self._open_tagger(metadata_path, session_id)
            
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"No se pudo aplicar la metadata:\n{e}",
                parent=self
            )
    
    def _open_tagger(self, metadata_path, session_id):
        """Abre el tagger con el lote procesado."""
        from gui_tagger import DynamicTagger
        
        app = DynamicTagger(
            metadata_path=metadata_path,
            session_id=session_id,
            scientific_mode=False
        )
        app.mainloop()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        manifest_path = sys.argv[1]
        app = BatchMetadataGUI(manifest_path)
        app.mainloop()
    else:
        print("Uso: python gui_batch_metadata.py <ruta_al_manifest>")