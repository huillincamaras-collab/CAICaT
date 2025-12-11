import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from procesamiento import (
    escanear_videos, wrapper, metadata_lock,
    obtener_fotos_con_timestamp, agrupar_en_rafagas, procesar_todas_las_rafagas
)
from gui_tagger import DynamicTagger
from config_utils import generate_session_id, load_config



class GUIInicial(tk.Tk):
    def __init__(self):
        super().__init__()

        # --- Cargar configuración ---
        self.config_data = load_config()
        gui_cfg = self.config_data.get("GUI_Inicial", {})

        # --- Parámetros de GUI ---
        self.title(gui_cfg.get("title", "Configuración inicial - Cámaras Trampa"))
        self.geometry(gui_cfg.get("geometry", "400x400"))
        colors = gui_cfg.get("colors", {})
        fonts = gui_cfg.get("fonts", {})
        labels = gui_cfg.get("labels", {})
        buttons = gui_cfg.get("buttons", {})

        self.configure(bg=colors.get("bg", "#f0f0f0"))

        # --- Crear widgets ---
        # Toggle para Modo Camtrap DB
        self.camtrap_mode_var = tk.BooleanVar(value=False) # <-- Variable para el toggle
        self.toggle_camtrap_btn = tk.Button(
            self,
            text="Modo Estándar",
            command=self._toggle_camtrap_mode,
            bg="#e0e0e0", # Gris claro por defecto
            fg="black",
            font=tuple(fonts.get("default", ("Arial", 10)))
        )
        self.toggle_camtrap_btn.pack(pady=(5, 10))

        # Carpeta de videos
        tk.Label(self, text=labels.get("input_folder", "Carpeta de videos:"), bg=colors.get("bg", "#f0f0f0"),
                 font=tuple(fonts.get("default", ("Arial", 10)))).pack(pady=5)
        self.entry_input = tk.Entry(self, width=50)
        self.entry_input.pack()
        tk.Button(
            self,
            text=buttons.get("browse", "Examinar"),
            command=self.select_input,
            bg=colors.get("button_bg", "#4CAF50"),
            fg=colors.get("button_fg", "white")
        ).pack(pady=5)

        # Campos de metadatos
        self._create_label_entry(labels.get("site", "Sitio:"), colors, fonts)
        self.entry_site = self._last_entry

        self._create_label_entry(labels.get("subsite", "Subsitio:"), colors, fonts)
        self.entry_subsite = self._last_entry

        self._create_label_entry(labels.get("camera", "Cámara:"), colors, fonts)
        self.entry_camera = self._last_entry

        self._create_label_entry(labels.get("operator", "Operador:"), colors, fonts)
        self.entry_operator = self._last_entry

        # Botón iniciar
        tk.Button(
            self,
            text=buttons.get("start", "Iniciar"),
            command=self.start,
            bg=colors.get("button_bg", "#4CAF50"),
            fg=colors.get("button_fg", "white")
        ).pack(pady=10)

        # --- Variables internas ---
        self.session_id = generate_session_id(self.config_data)
        self.input_folder = ""
        self.metadata_path = ""  # ←←← ahora será dentro de sessions/{session_id}/
        self.metadata_list = []

    # -------------------------------
    # Crear etiqueta y campo de texto
    # -------------------------------
    def _create_label_entry(self, text, colors, fonts):
        tk.Label(self, text=text, bg=colors.get("bg", "#f0f0f0"),
                 font=tuple(fonts.get("default", ("Arial", 10)))).pack(pady=2)
        entry = tk.Entry(self, width=30)
        entry.pack()
        self._last_entry = entry

    # -------------------------------
    # Selección de carpeta de entrada
    # -------------------------------
    def select_input(self):
        folder = filedialog.askdirectory(parent=self, title="Seleccione carpeta de entrada")
        if folder:
            self.input_folder = folder
            self.entry_input.delete(0, tk.END)
            self.entry_input.insert(0, folder)
            threading.Thread(target=self.start_processing, daemon=True).start()

    # -------------------------------
    # Procesamiento en segundo plano
    # -------------------------------
    def start_processing(self):
        output_folder = self.config_data["General"]["output_folder"]
        
        # Crear carpeta de sesión
        session_folder = os.path.join(output_folder, "sessions", self.session_id)
        os.makedirs(session_folder, exist_ok=True)
        self.metadata_path = os.path.join(session_folder, "metadata.json")

        # Escanear como videos (incluye modo híbrido)
        self.metadata_list = escanear_videos(self.input_folder, output_folder)
        self._save_metadata_temporal()

        # ←←← NUEVO: detectar si es modo fotos puras →→→
        if not self.metadata_list:
            # Verificar si hay fotos
            img_exts = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
            has_photos = any(
                os.path.isfile(os.path.join(self.input_folder, f)) and
                os.path.splitext(f)[1] in img_exts
                for f in os.listdir(self.input_folder)
            )
            if has_photos:
                # Guardar metadatos vacíos temporalmente
                self.metadata_list = []
                self._save_metadata_temporal()
                # Lanzar detección en segundo plano
                threading.Thread(
                    target=self._detectar_fotos_puras_bg,
                    args=(output_folder,),
                    daemon=True
                ).start()
                return
        # →→→ FIN NUEVO

        # Procesar videos (igual que antes)
        def process_first_videos():
            first_n = min(3, len(self.metadata_list))
            for i in range(first_n):
                res = wrapper((self.metadata_list[i], output_folder))
                self.metadata_list[i] = res
                self._save_metadata_temporal()

            def process_rest():
                from multiprocessing import Pool, cpu_count
                rest = self.metadata_list[first_n:]
                if not rest:
                    return
                args_list = [(m, output_folder) for m in rest]
                num_proc = max(1, cpu_count() - 1)
                if num_proc > 1:
                    with Pool(num_proc) as pool:
                        for res in pool.imap_unordered(wrapper, args_list):
                            for idx, v in enumerate(self.metadata_list):
                                if v["video_path"] == res["video_path"]:
                                    self.metadata_list[idx] = res
                            self._save_metadata_temporal()
                else:
                    for args in args_list:
                        res = wrapper(args)
                        for idx, v in enumerate(self.metadata_list):
                            if v["video_path"] == res["video_path"]:
                                self.metadata_list[idx] = res
                        self._save_metadata_temporal()

            threading.Thread(target=process_rest, daemon=True).start()

        threading.Thread(target=process_first_videos, daemon=True).start()

    def _detectar_fotos_puras_bg(self, output_folder):
        """Detecta ráfagas automáticamente y programa el diálogo en el hilo principal."""
        try:
            fotos_con_ts = obtener_fotos_con_timestamp(self.input_folder)
            if not fotos_con_ts:
                return
            
            # Agrupar con umbral por defecto (2.0 segundos)
            photo_groups = agrupar_en_rafagas(fotos_con_ts, umbral_seg=2.0)
            total = len(fotos_con_ts)
            n_grupos = len(photo_groups)
            avg_por_grupo = total / n_grupos if n_grupos else 1.0
            
            # Programar diálogo en hilo principal
            self.after(0, lambda: self._mostrar_dialogo_rafagas(fotos_con_ts, avg_por_grupo))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"No se pudieron analizar las fotos:\n{e}"))
    
    def _mostrar_dialogo_rafagas(self, fotos_con_ts, avg_estimado):
        """Muestra diálogo para ajustar 'fotos por activación'."""
        dialog = tk.Toplevel(self)
        dialog.title("Configuración de ráfagas fotográficas")
        dialog.geometry("400x260")
        dialog.transient(self)
        dialog.grab_set()
        dialog.focus_set()

        total = len(fotos_con_ts)
        n_estimado = max(1, round(total / max(1, avg_estimado)))
        
        tk.Label(dialog, text=f"Fotos detectadas: {total}", font=("Arial", 10)).pack(pady=5)
        tk.Label(dialog, text=f"Ráfagas estimadas: {n_estimado}", font=("Arial", 10)).pack(pady=2)
        tk.Label(dialog, text=f"Promedio por ráfaga: {avg_estimado:.1f}", font=("Arial", 10)).pack(pady=2)
        tk.Label(dialog, text="Ajuste el número de fotos por activación:", 
                font=("Arial", 10, "bold")).pack(pady=(10, 5))

        # ←←← IMPORTANTE: creamos el Spinbox y lo guardamos en una variable local →→→
        burst_spin = tk.Spinbox(dialog, from_=1, to=total, width=8)
        burst_spin.delete(0, "end")
        burst_spin.insert(0, str(max(1, round(avg_estimado))))
        burst_spin.pack(pady=5)

        tk.Label(dialog, text="Nota: se reagruparán las fotos\nsegún este valor.", 
                font=("Arial", 9), fg="gray").pack(pady=5)

        def confirmar():
            try:
                # ←←← LEEMOS DIRECTAMENTE DEL SPINBOX →→→
                burst_size = int(burst_spin.get())
            except:
                burst_size = 1
            if burst_size < 1:
                burst_size = 1
            
            total_fotos = len(fotos_con_ts)
            resto = total_fotos % burst_size
            if resto != 0:
                msg = f"Advertencia: {total_fotos} fotos no son múltiplo de {burst_size}.\n" \
                    f"La última ráfaga tendrá {resto} fotos.\n\n¿Desea continuar?"
                if not messagebox.askyesno("Ráfaga incompleta", msg, parent=dialog):
                    return

            dialog.destroy()  # ← cerramos el diálogo DESPUÉS de leer el valor
            
            threading.Thread(
                target=self._procesar_fotos_con_parametro,
                args=(fotos_con_ts, burst_size, self.config_data["General"]["output_folder"]),
                daemon=True
            ).start()

        def cancelar():
            dialog.destroy()

        tk.Button(dialog, text="Aceptar", command=confirmar, bg="#4CAF50", fg="white").pack(pady=5)
        tk.Button(dialog, text="Cancelar", command=cancelar).pack()   
    def _procesar_fotos_con_parametro(self, fotos_con_ts, burst_size, output_folder):
        """Procesa las fotos agrupando en bloques secuenciales de 'burst_size' fotos."""
        try:
            # ←←← AGRUPAMIENTO POR CONTEO (NO POR TIEMPO) →→→
            photo_groups = []
            for i in range(0, len(fotos_con_ts), burst_size):
                photo_groups.append(fotos_con_ts[i:i + burst_size])
            
            metadata_list = procesar_todas_las_rafagas(photo_groups, output_folder)
            self.after(0, lambda: self._actualizar_metadata_fotos(metadata_list))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Fallo al procesar fotos:\n{e}"))
            
    def _actualizar_metadata_fotos(self, metadata_list):
        """Actualiza la lista de metadatos con los resultados de fotos."""
        self.metadata_list = metadata_list
        self._save_metadata_temporal() 

    # -------------------------------
    # Abrir GUI de tagging
    # -------------------------------
    def start(self):
        if not self.input_folder:
            messagebox.showerror("Error", "Debe seleccionar la carpeta de videos.")
            return

        # <-- NUEVO: Verificar si estamos en modo Camtrap DB antes de continuar -->
        if self.camtrap_mode_var.get():
            # Cargar la configuración actual para verificar el flag
            current_config = load_config()
            # Acceder al flag camtrap_mode en la sección GUI_Tagger
            config_camtrap_mode = current_config.get("GUI_Tagger", {}).get("camtrap_mode", False)

            if not config_camtrap_mode:
                # El flag en config.ini es False, pero el toggle está activo
                # Mostrar diálogo
                from tkinter import messagebox
                msg = "Para usar el modo Camtrap DB, debe configurar los tags válidos en SETUP. ¿Desea abrir SETUP ahora?"
                result = messagebox.askyesno("Configuración requerida", msg, parent=self)
                if result: # Usuario dijo "Sí"
                    # Cerrar esta ventana y abrir setup
                    self.destroy()
                    try:
                        from gui_setup import SetupApp
                        SetupApp().mainloop()
                    except Exception as e:
                        print(f"Error abriendo setup: {e}")
                        # Si falla abrir setup, mostrar error y volver a main
                        try:
                            from main import MainApp
                            MainApp().mainloop()
                        except Exception:
                            pass
                else: # Usuario dijo "No"
                    # Volver al menú principal
                    self.destroy()
                    try:
                        from main import MainApp
                        MainApp().mainloop()
                    except Exception:
                        pass
                return # No continuar con el flujo normal si no se cumplió la condición

        # <-- FIN NUEVO -->

        site = self.entry_site.get()
        subsite = self.entry_subsite.get()
        camera = self.entry_camera.get()
        operator = self.entry_operator.get()

        for entry in self.metadata_list:
            entry["site"] = site
            entry["subsite"] = subsite
            entry["camera"] = camera
            entry["operator"] = operator
            entry["session_id"] = self.session_id
            # <-- AÑADIR ESTA LÍNEA -->
            # Registrar si la sesión se inició en modo Camtrap DB
            entry["camtrap_db_session"] = self.camtrap_mode_var.get()
            # <-- FIN AÑADIDO -->

        self._save_metadata_temporal()

        self.after(100, self.open_tagger_delayed)

    def open_tagger_delayed(self):
        self.destroy()
        app = DynamicTagger(metadata_path=self.metadata_path, session_id=self.session_id)
        app.mainloop()

    def _save_metadata_temporal(self):
        """Guarda self.metadata_list en self.metadata_path de forma segura."""
        with metadata_lock:
            import json
            with open(self.metadata_path, "w") as f:
                json.dump(self.metadata_list, f, indent=4)

    def _toggle_camtrap_mode(self):
        """Cambia el estado del toggle y actualiza la interfaz."""
        # Cambia el valor de la variable booleana
        self.camtrap_mode_var.set(not self.camtrap_mode_var.get())

        # Actualiza el texto y el color del botón
        if self.camtrap_mode_var.get():
            self.toggle_camtrap_btn.config(text="Modo Camtrap DB", bg="#4CAF50", fg="white")
        else:
            self.toggle_camtrap_btn.config(text="Modo Estándar", bg="#e0e0e0", fg="black")

        # <-- Opcional: Aquí puedes deshabilitar/habilitar otros campos si aplica -->
        # Por ahora, solo cambia el texto del botón.


if __name__ == "__main__":
    gui = GUIInicial()
    gui.mainloop()