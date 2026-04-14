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
from export_utils import export_to_excel
from export_utils import export_to_csv


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

    Button(btn_frame, text="Abrir", command=confirmar, bg="#4CAF50", fg="white", width=10).pack(side="left", padx=5)
    Button(btn_frame, text="Cancelar", command=cancelar, width=10).pack(side="left", padx=5)

    parent.wait_window(dialog)
    return selected[0]


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
        self.build_layout()

    def build_layout(self):
        labels = self.config_data.get('Labels', {})

        main_frame = tk.Frame(self, bg="#e0e0e0")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Frame para botones a la izquierda ---
        button_frame = tk.Frame(main_frame, bg="#d0d0d0", relief="raised", bd=2)
        button_frame.pack(side="left", fill="y", padx=(0, 10), pady=5)

        # Botón reanudar (visible si hay sesiones)
        if self.all_sessions:
            n_incomplete = sum(1 for s in self.all_sessions if not s["completed"])
            if n_incomplete > 0:
                btn_text = f"Reanudar sesión ({n_incomplete} pendiente{'s' if n_incomplete != 1 else ''})"
            else:
                btn_text = "Revisar sesión"
            tk.Button(button_frame, text=btn_text, width=20, height=2,
                      command=self.resume_session, bg="#ff5722", fg="white").pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_etiquetar_videos', 'Etiquetar Videos'),
                  width=20, height=2, command=self.run_gui_inicial, bg="#4caf50", fg="white").pack(pady=5)

        tk.Button(button_frame, text="Análisis rápido", width=20, height=2,
                  command=self.run_analysis_gui, bg="#9c27b0", fg="white").pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_generar_excel', 'Generar Excel'),
                  width=20, height=2, command=self.run_excel_export, bg="#2196f3", fg="white").pack(pady=5)

        tk.Button(button_frame, text="Exportación rápida", width=20, height=2,
                  command=self.run_quick_export, bg="#00bcd4", fg="white").pack(pady=5)

        tk.Button(button_frame, text=labels.get('btn_rename_sort', 'Sort & Rename'),
                  width=20, height=2, command=self.run_sort_rename, bg="#ff9800", fg="white").pack(pady=5)

        tk.Button(button_frame, text="Incrustar Metadatos", width=20, height=2,
                  command=self.run_embed_metadata, bg="#607d8b", fg="white").pack(pady=5)

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

        # --- LOGO FLOTANTE (Reemplaza todo el bloque anterior del logo) ---
        try:
            from PIL import Image, ImageTk
            
            logo_path = os.path.join(os.path.dirname(__file__), "caicat_transparente.png")
            
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                # Ajusta tamaño aquí: (ancho, alto). 
                # Puedes cambiar estos números a tu gusto.
                logo_img = logo_img.resize((500, 200), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_img)
                
                # bg="#e0e0e0" iguala el fondo de la ventana para que la transparencia sea visual
                self.logo_label = tk.Label(self, image=self.logo_photo, bg="#e0e0e0")
                
                # 🔹 POSICIÓN FLOTANTE:
                # relx=0.5  → Centro horizontal
                # rely=0.03 → Muy arriba (ajusta este valor: 0.02 más arriba, 0.05 más abajo)
                # anchor="n" → El ancla es el borde superior del logo
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

        help_btn = tk.Button(setup_frame, text="?", width=3, height=1, command=self.show_help,
                             bg="#2196f3", fg="white", font=("Arial", 14, "bold"))
        help_btn.pack(side="right", padx=(0, 10))

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
        gui_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "gui_inicial.py")
        try:
            subprocess.Popen([sys.executable, gui_path])
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir GUI Inicial:\n{e}")

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

    def run_quick_export(self):
        try:
            path = export_to_excel()
            if path:
                messagebox.showinfo("Exportación", f"Excel generado:\n{path}")
            else:
                messagebox.showwarning("Exportación", "No se generó ningún archivo")
        except Exception as e:
            messagebox.showerror("Error", f"Error exportando:\n{e}")

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


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
