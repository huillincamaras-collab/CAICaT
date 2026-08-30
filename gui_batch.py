"""
gui_batch.py - Interfaz gráfica para procesamiento batch interactivo.

Flujo:
1. Seleccionar carpeta
2. Conteo rápido (videos/fotos)
3. Branching según contenido:
   - Solo videos → diálogo simple
   - Solo fotos → diálogo de ráfagas (auto/manual)
   - Mixto → diálogo unificado con 3 opciones
4. Procesar en background con ventana de progreso
5. Abrir BatchMetadataGUI al terminar

Diseño:
- Mantiene main.py limpio (solo 3 líneas de llamada)
- No depende de gui_inicial.py
- Usa procesamiento_batch.py para la lógica pura
"""
import os
import json
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from datetime import datetime


# =============================================================================
# ENTRY POINT PRINCIPAL
# =============================================================================
def run_batch_interactive(parent):
    """
    Entry point principal para el batch interactivo.
    Llamado desde main.py con: run_batch_interactive(self)
    
    Args:
        parent: Ventana padre (MainApp)
    """
    # 1. Seleccionar carpeta
    folder = filedialog.askdirectory(
        parent=parent,
        title="Seleccionar carpeta con videos/fotos (puede contener subcarpetas)"
    )
    if not folder:
        return
    
    # 2. Conteo rápido
    try:
        from procesamiento_batch import scan_batch_folder
        folder_structure = scan_batch_folder(folder)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo escanear la carpeta:\n{e}", parent=parent)
        return
    
    if not folder_structure:
        messagebox.showwarning(
            "Sin contenido",
            "No se encontraron videos ni fotos en la carpeta seleccionada.",
            parent=parent
        )
        return
    
    # Calcular totales
    total_videos = sum(info["video_count"] for info in folder_structure.values())
    total_photos = sum(info["photo_count"] for info in folder_structure.values())
    total_folders = len(folder_structure)
    
    counts = {
        "videos": total_videos,
        "photos": total_photos,
        "folders": total_folders
    }
    
    # 3. Branching según contenido
    if total_videos > 0 and total_photos == 0:
        _show_dialog_only_videos(parent, folder, folder_structure, counts)
    elif total_videos == 0 and total_photos > 0:
        _show_dialog_only_photos(parent, folder, folder_structure, counts)
    else:
        _show_dialog_mixed(parent, folder, folder_structure, counts)


# =============================================================================
# DIÁLOGO: SOLO VIDEOS
# =============================================================================
def _show_dialog_only_videos(parent, folder, folder_structure, counts):
    """Diálogo simple para procesar solo videos."""
    dialog = tk.Toplevel(parent)
    dialog.title("📦 Procesamiento Batch - Solo Videos")
    dialog.geometry("450x250")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.focus_set()
    _center_dialog(dialog, 450, 250)
    
    # Info
    info_frame = tk.LabelFrame(dialog, text="Contenido detectado",
                               font=("Arial", 10, "bold"), padx=15, pady=10)
    info_frame.pack(fill="x", padx=20, pady=(15, 10))
    
    tk.Label(info_frame, text=f"🎥 Videos: {counts['videos']}",
             font=("Arial", 11)).pack(anchor="w", pady=3)
    tk.Label(info_frame, text=f"📂 Carpetas: {counts['folders']}",
             font=("Arial", 11)).pack(anchor="w", pady=3)
    
    # Modo
    mode_frame = tk.Frame(dialog)
    mode_frame.pack(pady=10)
    
    legacy_var = tk.BooleanVar(value=False)
    tk.Checkbutton(mode_frame, text="🐌 Modo Legacy (PCs lentas)",
                   variable=legacy_var, font=("Arial", 10)).pack(anchor="w")
    
    # Botones
    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=15)
    
    def aceptar():
        dialog.destroy()
        _start_batch(parent, folder, folder_structure,
                     process_mode="videos",
                     photos_per_video=0,
                     burst_size=3,
                     use_legacy=legacy_var.get())
    
    tk.Button(btn_frame, text="✅ Procesar", command=aceptar,
              bg="#4CAF50", fg="white", width=12,
              font=("Arial", 10, "bold")).pack(side="left", padx=10)
    tk.Button(btn_frame, text="❌ Cancelar", command=dialog.destroy,
              width=12).pack(side="left", padx=10)


