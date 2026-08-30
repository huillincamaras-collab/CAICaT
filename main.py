import tkinter as tk
from tkinter import messagebox
import os
import sys
import json
import datetime
import subprocess

from config_utils import load_config, update_summaries_from_metadata
from sort_rename import run_sort_rename_advanced
from gui_excel_export import ExcelExportGUI
from gui_analysis import AnalysisGUI

def open_manual():
    """Abre el manual.pdf ubicado en la misma carpeta que el ejecutable/script."""
    import sys
    import subprocess
    from tkinter import messagebox
    
    # 🔒 Detectar ruta base (compatible con Nuitka y script)
    if getattr(sys, 'frozen', False):
        # Compilado con Nuitka: el PDF está junto al .exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # Script Python: el PDF está junto a main.py
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    manual_path = os.path.join(base_dir, "manual.pdf")
    
    if not os.path.exists(manual_path):
        messagebox.showerror(
            "Manual no encontrado",
            f"No se encontró manual.pdf en:\n{base_dir}\n\n"
            f"Coloque el archivo manual.pdf junto al ejecutable.",
            parent=None
        )
        return
    
    # 🔒 Abrir PDF según el sistema operativo
    try:
        if os.name == 'nt':  # Windows
            os.startfile(manual_path)
        elif sys.platform == 'darwin':  # macOS
            subprocess.Popen(['open', manual_path])
        else:  # Linux
            subprocess.Popen(['xdg-open', manual_path])
    except Exception as e:
        messagebox.showerror(
            "Error al abrir manual",
            f"No se pudo abrir manual.pdf:\n{e}",
            parent=None
        )

