import tkinter as tk
from tkinter import messagebox
import os
import sys  
import subprocess

from config_utils import load_config, update_summaries_from_metadata
from sort_rename import run_sort_rename_advanced
from gui_excel_export import ExcelExportGUI  # existente
from gui_analysis import AnalysisGUI  # <-- import del nuevo análisis


def find_last_session(output_folder):
    """Encuentra la carpeta de sesión más reciente en output_folder/sessions/."""
    sessions_dir = os.path.join(output_folder, "sessions")
    if not os.path.exists(sessions_dir):
        return None

    session_folders = []
    for item in os.listdir(sessions_dir):
        item_path = os.path.join(sessions_dir, item)
        if os.path.isdir(item_path):
            # Obtener fecha de modificación más reciente dentro de la carpeta
            mtime = os.path.getmtime(item_path)
            session_folders.append((mtime, item))

    if not session_folders:
        return None

    # Ordenar por fecha (más reciente primero)
    session_folders.sort(key=lambda x: x[0], reverse=True)
    return os.path.join(sessions_dir, session_folders[0][1])

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # --- Cargar configuración ---
        try:
            self.config_data = load_config()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar la configuración:\n{e}")
            self.config_data = {}

        self.title(self.config_data.get("GUI_Main", {}).get("title", "Caicat2.0 - Main"))
        self.geometry(self.config_data.get("GUI_Main", {}).get("geometry", "1000x700"))
        self.configure(bg="#e0e0e0")  # Fondo general

        # Actualizar resúmenes
        try:
            update_summaries_from_metadata()
        except Exception as e:
            messagebox.showwarning("Advertencia", f"No se pudieron actualizar los resúmenes automáticamente:\n{e}")

        # --- Detectar última sesión para reanudar ---
        self.last_session_folder = find_last_session(self.config_data["General"]["output_folder"])
        self.build_layout()

    def build_layout(self):
        labels = self.config_data.get('Labels', {})

        main_frame = tk.Frame(self, bg="#e0e0e0")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Frame para botones a la izquierda ---
        button_frame = tk.Frame(main_frame, bg="#d0d0d0", relief="raised", bd=2)
        button_frame.pack(side="left", fill="y", padx=(0,10), pady=5)

        # Botón de Reanudar sesión (si existe)
        if self.last_session_folder:
            session_id = os.path.basename(self.last_session_folder)
            tk.Button(button_frame, text=f"Reanudar sesión", width=20, height=2,
                      command=self.resume_last_session, bg="#ff5722", fg="white").pack(pady=5)

        # Botón de Análisis rápido

        tk.Button(button_frame, text=labels.get('btn_etiquetar_videos','Etiquetar Videos'),
                  width=20, height=2, command=self.run_gui_inicial, bg="#4caf50", fg="white").pack(pady=5)
        
        tk.Button(button_frame, text="Análisis rápido", width=20, height=2,
                  command=self.run_analysis_gui, bg="#9c27b0", fg="white").pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_generar_excel','Generar Excel'),
                  width=20, height=2, command=self.run_excel_export, bg="#2196f3", fg="white").pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_rename_sort','Sort & Rename'),
                  width=20, height=2, command=self.run_sort_rename, bg="#ff9800", fg="white").pack(pady=5)
        
        tk.Button(button_frame, text="Incrustar Metadatos",
          width=20, height=2,
          command=self.run_embed_metadata,
          bg="#607d8b", fg="white").pack(pady=5)

        # --- Frame para resúmenes a la derecha ---
        summary_frame = tk.Frame(main_frame, bg="#e0e0e0")
        summary_frame.pack(side="left", fill="both", expand=True, pady=5)

        # Resumen Global
        summary_global_frame = tk.Frame(summary_frame, bg="#f8f8f8", relief="groove", bd=2)
        summary_global_frame.pack(fill="x", padx=5, pady=5)
        summary = self.config_data.get('SummaryGlobal', {})
        tk.Label(summary_global_frame, text=f"Total de sesiones: {summary.get('total_sessions','0')}", 
                 font=("Arial", 12, "bold"), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Total de sitios: {summary.get('total_sites','0')}", 
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Sitios: {', '.join(summary.get('list_sites',[]))}", 
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Total de videos procesados: {summary.get('total_videos_processed','0')}", 
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Operadores: {', '.join(summary.get('list_operators',[]))}", 
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Especies identificadas: {summary.get('total_species_identified','0')}", 
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)

        # Última sesión
        last_frame = tk.Frame(summary_frame, bg="#f8f8f8", relief="groove", bd=2)
        last_frame.pack(fill="x", padx=5, pady=5)
        last = self.config_data.get('LastSession', {})
        tk.Label(last_frame, text="--- Última sesión ---", font=("Arial", 12, "bold"), bg="#f8f8f8").pack(anchor="w", padx=10, pady=(5,0))
        tk.Label(last_frame, text=f"Operador: {last.get('operator','')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Sitio_Subsitio_Cámara: {last.get('site_subsite_camera','')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Fecha: {last.get('date','')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"ID Sesión: {last.get('session_id','')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Videos procesados: {last.get('videos_processed','0')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Especies identificadas: {', '.join(last.get('species_identified',[]))}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)

        # --- Frame para logo o imagen debajo de botones y resúmenes ---
        logo_frame = tk.Frame(self, bg="#cccccc", relief="ridge", bd=2, height=150)
        logo_frame.pack(fill="x", padx=10, pady=10)
        tk.Label(logo_frame, text="Aquí irá el Logo o Imagen", bg="#cccccc", font=("Arial", 14, "bold")).pack(expand=True)

        # --- Frame para Setup y ayuda ---
        setup_frame = tk.Frame(self, bg="#f0f0f0")
        setup_frame.pack(fill="x", padx=10, pady=(0,10))

        # Botón de Setup (tamaño igual al de ?)
        setup_btn = tk.Button(setup_frame, text="...", width=3, height=1, command=self.run_setup,
                              bg="#4caf50", fg="white", font=("Arial", 14, "bold"))
        setup_btn.pack(side="right", padx=(0,5))

        # Botón de Ayuda
        help_btn = tk.Button(setup_frame, text="?", width=3, height=1, command=self.show_help, 
                             bg="#2196f3", fg="white", font=("Arial", 14, "bold"))
        help_btn.pack(side="right", padx=(0,10))


    def run_gui_inicial(self):
        gui_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "gui_inicial.py")
        try:
            subprocess.Popen([sys.executable, gui_path])
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir GUI Inicial:\n{e}")

    def run_sort_rename(self):
        try:
            # ←←← CORREGIDO: usar el archivo consolidado en vez de videos_metadata.json
            consolidated_dir = os.path.join(self.config_data['General']['output_folder'], "consolidated")
            metadata_path = os.path.join(consolidated_dir, "all_sessions_metadata.json")
            
            # Verificar que el archivo exista
            if not os.path.exists(metadata_path):
                messagebox.showerror(
                    "Error", 
                    "No se encontró el archivo consolidado de metadatos.\n"
                    "Asegúrese de haber completado al menos una sesión de etiquetado."
                )
                return
            
            self.destroy()
            run_sort_rename_advanced(metadata_path)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir Sort & Rename:\n{e}")

    def run_excel_export(self):
        try:
            self.destroy()
            ExcelExportGUI().mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la herramienta de exportación a Excel:\n{e}")

    def run_analysis_gui(self):
        try:
            self.destroy()
            AnalysisGUI().mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el Análisis rápido:\n{e}")

    def run_embed_metadata(self):
        try:
            self.destroy()
            from embed_metadata import EmbedMetadataGUI
            app = EmbedMetadataGUI()
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la herramienta de incrustación:\n{e}")

    def run_setup(self):
        try:
            import gui_setup
            self.destroy()
            gui_setup.SetupApp().mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la configuración (Setup):\n{e}")

    def not_implemented(self):
        messagebox.showinfo("Info", "Funcionalidad no implementada aún.")

    def show_help(self):
        messagebox.showinfo("Ayuda", "Este botón abrirá la documentación o asistencia de la aplicación.\n\nPor ahora es un placeholder.")

    def resume_last_session(self):
        if not self.last_session_folder:
            messagebox.showerror("Error", "No se encontró una sesión anterior.")
            return

        session_id = os.path.basename(self.last_session_folder)
        metadata_path = os.path.join(self.last_session_folder, "metadata.json")

        if not os.path.exists(metadata_path):
            messagebox.showerror("Error", f"No se encontró metadata.json en la sesión:\n{session_id}")
            return

        try:
            self.destroy()
            from gui_tagger import DynamicTagger
            app = DynamicTagger(metadata_path=metadata_path, session_id=session_id)
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo reanudar la sesión:\n{e}")

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