# =============================================================================
# DIÁLOGO: SOLO FOTOS
# =============================================================================
def _show_dialog_only_photos(parent, folder, folder_structure, counts):
    """Diálogo para procesar solo fotos (ráfagas)."""
    dialog = tk.Toplevel(parent)
    dialog.title("📦 Procesamiento Batch - Solo Fotos")
    dialog.geometry("480x350")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.focus_set()
    _center_dialog(dialog, 480, 350)
    
    # Info
    info_frame = tk.LabelFrame(dialog, text="Contenido detectado",
                               font=("Arial", 10, "bold"), padx=15, pady=10)
    info_frame.pack(fill="x", padx=20, pady=(15, 10))
    
    tk.Label(info_frame, text=f"📷 Fotos: {counts['photos']}",
             font=("Arial", 11)).pack(anchor="w", pady=3)
    tk.Label(info_frame, text=f"📂 Carpetas: {counts['folders']}",
             font=("Arial", 11)).pack(anchor="w", pady=3)
    
    # Configuración de ráfagas
    burst_frame = tk.LabelFrame(dialog, text="Tamaño de ráfaga",
                                font=("Arial", 10, "bold"), padx=15, pady=10)
    burst_frame.pack(fill="x", padx=20, pady=5)
    
    burst_mode_var = tk.StringVar(value="auto")
    
    # Estimación automática
    estimated = _estimate_burst_size(folder_structure)
    
    tk.Radiobutton(burst_frame, text=f"🔍 Automático (estimado: {estimated} fotos/ráfaga)",
                   variable=burst_mode_var, value="auto",
                   font=("Arial", 10)).pack(anchor="w", pady=2)
    
    manual_frame = tk.Frame(burst_frame)
    manual_frame.pack(anchor="w", pady=2)
    tk.Radiobutton(manual_frame, text="✏️ Manual:",
                   variable=burst_mode_var, value="manual",
                   font=("Arial", 10)).pack(side="left")
    burst_spin = tk.Spinbox(manual_frame, from_=1, to=50, width=5,
                            font=("Arial", 10, "bold"))
    burst_spin.delete(0, "end")
    burst_spin.insert(0, str(estimated))
    burst_spin.pack(side="left", padx=5)
    tk.Label(manual_frame, text="fotos por ráfaga",
             font=("Arial", 9), fg="gray").pack(side="left")
    
    # Preview de conteo
    preview_label = tk.Label(burst_frame, text="", font=("Arial", 9), fg="#1976d2")
    preview_label.pack(anchor="w", pady=(5, 0))
    
    def update_preview(*args):
        mode = burst_mode_var.get()
        if mode == "auto":
            bs = estimated
        else:
            try:
                bs = int(burst_spin.get())
            except Exception:
                bs = estimated
        if bs < 1:
            bs = 1
        n_bursts = (counts["photos"] + bs - 1) // bs
        preview_label.config(text=f"→ {counts['photos']} fotos → ~{n_bursts} ráfagas")
    
    burst_mode_var.trace_add("write", update_preview)
    update_preview()
    
    # Modo legacy
    mode_frame = tk.Frame(dialog)
    mode_frame.pack(pady=5)
    
    legacy_var = tk.BooleanVar(value=False)
    tk.Checkbutton(mode_frame, text="🐌 Modo Legacy (PCs lentas)",
                   variable=legacy_var, font=("Arial", 10)).pack(anchor="w")
    
    # Botones
    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=10)
    
    def aceptar():
        mode = burst_mode_var.get()
        if mode == "auto":
            bs = estimated
        else:
            try:
                bs = int(burst_spin.get())
            except Exception:
                bs = estimated
        if bs < 1:
            bs = 1
        dialog.destroy()
        _start_batch(parent, folder, folder_structure,
                     process_mode="photos",
                     photos_per_video=0,
                     burst_size=bs,
                     use_legacy=legacy_var.get())
    
    tk.Button(btn_frame, text="✅ Procesar", command=aceptar,
              bg="#4CAF50", fg="white", width=12,
              font=("Arial", 10, "bold")).pack(side="left", padx=10)
    tk.Button(btn_frame, text="❌ Cancelar", command=dialog.destroy,
              width=12).pack(side="left", padx=10)


