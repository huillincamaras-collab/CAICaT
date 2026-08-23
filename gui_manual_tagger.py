"""
Manual Tagger for Failed Videos
Simplified tagging interface for videos that failed processing.
No frame canvas - uses external video player.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import sys
import subprocess
from config_utils import load_config, save_config


class ManualTaggerGUI(tk.Tk):
    def __init__(self, failed_videos, config_data, metadata_path):
        super().__init__()
        
        self.title("Etiquetado Manual - Videos Fallidos")
        self.geometry("700x600")
        
        self.failed_videos = failed_videos
        self.config_data = config_data
        self.metadata_path = metadata_path
        self.current_index = 0
        
        # Tag colors
        self.tag_active_bg = "#FFD700"  # Gold
        self.tag_inactive_bg = "#f0f0f0"  # Light gray
        
        # Load configurations
        gui_tagger_config = self.config_data.get("GUI_Tagger", {})
        self.species_tags = gui_tagger_config.get("species_tags", [])
        self.behavior_tags = gui_tagger_config.get("behavior_tags", [])
        self.custom_tag_labels = gui_tagger_config.get("custom_tag_labels", 
                                                        ["Custom 1", "Custom 2", "Custom 3", "Custom 4"])
        
        self.build_ui()
        self.load_current_video()
    
    def build_ui(self):
        """Build the simplified tagger interface"""
        
        # Header: Video info
        header_frame = tk.Frame(self, bg="#2c3e50", height=80)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        self.video_name_label = tk.Label(header_frame, text="", 
                                         font=("Arial", 12, "bold"),
                                         bg="#2c3e50", fg="white")
        self.video_name_label.pack(pady=5)
        
        self.error_label = tk.Label(header_frame, text="", 
                                    font=("Arial", 9),
                                    bg="#2c3e50", fg="#e74c3c")
        self.error_label.pack()
        
        self.video_count_label = tk.Label(header_frame, text="",
                                          font=("Arial", 9),
                                          bg="#2c3e50", fg="#95a5a6")
        self.video_count_label.pack()
        
        # Main content area
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Play Video Button (prominent)
        play_frame = tk.Frame(main_frame, bg="#27ae60", relief="raised", bd=2)
        play_frame.pack(fill="x", pady=(0, 20))
        
        tk.Button(play_frame, text="▶ Reproducir Video", 
                 command=self.play_video,
                 font=("Arial", 14, "bold"),
                 bg="#27ae60", fg="white",
                 height=2, relief="flat",
                 cursor="hand2").pack(fill="x", padx=5, pady=5)
        
        tk.Label(play_frame, text="(Abre con reproductor del sistema)",
                font=("Arial", 8), bg="#27ae60", fg="white").pack(pady=(0, 5))
        
        # Metadata fields
        metadata_frame = tk.LabelFrame(main_frame, text="Metadata", 
                                       font=("Arial", 10, "bold"))
        metadata_frame.pack(fill="x", pady=(0, 10))
        
        meta_grid = tk.Frame(metadata_frame)
        meta_grid.pack(padx=10, pady=10)
        
        tk.Label(meta_grid, text="Sitio:").grid(row=0, column=0, sticky="e", padx=5)
        self.site_entry = tk.Entry(meta_grid, width=15)
        self.site_entry.grid(row=0, column=1, padx=5)
        
        tk.Label(meta_grid, text="Subsitio:").grid(row=0, column=2, sticky="e", padx=5)
        self.subsite_entry = tk.Entry(meta_grid, width=15)
        self.subsite_entry.grid(row=0, column=3, padx=5)
        
        tk.Label(meta_grid, text="Cámara:").grid(row=1, column=0, sticky="e", padx=5)
        self.camera_entry = tk.Entry(meta_grid, width=15)
        self.camera_entry.grid(row=1, column=1, padx=5)
        
        tk.Label(meta_grid, text="Operador:").grid(row=1, column=2, sticky="e", padx=5)
        self.operator_entry = tk.Entry(meta_grid, width=15)
        self.operator_entry.grid(row=1, column=3, padx=5)
        
        # Species Tags
        species_frame = tk.LabelFrame(main_frame, text="Especies",
                                      font=("Arial", 10, "bold"))
        species_frame.pack(fill="x", pady=(0, 10))
        
        species_btn_frame = tk.Frame(species_frame)
        species_btn_frame.pack(padx=10, pady=10)
        
        self.species_buttons = {}
        for idx, tag in enumerate(self.species_tags):
            btn = tk.Button(species_btn_frame, text=tag,
                           bg=self.tag_inactive_bg,
                           width=12, height=2,
                           command=lambda t=tag: self.toggle_species(t))
            btn.grid(row=idx//4, column=idx%4, padx=3, pady=3)
            self.species_buttons[tag] = btn
        
        # Quantity
        qty_frame = tk.Frame(species_frame)
        qty_frame.pack(pady=(0, 10))
        tk.Label(qty_frame, text="Cantidad:").pack(side="left", padx=5)
        self.quantity_spinbox = tk.Spinbox(qty_frame, from_=1, to=99, width=5)
        self.quantity_spinbox.pack(side="left")
        
        # Behavior Tags
        behavior_frame = tk.LabelFrame(main_frame, text="Comportamientos",
                                       font=("Arial", 10, "bold"))
        behavior_frame.pack(fill="x", pady=(0, 10))
        
        behavior_btn_frame = tk.Frame(behavior_frame)
        behavior_btn_frame.pack(padx=10, pady=10)
        
        self.behavior_buttons = {}
        for idx, tag in enumerate(self.behavior_tags):
            btn = tk.Button(behavior_btn_frame, text=tag,
                           bg=self.tag_inactive_bg,
                           width=12, height=2,
                           command=lambda t=tag: self.toggle_behavior(t))
            btn.grid(row=idx//5, column=idx%5, padx=3, pady=3)
            self.behavior_buttons[tag] = btn
        
        # Custom Tags
        custom_frame = tk.LabelFrame(main_frame, text="Tags Personalizados",
                                     font=("Arial", 10, "bold"))
        custom_frame.pack(fill="x", pady=(0, 10))
        
        custom_btn_frame = tk.Frame(custom_frame)
        custom_btn_frame.pack(padx=10, pady=10)
        
        self.custom_buttons = []
        for idx, label in enumerate(self.custom_tag_labels):
            btn = tk.Button(custom_btn_frame, text=label,
                           bg=self.tag_inactive_bg,
                           width=15, height=2,
                           command=lambda i=idx: self.toggle_custom(i))
            btn.grid(row=0, column=idx, padx=3, pady=3)
            self.custom_buttons.append(btn)
        
        # Navigation buttons
        nav_frame = tk.Frame(self)
        nav_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Button(nav_frame, text="<< Anterior", 
                 command=self.prev_video, width=15).pack(side="left", padx=5)
        
        tk.Button(nav_frame, text="Guardar y Cerrar",
                 command=self.save_and_close,
                 bg="#3498db", fg="white",
                 width=20).pack(side="left", expand=True, padx=5)
        
        tk.Button(nav_frame, text="Siguiente >>",
                 command=self.next_video, width=15).pack(side="right", padx=5)
    
    def load_current_video(self):
        """Load current video metadata and update UI"""
        if not self.failed_videos or self.current_index >= len(self.failed_videos):
            return
        
        video = self.failed_videos[self.current_index]
        
        # Update header
        video_name = os.path.basename(video.get("video_path", "Unknown"))
        self.video_name_label.config(text=f"📹 {video_name}")
        
        error_msg = video.get("error_message", "Error desconocido")
        self.error_label.config(text=f"⚠️ {error_msg}")
        
        count_text = f"Video {self.current_index + 1} de {len(self.failed_videos)}"
        self.video_count_label.config(text=count_text)
        
        # Load metadata
        metadata = video.get("metadata", {})
        self.site_entry.delete(0, tk.END)
        self.site_entry.insert(0, metadata.get("site", ""))
        
        self.subsite_entry.delete(0, tk.END)
        self.subsite_entry.insert(0, metadata.get("subsite", ""))
        
        self.camera_entry.delete(0, tk.END)
        self.camera_entry.insert(0, metadata.get("camera", ""))
        
        self.operator_entry.delete(0, tk.END)
        self.operator_entry.insert(0, metadata.get("operator", ""))
        
        # Load classification
        classification = video.get("classification", {})
        
        # Update species buttons
        species_list = classification.get("species", [])
        for tag, btn in self.species_buttons.items():
            if tag in species_list:
                btn.config(bg=self.tag_active_bg)
            else:
                btn.config(bg=self.tag_inactive_bg)
        
        # Update behavior buttons
        behaviors_list = classification.get("behaviors", [])
        for tag, btn in self.behavior_buttons.items():
            if tag in behaviors_list:
                btn.config(bg=self.tag_active_bg)
            else:
                btn.config(bg=self.tag_inactive_bg)
        
        # Update custom buttons
        custom_tags_list = classification.get("custom_tags", [])
        for idx, btn in enumerate(self.custom_buttons):
            label = self.custom_tag_labels[idx]
            if label in custom_tags_list:
                btn.config(bg=self.tag_active_bg)
            else:
                btn.config(bg=self.tag_inactive_bg)
    
    def play_video(self):
        """Open video with system default player"""
        if not self.failed_videos or self.current_index >= len(self.failed_videos):
            return
        
        video_path = self.failed_videos[self.current_index].get("video_path", "")
        
        if not os.path.exists(video_path):
            messagebox.showerror("Error", f"No se encuentra el video:\n{video_path}")
            return
        
        try:
            if os.name == 'nt':  # Windows
                os.startfile(video_path)
            elif sys.platform == 'darwin':  # Mac
                subprocess.Popen(['open', video_path])
            else:  # Linux
                subprocess.Popen(['xdg-open', video_path])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el video:\n{e}")
    
    def toggle_species(self, tag):
        """Toggle species tag"""
        video = self.failed_videos[self.current_index]
        classification = video.setdefault("classification", {})
        species_list = classification.setdefault("species", [])
        
        if tag in species_list:
            species_list.remove(tag)
            self.species_buttons[tag].config(bg=self.tag_inactive_bg)
        else:
            species_list.append(tag)
            self.species_buttons[tag].config(bg=self.tag_active_bg)
    
    def toggle_behavior(self, tag):
        """Toggle behavior tag"""
        video = self.failed_videos[self.current_index]
        classification = video.setdefault("classification", {})
        behaviors_list = classification.setdefault("behaviors", [])
        
        if tag in behaviors_list:
            behaviors_list.remove(tag)
            self.behavior_buttons[tag].config(bg=self.tag_inactive_bg)
        else:
            behaviors_list.append(tag)
            self.behavior_buttons[tag].config(bg=self.tag_active_bg)
    
    def toggle_custom(self, idx):
        """Toggle custom tag"""
        video = self.failed_videos[self.current_index]
        classification = video.setdefault("classification", {})
        custom_tags_list = classification.setdefault("custom_tags", [])
        
        label = self.custom_tag_labels[idx]
        
        if label in custom_tags_list:
            custom_tags_list.remove(label)
            self.custom_buttons[idx].config(bg=self.tag_inactive_bg)
        else:
            custom_tags_list.append(label)
            self.custom_buttons[idx].config(bg=self.tag_active_bg)
    
    def save_current_video(self):
        """Save current video metadata"""
        video = self.failed_videos[self.current_index]
        
        # Update metadata
        metadata = video.setdefault("metadata", {})
        metadata["site"] = self.site_entry.get().strip()
        metadata["subsite"] = self.subsite_entry.get().strip()
        metadata["camera"] = self.camera_entry.get().strip()
        metadata["operator"] = self.operator_entry.get().strip()
        
        # Update counts
        classification = video.setdefault("classification", {})
        species_list = classification.get("species", [])
        
        if species_list:
            try:
                qty = int(self.quantity_spinbox.get())
                counts = classification.setdefault("counts", {})
                for sp in species_list:
                    counts[sp] = qty
            except ValueError:
                pass
    
    def prev_video(self):
        """Go to previous video"""
        if self.current_index > 0:
            self.save_current_video()
            self.current_index -= 1
            self.load_current_video()
    
    def next_video(self):
        """Go to next video"""
        if self.current_index < len(self.failed_videos) - 1:
            self.save_current_video()
            self.current_index += 1
            self.load_current_video()
    
    def save_and_close(self):
        """Save all changes and close"""
        # Save current video
        self.save_current_video()
        
        # Save metadata to file
        try:
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                # Need to reload full metadata and update failed videos
                with open(self.metadata_path, 'r', encoding='utf-8') as rf:
                    all_metadata = json.load(rf)
                
                # Update failed videos in all_metadata
                for failed_video in self.failed_videos:
                    video_hash = failed_video.get("video_hash", "")
                    for idx, meta in enumerate(all_metadata):
                        if meta.get("video_hash", "") == video_hash:
                            all_metadata[idx] = failed_video
                            break
                
                json.dump(all_metadata, f, indent=4, ensure_ascii=False)
            
            messagebox.showinfo("Éxito", 
                              f"Etiquetado guardado para {len(self.failed_videos)} videos fallidos.")
            self.destroy()
            
            # Return to main
            from main import MainApp
            MainApp().mainloop()
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")


if __name__ == "__main__":
    # Test with dummy data
    config = load_config()
    failed = [
        {
            "video_path": "test.avi",
            "video_hash": "test123",
            "error_message": "Timeout error",
            "status": "error",
            "metadata": {},
            "classification": {}
        }
    ]
    app = ManualTaggerGUI(failed, config, "test_metadata.json")
    app.mainloop()