def find_all_sessions(output_folder):
    """Devuelve lista de sesiones ordenadas: incompletas primero, luego por fecha descendente."""
    sessions_dir = os.path.join(output_folder, "sessions")
    if not os.path.exists(sessions_dir):
        return []

    sessions = []
    for item in os.listdir(sessions_dir):
        item_path = os.path.join(sessions_dir, item)
        if not os.path.isdir(item_path):
            continue

        metadata_path = os.path.join(item_path, "metadata.json")
        if not os.path.exists(metadata_path):
            continue

        session_info_path = os.path.join(item_path, "session_info.json")
        completed = False
        if os.path.exists(session_info_path):
            try:
                with open(session_info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                completed = info.get("session_completed", False)
            except Exception:
                pass

        mtime = os.path.getmtime(metadata_path)
        sessions.append({
            "session_id": item,
            "folder": item_path,
            "metadata_path": metadata_path,
            "session_info_path": session_info_path,
            "completed": completed,
            "mtime": mtime
        })

    # Incompletas primero, luego por fecha descendente
    sessions.sort(key=lambda x: (x["completed"], -x["mtime"]))
    return sessions


def show_session_selector(parent, sessions):
    """Muestra diálogo para elegir sesión. Retorna la sesión elegida o None."""
    from tkinter import Toplevel, Listbox, Scrollbar, Button, Label, Frame, END, SINGLE

    selected = [None]

    dialog = Toplevel(parent)
    dialog.title("Seleccionar sesión")
    dialog.geometry("600x400")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.focus_set()

    Label(dialog, text="Seleccione una sesión para reanudar:", font=("Arial", 11, "bold")).pack(pady=(10, 5))

    list_frame = Frame(dialog)
    list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    scrollbar = Scrollbar(list_frame)
    scrollbar.pack(side="right", fill="y")

    listbox = Listbox(list_frame, yscrollcommand=scrollbar.set, selectmode=SINGLE,
                      font=("Courier", 10), width=70)
    listbox.pack(fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    for s in sessions:
        fecha = datetime.datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d %H:%M")
        estado = "✓ Completa" if s["completed"] else "⏳ Incompleta"

        n_videos = "?"
        n_tagged = "?"
        try:
            with open(s["metadata_path"], "r", encoding="utf-8") as f:
                videos = json.load(f)
            n_videos = len(videos)
            n_tagged = sum(1 for v in videos if v.get("classification", {}).get("species"))
        except Exception:
            pass

        line = f"{fecha}  |  {estado}  |  {n_tagged}/{n_videos} etiquetados  |  {s['session_id']}"
        listbox.insert(END, line)

    if sessions:
        listbox.selection_set(0)
        listbox.activate(0)

    btn_frame = Frame(dialog)
    btn_frame.pack(pady=10)

    def confirmar():
        idx = listbox.curselection()
        if idx:
            selected[0] = sessions[idx[0]]
        dialog.destroy()

    def cancelar():
        dialog.destroy()

    Button(btn_frame, text="Abrir", command=confirmar, bg="#4CAF50", fg="#111111", width=10, font=("Arial", 11)).pack(side="left", padx=5)
    Button(btn_frame, text="Cancelar", command=cancelar, width=10, fg="#111111", font=("Arial", 11)).pack(side="left", padx=5)

    parent.wait_window(dialog)
    return selected[0]


def is_session_pending(session_path):
    import json, os
    meta_path = os.path.join(session_path, "metadata.json")
    if not os.path.exists(meta_path): return True
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return any(
            (v.get("status") != "done") or 
            (not v.get("classification", {}).get("species") and not v.get("ui", {}).get("is_excluded", False))
            for v in data
        )
    except: return True


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
        self.configure(bg="#e0e0e0")

        # Actualizar resúmenes
        try:
            update_summaries_from_metadata()
        except Exception as e:
            messagebox.showwarning("Advertencia", f"No se pudieron actualizar los resúmenes automáticamente:\n{e}")

        # --- Cargar todas las sesiones disponibles ---
        self.all_sessions = find_all_sessions(self.config_data["General"]["output_folder"])
        
        # --- Detectar última sesión ---
        self.last_session_folder = None
        if self.all_sessions:
            # Get the most recent session (first in the list after sorting)
            self.last_session_folder = self.all_sessions[0]["folder"]
        
        self.build_layout()

    def build_layout(self):
        labels = self.config_data.get('Labels', {})

        main_frame = tk.Frame(self, bg="#e0e0e0")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Frame para botones a la izquierda ---
        button_frame = tk.Frame(main_frame, bg="#d0d0d0", relief="raised", bd=2)
        button_frame.pack(side="left", fill="y", padx=(0, 10), pady=5)

        # Botón de Reanudar sesión (solo si realmente queda trabajo pendiente)
        if self.last_session_folder and is_session_pending(self.last_session_folder):
            session_id = os.path.basename(self.last_session_folder)
            tk.Button(button_frame, text="Reanudar sesión", width=20, height=2,
                      command=self.resume_last_session, bg="#ff5722", fg="#111111", font=("Arial", 11)).pack(pady=5)
        elif self.last_session_folder:
            tk.Label(button_frame, text="✅ Última sesión completa", 
                     font=("Arial", 9), fg="gray").pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_etiquetar_videos', 'Etiquetar Videos'),
                  width=20, height=2, command=self.run_gui_inicial, bg="#4caf50", fg="#111111", font=("Arial", 11)).pack(pady=5)

        tk.Button(button_frame, text="Análisis rápido", width=20, height=2,
                  command=self.run_analysis_gui, bg="#9c27b0", fg="#111111", font=("Arial", 11)).pack(pady=5)

        # 🔍 Botón de Auditoría (visible solo si está habilitado en config.ini)
        auditor_cfg = self.config_data.get("Auditor", {})
        if auditor_cfg.get("is_enabled", False):
            tk.Button(button_frame, text="🔍 Auditar", width=20, height=2,
                    command=self.run_auditor, bg="#FF9800", fg="#111111", font=("Arial", 11)).pack(pady=5)
        
        # ✨ Botón "Corregir etiquetados" (condicional - solo si hay videos marcados)
        self.correction_btn = tk.Button(button_frame, text="🔖 Corregir Etiquetados", width=20, height=2,
                    command=self.open_correction_tagger, bg="#E91E63", fg="#111111", font=("Arial", 11))
        
        if self._has_videos_needing_correction():
            self.correction_btn.pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_generar_excel', 'Generar Excel'),
                  width=20, height=2, command=self.run_excel_export, bg="#2196f3", fg="#111111", font=("Arial", 11)).pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_rename_sort', 'Sort & Rename'),
                  width=20, height=2, command=self.run_sort_rename, bg="#ff9800", fg="#111111", font=("Arial", 11)).pack(pady=5)

        tk.Button(button_frame, text="Incrustar Metadatos", width=20, height=2,
                  command=self.run_embed_metadata, bg="#607d8b", fg="#111111", font=("Arial", 11)).pack(pady=5)
        
        # ✨ MODO BATCH
        tk.Button(button_frame, text="📦 Lote", width=20, height=2,
                  command=self.run_batch_mode, bg="#9C27B0", fg="#111111", font=("Arial", 11)).pack(pady=5)
        
        # Botón "Continuar Lote" - solo visible si existe batch pendiente
        self.continue_batch_btn = tk.Button(button_frame, text="📂 Continuar Lote", width=20, height=2,
                  command=self.continue_batch, bg="#673AB7", fg="#111111", font=("Arial", 11))
        
        if self._has_pending_batch():
            self.continue_batch_btn.pack(pady=5)

        # --- Frame para resúmenes a la derecha ---
        summary_frame = tk.Frame(main_frame, bg="#e0e0e0")
        summary_frame.pack(side="left", fill="both", expand=True, pady=5)

        # Resumen Global
        summary_global_frame = tk.Frame(summary_frame, bg="#f8f8f8", relief="groove", bd=2)
        summary_global_frame.pack(fill="x", padx=5, pady=5)
        summary = self.config_data.get('SummaryGlobal', {})
        tk.Label(summary_global_frame, text=f"Total de sesiones: {summary.get('total_sessions', '0')}",
                 font=("Arial", 12, "bold"), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Total de sitios: {summary.get('total_sites', '0')}",
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Sitios: {', '.join(summary.get('list_sites', []))}",
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Total de videos procesados: {summary.get('total_videos_processed', '0')}",
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Operadores: {', '.join(summary.get('list_operators', []))}",
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)
        tk.Label(summary_global_frame, text=f"Especies identificadas: {summary.get('total_species_identified', '0')}",
                 font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10, pady=2)

        # Última sesión
        last_frame = tk.Frame(summary_frame, bg="#f8f8f8", relief="groove", bd=2)
        last_frame.pack(fill="x", padx=5, pady=5)
        last = self.config_data.get('LastSession', {})
        tk.Label(last_frame, text="--- Última sesión ---", font=("Arial", 12, "bold"), bg="#f8f8f8").pack(anchor="w", padx=10, pady=(5, 0))
        tk.Label(last_frame, text=f"Operador: {last.get('operator', '')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Sitio_Subsitio_Cámara: {last.get('site_subsite_camera', '')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Fecha: {last.get('date', '')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"ID Sesión: {last.get('session_id', '')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Videos procesados: {last.get('videos_processed', '0')}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)
        tk.Label(last_frame, text=f"Especies identificadas: {', '.join(last.get('species_identified', []))}", font=("Arial", 12), bg="#f8f8f8").pack(anchor="w", padx=10)

        # --- LOGO FLOTANTE ---
        try:
            from PIL import Image, ImageTk

            logo_path = os.path.join(os.path.dirname(__file__), "caicat_transparente.png")

            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                logo_img = logo_img.resize((500, 200), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_img)
                self.logo_label = tk.Label(self, image=self.logo_photo, bg="#e0e0e0")
                self.logo_label.place(relx=0.5, rely=0.7, anchor="n")
            else:
                print("⚠️ No se encontró caicat_transparente.png")

        except Exception as e:
            print(f"Error cargando logo: {e}")

        # --- Frame para Setup y ayuda ---
        setup_frame = tk.Frame(self, bg="#f0f0f0")
        setup_frame.pack(fill="x", padx=10, pady=(0, 10))

        setup_btn = tk.Button(setup_frame, text="...", width=3, height=1, command=self.run_setup,
                              bg="#4caf50", fg="white", font=("Arial", 14, "bold"))
        setup_btn.pack(side="right", padx=(0, 5))

        help_btn = tk.Button(setup_frame, text="?", width=3, height=1, command=open_manual,
                            bg="#2196f3", fg="white", font=("Arial", 14, "bold"))
        help_btn.pack(side="right", padx=(0, 10))

    def resume_last_session(self):
        """Resume the most recent session directly without showing selector."""
        if not self.last_session_folder:
            messagebox.showerror("Error", "No se encontró una sesión para reanudar.")
            return
        
        metadata_path = os.path.join(self.last_session_folder, "metadata.json")
        session_id = os.path.basename(self.last_session_folder)
        
        try:
            self.destroy()
            from gui_tagger import DynamicTagger
            app = DynamicTagger(metadata_path=metadata_path, session_id=session_id)
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la sesión:\n{e}")

    def resume_session(self):
        if not self.all_sessions:
            messagebox.showerror("Error", "No se encontraron sesiones.")
            return

        session = show_session_selector(self, self.all_sessions)
        if session is None:
            return

        metadata_path = session["metadata_path"]
        session_id = session["session_id"]

        try:
            self.destroy()
            from gui_tagger import DynamicTagger
            app = DynamicTagger(metadata_path=metadata_path, session_id=session_id)
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la sesión:\n{e}")

    def run_gui_inicial(self):
        try:
            # Importar directamente la clase GUIInicial
            # Esto asegura que el código esté incluido dentro del .exe por Nuitka
            from gui_inicial import GUIInicial
            
            # Destruir la ventana actual (MainApp) para liberar memoria
            self.destroy()
            # Crear y lanzar la nueva ventana
            app = GUIInicial()
            app.mainloop()
        except Exception as e:
            import traceback
            messagebox.showerror(
                "Error Crítico", 
                f"No se pudo iniciar la configuración inicial:\n{e}\n\n"
                f"Detalles técnicos:\n{traceback.format_exc()}"
            )
    def run_sort_rename(self):
        try:
            consolidated_dir = os.path.join(self.config_data['General']['output_folder'], "consolidated")
            metadata_path = os.path.join(consolidated_dir, "all_sessions_metadata.json")

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
        # Método nuevo a agregar en la clase MainApp:

    def run_auditor(self):
        try:
            from gui_auditor import AuditorGUI
            self.destroy()
            AuditorGUI().mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el módulo de auditoría:\n{e}")
    
    # ========== MÉTODOS PARA MODO BATCH ==========
    
    def _has_pending_batch(self):
        """Detecta si existe una carpeta batch/ con manifest pendiente."""
        output_folder = self.config_data["General"]["output_folder"]
        batch_folder = os.path.join(output_folder, "batch")
        manifest_path = os.path.join(batch_folder, "batch_manifest.json")
        if not os.path.exists(manifest_path):
            return False
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            status = manifest.get("status", "")
            # Pendiente si necesita procesamiento o asignación de metadata
            return status in [
                "pending_processing",
                "processing",
                "completed_with_errors",
                "pending_metadata_assignment",
                "ready_for_tagging"
            ]
        except Exception:
            return False

    def run_batch_mode(self):
        from gui_batch import run_batch_interactive
        run_batch_interactive(self)

    def _process_batch_with_progress(self, folder_structure, output_folder, use_legacy, manifest_path):
        """Procesa batch mostrando progreso."""
        import threading
        from procesamiento_batch import process_batch_videos
        # Crear ventana de progreso
        progress_window = tk.Toplevel(self)
        progress_window.title("Procesando lote...")
        progress_window.geometry("550x250")
        progress_window.transient(self)
        progress_window.grab_set()
        tk.Label(
            progress_window,
            text="📦 Procesando lote (no cierres esta ventana)",
            font=("Arial", 12, "bold")
        ).pack(pady=10)
        progress_label = tk.Label(progress_window, text="Iniciando...", font=("Arial", 10), wraplength=500)
        progress_label.pack(pady=5)
        phase_label = tk.Label(progress_window, text="", font=("Arial", 9), fg="gray")
        phase_label.pack(pady=2)
        # Callback con la nueva firma (4 parámetros)
        def update_progress(folder_key, current, total, phase="processing"):
            phase_text = {
                "starting": "🔄 Iniciando carpeta...",
                "processing": f"🎥 Procesando archivo {current}/{total}...",
                "completed": "✅ Carpeta completada"
            }.get(phase, phase)
            progress_label.config(text=f"Carpeta: {folder_key}\n{phase_text}")
            phase_label.config(text=f"Progreso: {current}/{total}")
        def process():
            try:
                # Procesar (ahora pasando manifest_path)
                process_batch_videos(
                    folder_structure, 
                    output_folder, 
                    manifest_path,  # ← NUEVO parámetro
                    use_legacy=use_legacy, 
                    progress_callback=update_progress
                )
                # Al terminar, cerrar ventana de progreso y abrir GUI de metadata
                progress_window.destroy()
                self._open_batch_metadata_gui(manifest_path)
            except Exception as e:
                import traceback
                progress_window.destroy()
                messagebox.showerror(
                    "Error", 
                    f"Error durante el procesamiento:\n{e}\n\n{traceback.format_exc()}"
                )
        # Iniciar procesamiento en thread
        threading.Thread(target=process, daemon=True).start()
                
    def continue_batch(self):
        from gui_batch import continue_batch_interactive
        continue_batch_interactive(self)

    def _resume_batch_processing(self, manifest_path, manifest):
        """Reanuda el procesamiento de un batch interrumpido."""
        from procesamiento_batch import resume_batch_processing
        output_folder = self.config_data["General"]["output_folder"]
        # Reconstruir folder_structure desde el manifest (solo carpetas pendientes)
        folder_structure = {}
        for folder_key, folder_data in manifest.get("folders", {}).items():
            if folder_data.get("status") in ("pending", "error"):
                folder_structure[folder_key] = {
                    "path": folder_data["original_path"],
                    "videos": [],  # Se re-escanearán
                    "photos": [],
                    "relative_path": folder_data.get("relative_path", ""),
                    "video_count": folder_data.get("video_count", 0),
                    "photo_count": folder_data.get("photo_count", 0)
                }
        if not folder_structure:
            messagebox.showinfo("Info", "No hay carpetas pendientes para procesar.")
            return
        use_legacy = manifest.get("use_legacy", False)
        self._process_batch_with_progress(folder_structure, output_folder, use_legacy, manifest_path)
        
    
    def _open_batch_metadata_gui(self, manifest_path):
        """Abre la GUI de asignación de metadata para el batch."""
        try:
            from gui_batch_metadata import BatchMetadataGUI
            self.destroy()
            app = BatchMetadataGUI(manifest_path)
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la GUI de metadata:\n{e}")
    
    # ========== MÉTODOS PARA AUDITORÍA Y CORRECCIÓN ==========
    
    def _has_videos_needing_correction(self):
        """Detecta si existen videos marcados para corrección."""
        try:
            # Buscar en todas las sesiones
            sessions_dir = os.path.join(self.config_data["General"]["output_folder"], "sessions")
            if not os.path.exists(sessions_dir):
                return False
            
            for item in os.listdir(sessions_dir):
                metadata_path = os.path.join(sessions_dir, item, "metadata.json")
                if os.path.exists(metadata_path):
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        videos = json.load(f)
                    
                    # Buscar videos que requieren corrección
                    for v in videos:
                        audit = v.get("audit", {})
                        if audit.get("requires_retagging", False) and not audit.get("retagged", False):
                            return True
            
            return False
        except Exception:
            return False
    
    def open_correction_tagger(self):
        """Abre el tagger en modo corrección con videos marcados para re-etiquetado."""
        try:
            # Buscar sesión con videos para corregir
            sessions_dir = os.path.join(self.config_data["General"]["output_folder"], "sessions")
            
            if not os.path.exists(sessions_dir):
                messagebox.showerror("Error", "No se encontraron sesiones.")
                return
            
            # Encontrar última sesión con correcciones pendientes
            correction_session = None
            max_mtime = 0
            
            for item in os.listdir(sessions_dir):
                metadata_path = os.path.join(sessions_dir, item, "metadata.json")
                if os.path.exists(metadata_path):
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        videos = json.load(f)
                    
                    # Verificar si tiene videos para corregir
                    has_corrections = any(
                        v.get("audit", {}).get("requires_retagging", False) and 
                        not v.get("audit", {}).get("retagged", False)
                        for v in videos
                    )
                    
                    if has_corrections:
                        mtime = os.path.getmtime(metadata_path)
                        if mtime > max_mtime:
                            max_mtime = mtime
                            correction_session = {
                                "metadata_path": metadata_path,
                                "session_id": item
                            }
            
            if not correction_session:
                messagebox.showinfo(
                    "Sin correcciones",
                    "No hay videos marcados para corrección."
                )
                return
            
            # Abrir tagger en modo corrección
            self.destroy()
            from gui_tagger import DynamicTagger
            app = DynamicTagger(
                metadata_path=correction_session["metadata_path"],
                session_id=correction_session["session_id"],
                correction_mode=True
            )
            app.mainloop()
            
        except Exception as e:
            import traceback
            messagebox.showerror(
                "Error",
                f"No se pudo abrir el modo de corrección:\n{e}\n\n{traceback.format_exc()}"
            )


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