# =============================================================================
# DIÁLOGO: MIXTO (VIDEOS + FOTOS)
# =============================================================================
def _show_dialog_mixed(parent, folder, folder_structure, counts):
    """Diálogo unificado para carpetas con videos Y fotos."""
    dialog = tk.Toplevel(parent)
    dialog.title("📦 Procesamiento Batch - Contenido Mixto")
    dialog.geometry("520x480")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.focus_set()
    _center_dialog(dialog, 520, 480)
    
    # Info
    info_frame = tk.LabelFrame(dialog, text="Contenido detectado",
                               font=("Arial", 10, "bold"), padx=15, pady=10)
    info_frame.pack(fill="x", padx=20, pady=(15, 5))
    
    tk.Label(info_frame, text=f"🎥 Videos: {counts['videos']}",
             font=("Arial", 11)).pack(anchor="w", pady=2)
    tk.Label(info_frame, text=f"📷 Fotos: {counts['photos']}",
             font=("Arial", 11)).pack(anchor="w", pady=2)
    tk.Label(info_frame, text=f"📂 Carpetas: {counts['folders']}",
             font=("Arial", 11)).pack(anchor="w", pady=2)
    
    # Opción de procesamiento
    tk.Label(dialog, text="¿Qué desea procesar?",
             font=("Arial", 11, "bold")).pack(pady=(10, 5))
    
    process_mode_var = tk.StringVar(value="both")
    
    tk.Radiobutton(dialog, text="🎥 Solo videos",
                   variable=process_mode_var, value="videos",
                   font=("Arial", 10)).pack(anchor="w", padx=40, pady=2)
    tk.Radiobutton(dialog, text="📷 Solo fotos (ráfagas)",
                   variable=process_mode_var, value="photos",
                   font=("Arial", 10)).pack(anchor="w", padx=40, pady=2)
    tk.Radiobutton(dialog, text="🔄 Ambos (videos + fotos)",
                   variable=process_mode_var, value="both",
                   font=("Arial", 10)).pack(anchor="w", padx=40, pady=2)
    
    # Controles dinámicos
    controls_frame = tk.LabelFrame(dialog, text="Parámetros",
                                   font=("Arial", 10, "bold"), padx=15, pady=8)
    controls_frame.pack(fill="x", padx=20, pady=5)
    
    # Spinbox fotos por video (solo para "both")
    ppv_frame = tk.Frame(controls_frame)
    tk.Label(ppv_frame, text="Fotos a asociar por video:",
             font=("Arial", 10)).pack(side="left")
    ppv_spin = tk.Spinbox(ppv_frame, from_=0, to=10, width=5, font=("Arial", 10))
    ppv_spin.delete(0, "end")
    ppv_spin.insert(0, "1")
    ppv_spin.pack(side="left", padx=5)
    
    # Spinbox ráfaga (para "photos" y "both")
    burst_frame = tk.Frame(controls_frame)
    burst_mode_var = tk.StringVar(value="auto")
    estimated = _estimate_burst_size(folder_structure)
    
    tk.Label(burst_frame, text="Fotos por ráfaga:",
             font=("Arial", 10)).pack(side="left")
    tk.Radiobutton(burst_frame, text=f"Auto ({estimated})",
                   variable=burst_mode_var, value="auto",
                   font=("Arial", 9)).pack(side="left", padx=5)
    tk.Radiobutton(burst_frame, text="Manual:",
                   variable=burst_mode_var, value="manual",
                   font=("Arial", 9)).pack(side="left")
    burst_spin = tk.Spinbox(burst_frame, from_=1, to=50, width=5,
                            font=("Arial", 10))
    burst_spin.delete(0, "end")
    burst_spin.insert(0, str(estimated))
    burst_spin.pack(side="left", padx=5)
    
    # Preview
    preview_label = tk.Label(controls_frame, text="", font=("Arial", 9), fg="#1976d2")
    preview_label.pack(anchor="w", pady=(5, 0))
    
    def update_controls(*args):
        mode = process_mode_var.get()
        if mode == "videos":
            ppv_frame.pack_forget()
            burst_frame.pack_forget()
            preview_label.config(text="→ Se procesarán solo los videos")
        elif mode == "photos":
            ppv_frame.pack_forget()
            burst_frame.pack(anchor="w", pady=3, fill="x")
            bs = _get_burst_size(burst_mode_var, burst_spin, estimated)
            n_bursts = (counts["photos"] + bs - 1) // bs
            preview_label.config(text=f"→ {counts['photos']} fotos → ~{n_bursts} ráfagas")
        else:  # both
            ppv_frame.pack(anchor="w", pady=3, fill="x")
            burst_frame.pack(anchor="w", pady=3, fill="x")
            bs = _get_burst_size(burst_mode_var, burst_spin, estimated)
            n_bursts = (counts["photos"] + bs - 1) // bs
            preview_label.config(
                text=f"→ {counts['videos']} videos + {counts['photos']} fotos (~{n_bursts} ráfagas)"
            )
    
    process_mode_var.trace_add("write", update_controls)
    burst_mode_var.trace_add("write", update_controls)
    update_controls()
    
    # Modo legacy
    mode_frame = tk.Frame(dialog)
    mode_frame.pack(pady=5)
    
    legacy_var = tk.BooleanVar(value=False)
    tk.Checkbutton(mode_frame, text="🐌 Modo Legacy (PCs lentas)",
                   variable=legacy_var, font=("Arial", 10)).pack(anchor="w")
    
    # Botones
    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=10)
    
    def aceptar():
        mode = process_mode_var.get()
        ppv = 0
        bs = _get_burst_size(burst_mode_var, burst_spin, estimated)
        
        if mode == "both":
            try:
                ppv = int(ppv_spin.get())
            except Exception:
                ppv = 1
        
        dialog.destroy()
        _start_batch(parent, folder, folder_structure,
                     process_mode=mode,
                     photos_per_video=ppv,
                     burst_size=bs,
                     use_legacy=legacy_var.get())
    
    tk.Button(btn_frame, text="✅ Procesar", command=aceptar,
              bg="#4CAF50", fg="white", width=12,
              font=("Arial", 10, "bold")).pack(side="left", padx=10)
    tk.Button(btn_frame, text="❌ Cancelar", command=dialog.destroy,
              width=12).pack(side="left", padx=10)


# =============================================================================
# VENTANA DE PROGRESO Y PROCESAMIENTO EN BACKGROUND
# =============================================================================
def _start_batch(parent, folder, folder_structure, process_mode,
                 photos_per_video, burst_size, use_legacy):
    """Inicia el procesamiento batch en un thread con ventana de progreso."""
    from procesamiento_batch import (
        create_batch_manifest, process_batch_videos
    )
    from config_utils import generate_session_id, load_config
    
    config = load_config()
    output_folder = config["General"]["output_folder"]
    
    # Crear manifest
    try:
        batch_id = generate_session_id(config)
        manifest_path = create_batch_manifest(
            batch_id, folder_structure, output_folder,
            use_legacy=use_legacy, root_folder=folder
        )
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo crear el manifest:\n{e}", parent=parent)
        return
    
    # Crear ventana de progreso
    progress_window = tk.Toplevel(parent)
    progress_window.title("📦 Procesando lote...")
    progress_window.geometry("550x280")
    progress_window.transient(parent)
    progress_window.grab_set()
    progress_window.resizable(False, False)
    _center_dialog(progress_window, 550, 280)
    progress_window.attributes('-topmost', True)
    
    main_frame = tk.Frame(progress_window, bg="#f0f0f0", padx=20, pady=15)
    main_frame.pack(fill="both", expand=True)
    
    title_label = tk.Label(main_frame,
                           text="📦 Procesando lote (no cierres esta ventana)",
                           font=("Arial", 12, "bold"), bg="#f0f0f0")
    title_label.pack(pady=(0, 10))
    
    current_label = tk.Label(main_frame, text="Iniciando...",
                             font=("Arial", 10), bg="#f0f0f0", wraplength=500)
    current_label.pack(pady=5)
    
    progress_bar = ttk.Progressbar(main_frame, length=500, mode='determinate',
                                   maximum=len(folder_structure))
    progress_bar.pack(pady=10)
    
    stats_label = tk.Label(main_frame, text="",
                           font=("Arial", 9), bg="#f0f0f0", fg="gray")
    stats_label.pack()
    
    error_label = tk.Label(main_frame, text="",
                           font=("Arial", 9), bg="#f0f0f0", fg="#d32f2f",
                           wraplength=500)
    error_label.pack(pady=5)
    
    start_time = time.time()
    errors_count = [0]
    
    def update_progress(folder_key, current, total, phase="processing"):
        """Callback de progreso llamado desde process_batch_videos."""
        try:
            elapsed = time.time() - start_time
            folder_idx = list(folder_structure.keys()).index(folder_key) + 1 if folder_key in folder_structure else 0
            total_folders = len(folder_structure)
            
            phase_text = {
                "starting": "🔄 Iniciando...",
                "processing": f"🎥 Procesando archivo {current}/{total}...",
                "completed": "✅ Completada"
            }.get(phase, phase)
            
            current_label.config(
                text=f"Carpeta {folder_idx}/{total_folders}: {folder_key}\n{phase_text}"
            )
            
            if phase == "completed":
                progress_bar['value'] = folder_idx
                pct = int((folder_idx / total_folders) * 100)
                avg_time = elapsed / folder_idx if folder_idx > 0 else 0
                remaining = avg_time * (total_folders - folder_idx)
                rem_str = f"{int(remaining // 60)}m {int(remaining % 60)}s" if remaining > 60 else f"{int(remaining)}s"
                stats_label.config(
                    text=f"{folder_idx}/{total_folders} carpetas ({pct}%) - "
                         f"Tiempo restante: ~{rem_str}"
                )
            
            progress_window.update()
        except Exception:
            pass
    
    def process_thread():
        """Thread de procesamiento."""
        try:
            manifest = process_batch_videos(
                folder_structure, output_folder, manifest_path,
                use_legacy=use_legacy,
                progress_callback=update_progress
            )
            
            # Verificar errores
            error_folders = sum(
                1 for f in manifest.get("folders", {}).values()
                if f.get("status") == "error"
            )
            
            progress_window.attributes('-topmost', False)
            
            if error_folders > 0:
                current_label.config(
                    text=f"⚠️ Procesamiento completado con {error_folders} errores",
                    fg="#d32f2f"
                )
                error_label.config(
                    text="Revisa la carpeta de salida para más detalles."
                )
            else:
                current_label.config(
                    text="✅ ¡Procesamiento completado exitosamente!",
                    fg="#2e7d32", font=("Arial", 11, "bold")
                )
            
            stats_label.config(text="Abriendo asignación de metadata...")
            progress_window.update()
            
            # Esperar 2 segundos y abrir BatchMetadataGUI
            time.sleep(2)
            progress_window.destroy()
            
            # Abrir GUI de metadata
            try:
                from gui_batch_metadata import BatchMetadataGUI
                parent.destroy()
                app = BatchMetadataGUI(manifest_path)
                app.mainloop()
            except Exception as e:
                messagebox.showerror(
                    "Error",
                    f"Procesamiento completado pero no se pudo abrir "
                    f"la GUI de metadata:\n{e}\n\n"
                    f"Manifest guardado en:\n{manifest_path}",
                    parent=parent
                )
        
        except Exception as e:
            import traceback
            progress_window.attributes('-topmost', False)
            progress_window.destroy()
            messagebox.showerror(
                "Error",
                f"Error durante el procesamiento:\n{e}\n\n{traceback.format_exc()}",
                parent=parent
            )
    
    # Iniciar thread
    threading.Thread(target=process_thread, daemon=True).start()


# =============================================================================
# CONTINUAR LOTE (re-escaneo robusto)
# =============================================================================
def continue_batch_interactive(parent):
    """
    Continúa un lote pendiente re-escaneando las carpetas originales.
    Llamado desde main.py cuando se presiona "Continuar Lote".
    """
    from config_utils import load_config
    
    config = load_config()
    output_folder = config["General"]["output_folder"]
    batch_folder = os.path.join(output_folder, "batch")
    manifest_path = os.path.join(batch_folder, "batch_manifest.json")
    
    if not os.path.exists(manifest_path):
        messagebox.showerror("Error", "No se encontró un lote pendiente.", parent=parent)
        return
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo leer el manifest:\n{e}", parent=parent)
        return
    
    status = manifest.get("status", "")
    
    # Caso 1: Ya procesado, necesita metadata
    if status in ("pending_metadata_assignment", "ready_for_tagging"):
        try:
            from gui_batch_metadata import BatchMetadataGUI
            parent.destroy()
            app = BatchMetadataGUI(manifest_path)
            app.mainloop()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la GUI de metadata:\n{e}",
                                 parent=parent)
        return
    
    # Caso 2: Necesita reanudar procesamiento
    if status in ("pending_processing", "processing", "completed_with_errors"):
        # Re-escanear carpetas pendientes
        from procesamiento_batch import scan_batch_folder
        
        pending_folders = {}
        for folder_key, folder_data in manifest.get("folders", {}).items():
            if folder_data.get("status") in ("pending", "error"):
                original_path = folder_data.get("original_path", "")
                if os.path.exists(original_path):
                    # Re-escanear esta carpeta
                    rescan = scan_batch_folder(original_path)
                    if rescan:
                        pending_folders.update(rescan)
                else:
                    print(f"[Batch] ⚠️ Carpeta no encontrada: {original_path}")
        
        if not pending_folders:
            messagebox.showinfo(
                "Sin pendientes",
                "No hay carpetas pendientes para procesar,\n"
                "o las carpetas originales ya no están disponibles.",
                parent=parent
            )
            return
        
        use_legacy = manifest.get("use_legacy", False)
        
        # Confirmar
        msg = (f"Se encontraron {len(pending_folders)} carpetas pendientes.\n"
               f"¿Reanudar procesamiento?")
        if not messagebox.askyesno("Continuar Lote", msg, parent=parent):
            return
        
        _start_batch(parent, manifest.get("root_folder", ""), pending_folders,
                     process_mode="both",
                     photos_per_video=1,
                     burst_size=manifest.get("burst_size", 3),
                     use_legacy=use_legacy)
        return
    
    # Caso 3: Estado desconocido
    messagebox.showinfo("Info", f"Estado del lote: {status}", parent=parent)


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================
def _center_dialog(dialog, width, height):
    """Centra un diálogo en la pantalla."""
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def _estimate_burst_size(folder_structure):
    """
    Estima el tamaño de ráfaga basándose en gaps de tiempo.
    Reglas:
    - 1 foto → 1 (no es ráfaga)
    - 2 fotos → 2 si gap < 2s, sino 1
    - 3+ fotos → agrupar por gaps de 2s y promediar
    """
    try:
        from procesamiento import obtener_timestamp_foto
        
        # Recopilar todas las fotos con timestamps (por subcarpeta)
        all_gaps = []
        
        for folder_key, folder_data in folder_structure.items():
            photos = folder_data.get("photos", [])
            if len(photos) < 2:
                continue
            
            # Obtener timestamps
            photos_with_ts = []
            for p in photos:
                try:
                    ts = obtener_timestamp_foto(p)
                    photos_with_ts.append(ts)
                except Exception:
                    pass
            
            if len(photos_with_ts) < 2:
                continue
            
            photos_with_ts.sort()
            
            # Calcular gaps
            for i in range(1, len(photos_with_ts)):
                gap = photos_with_ts[i] - photos_with_ts[i-1]
                all_gaps.append(gap)
        
        if not all_gaps:
            return 3  # Default
        
        # Contar ráfagas usando umbral de 2s
        umbral = 2.0
        n_rafagas = 1
        total_fotos_con_gaps = len(all_gaps) + 1
        
        for gap in all_gaps:
            if gap > umbral:
                n_rafagas += 1
        
        avg = max(1, round(total_fotos_con_gaps / n_rafagas))
        return min(avg, 20)  # Cap razonable
    
    except Exception:
        return 3  # Default seguro


def _get_burst_size(burst_mode_var, burst_spin, estimated):
    """Obtiene el tamaño de ráfaga según el modo seleccionado."""
    if burst_mode_var.get() == "auto":
        return estimated
    try:
        bs = int(burst_spin.get())
        return max(1, bs)
    except Exception:
        return estimated