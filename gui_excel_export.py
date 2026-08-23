"""
gui_excel_export.py - GUI de exportación de metadata
Permite seleccionar campos, orden de columnas, etiquetas personalizadas.
Exporta a CSV personalizado o paquete Camtrap DP completo.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import json
import string
import subprocess
import sys
from config_utils import load_config, get_excel_fields_default
from export_utils import (
    filter_videos,
    get_unique_tags,
    get_unique_values,
    get_unique_behaviors,
    flatten_metadata
)
from export_camtrap import export_camtrap
from export_inabio import export_inabio_gui

class ExcelExportGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Exportar metadata")
        self.geometry("850x650")

        self.config_data = load_config()
        self.consolidated_path = os.path.join(
            self.config_data["General"]["output_folder"],
            "consolidated",
            "all_sessions_metadata.json"
        )

        if not os.path.exists(self.consolidated_path):
            messagebox.showerror(
                "Error",
                "No se encontró el archivo consolidado.\n"
                "Complete al menos una sesión de etiquetado primero."
            )
            self.destroy()
            return

        with open(self.consolidated_path, "r", encoding="utf-8") as f:
            self.all_metadata = json.load(f)

        # Estado de la UI
        self.fields_vars = {}          # {field: BooleanVar}
        self.column_dropdowns = {}     # {field: StringVar}
        self.label_entries = {}        # {field: Entry}
        self.checkbuttons = {}         # {field: Checkbutton}
        self.field_letter_map = {}     # {field: letter} - PRESERVA asignación
        self.used_letters = set()      # Letras ya asignadas
        self.all_letters = list(string.ascii_uppercase)
        self.advanced_filters = {}

        # -------------------------
        # Frame superior: opciones y filtros
        # -------------------------
        top_frame = tk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=5)

        options_frame = tk.Frame(top_frame)
        options_frame.pack(side="left", padx=10)

        self.selection_option = tk.StringVar(value="predeterminados")
        tk.Radiobutton(options_frame, text="Predeterminados",
                       variable=self.selection_option, value="predeterminados",
                       command=self.refresh_fields).pack(side="left", padx=10)
        tk.Radiobutton(options_frame, text="Todos",
                       variable=self.selection_option, value="todos",
                       command=self.refresh_fields).pack(side="left", padx=10)

        tk.Button(top_frame, text="Filtros avanzados...",
                  command=self.open_advanced_filters).pack(side="right", padx=10)

        # -------------------------
        # Frame scrollable para campos
        # -------------------------
        container = tk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(container)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.fields_frame = tk.Frame(canvas)
        self.fields_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.fields_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # -------------------------
        # Botones de exportación
        # -------------------------
        buttons_frame = tk.Frame(self)
        buttons_frame.pack(pady=10)

        tk.Button(buttons_frame, text="Cancelar", command=self.cancel).pack(side="left", padx=5)
        tk.Button(buttons_frame, text="CAMTRAP", command=self.export_camtrap_package,
                  bg="#00bcd4", fg="white", width=15, font=("Arial", 10, "bold")).pack(side="left", padx=5)
        tk.Button(buttons_frame, text="INABIO", command=self.export_inabio_package,
                  bg="#2e7d32", fg="white", width=15, font=("Arial", 10, "bold")).pack(side="left", padx=5)
        tk.Button(buttons_frame, text="CSV", command=self.export_custom_csv,
                  bg="#2196f3", fg="white", width=15, font=("Arial", 10, "bold")).pack(side="left", padx=5)

        # Cerrar vuelve a main
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        # Inicializar campos
        self.refresh_fields()

    # -------------------------
    # Asignación inteligente de columnas
    # -------------------------
    def _assign_letter(self, field):
        """Asigna una letra libre al campo. Preserva si ya tenía."""
        if field in self.field_letter_map:
            return self.field_letter_map[field]
        # Buscar primera letra libre
        for letter in self.all_letters:
            if letter not in self.used_letters:
                self.field_letter_map[field] = letter
                self.used_letters.add(letter)
                return letter
        return ""

    def _release_letter(self, field):
        """Libera la letra asignada al campo."""
        if field in self.field_letter_map:
            letter = self.field_letter_map[field]
            self.used_letters.discard(letter)
            del self.field_letter_map[field]

    # -------------------------
    # Ventana de filtros avanzados
    # -------------------------
    def open_advanced_filters(self):
        if hasattr(self, '_filter_window') and tk.Toplevel.winfo_exists(self._filter_window):
            self._filter_window.lift()
            return

        win = tk.Toplevel(self)
        win.title("Filtros avanzados")
        win.geometry("500x500")
        self._filter_window = win

        # Sesión
        tk.Label(win, text="Sesión:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        session_frame = tk.Frame(win)
        session_frame.pack(fill="x", padx=10, pady=2)
        self.session_var = tk.StringVar(value=self.advanced_filters.get("session_filter", "all"))
        tk.Radiobutton(session_frame, text="Todas", variable=self.session_var, value="all").pack(side="left")
        tk.Radiobutton(session_frame, text="Última", variable=self.session_var, value="last").pack(side="left", padx=5)
        self.session_entry = tk.Entry(session_frame, width=15)
        self.session_entry.pack(side="left", padx=5)
        if self.advanced_filters.get("session_filter", "").startswith("specific:"):
            spec_id = self.advanced_filters["session_filter"].split(":", 1)[1]
            self.session_entry.insert(0, spec_id)
            self.session_var.set("specific")

        # Tags
        tags = get_unique_tags(self.all_metadata)
        if tags:
            tk.Label(win, text="Especies:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            tag_frame = tk.Frame(win)
            tag_frame.pack(fill="x", padx=10, pady=2)
            self.tag_vars = {}
            for i, tag in enumerate(tags):
                var = tk.BooleanVar(value=tag in self.advanced_filters.get("tags", []))
                cb = tk.Checkbutton(tag_frame, text=tag, variable=var)
                cb.grid(row=i // 3, column=i % 3, sticky="w", padx=5)
                self.tag_vars[tag] = var

        # Operadores
        operators = get_unique_values(self.all_metadata, "operator")
        if operators:
            tk.Label(win, text="Operadores:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            op_frame = tk.Frame(win)
            op_frame.pack(fill="x", padx=10, pady=2)
            self.op_vars = {}
            for i, op in enumerate(operators):
                var = tk.BooleanVar(value=op in self.advanced_filters.get("operators", []))
                cb = tk.Checkbutton(op_frame, text=op, variable=var)
                cb.grid(row=i // 3, column=i % 3, sticky="w", padx=5)
                self.op_vars[op] = var

        # Botones
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Aplicar",
                  command=lambda: [self._apply_filters(), win.destroy()]).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="left", padx=5)

    def _apply_filters(self):
        """Guarda los filtros seleccionados en self.advanced_filters."""
        filters = {}
        session_opt = self.session_var.get()
        if session_opt == "last":
            filters["session_filter"] = "last"
        elif session_opt == "specific":
            spec_id = self.session_entry.get().strip()
            filters["session_filter"] = f"specific:{spec_id}" if spec_id else "all"
        else:
            filters["session_filter"] = "all"

        if hasattr(self, 'tag_vars'):
            selected_tags = [t for t, var in self.tag_vars.items() if var.get()]
            if selected_tags:
                filters["tags"] = selected_tags

        if hasattr(self, 'op_vars'):
            selected_ops = [o for o, var in self.op_vars.items() if var.get()]
            if selected_ops:
                filters["operators"] = selected_ops

        self.advanced_filters = filters

    # -------------------------
    # Refrescar checkboxes y dropdowns
    # -------------------------
    def refresh_fields(self):
        """Regenera la lista de campos según la opción seleccionada."""
        # Limpiar UI
        for widget in self.fields_frame.winfo_children():
            widget.destroy()

        # Limpiar estado (PERO preservar field_letter_map para mantener asignaciones)
        self.fields_vars.clear()
        self.column_dropdowns.clear()
        self.label_entries.clear()
        self.checkbuttons.clear()
        self.used_letters = set(self.field_letter_map.values())

        # Obtener lista de campos
        if self.selection_option.get() == "todos":
            # Todos los campos del modelo (planos, desde flatten_metadata de ejemplo)
            if self.all_metadata:
                sample = flatten_metadata(self.all_metadata[0])
                fields_list = list(sample.keys())
            else:
                fields_list = list(self.config_data["MetadataSettings"]["model"].keys())
        else:
            fields_list = get_excel_fields_default(self.config_data)

        # Crear filas
        for field in fields_list:
            row = tk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)

            # Checkbox (por defecto marcado)
            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(row, text=field, variable=var, width=20, anchor="w",
                                command=lambda f=field, v=var: self.toggle_column_controls(f, v))
            cb.pack(side="left", padx=5)
            self.fields_vars[field] = var
            self.checkbuttons[field] = cb

            # Column dropdown
            tk.Label(row, text="Col:").pack(side="left")
            col_var = tk.StringVar()
            dropdown = ttk.Combobox(row, textvariable=col_var, width=3, state="readonly")
            dropdown['values'] = self.all_letters
            dropdown.pack(side="left", padx=2)

            # Asignar letra (preservando si ya tenía)
            letter = self._assign_letter(field)
            col_var.set(letter)

            self.column_dropdowns[field] = dropdown

            # Label textbox
            tk.Label(row, text="Label:").pack(side="left", padx=(10, 2))
            label_entry = tk.Entry(row, width=20)
            label_entry.insert(0, field)  # Default al nombre del campo
            label_entry.pack(side="left", padx=2)
            self.label_entries[field] = label_entry

    def toggle_column_controls(self, field, var):
        """Muestra/oculta controles y libera/reserva letra."""
        dropdown = self.column_dropdowns[field]
        label_entry = self.label_entries[field]
        cb = self.checkbuttons[field]

        if var.get():
            # Mostrar controles y (re)asignar letra
            dropdown.pack(side="left", padx=2)
            label_entry.pack(side="left", padx=2)
            cb.config(fg="black")
            if field not in self.field_letter_map:
                letter = self._assign_letter(field)
                self.column_dropdowns[field].set(letter)
        else:
            # Ocultar controles y liberar letra
            dropdown.pack_forget()
            label_entry.pack_forget()
            cb.config(fg="gray60")
            self._release_letter(field)

    # -------------------------
    # Export CAMTRAP Package
    # -------------------------
    def export_camtrap_package(self):
        """Exporta paquete Camtrap DP 1.0 completo (6 CSV + datapackage.json)."""
        try:
            output_folder = self.config_data['General']['output_folder']
            camtrap_dir = filedialog.askdirectory(
                initialdir=output_folder,
                title="Seleccionar carpeta para exportar Camtrap DP"
            )
            if not camtrap_dir:
                return

            result_dir = export_camtrap(
                metadata_path=self.consolidated_path,
                output_dir=camtrap_dir,
                config=self.config_data
            )

            if result_dir:
                messagebox.showinfo(
                    "Éxito",
                    f"Paquete Camtrap DP exportado:\n\n{result_dir}\n\n"
                    "Archivos:\n"
                    "- projects.csv\n"
                    "- deployments.csv\n"
                    "- locations.csv\n"
                    "- taxa.csv\n"
                    "- media.csv\n"
                    "- observations.csv\n"
                    "- datapackage.json"
                )
                self._open_file(result_dir)

            self.cancel()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo exportar Camtrap DP:\n{e}")


    def export_inabio_package(self):
        """Exporta a formato INABIO (Darwin Core completo)."""
        try:
            result = export_inabio_gui(
                parent=self,
                metadata_path=self.consolidated_path,
                config=self.config_data
            )
            if result:
                self.cancel()  # Volver al menú principal
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo exportar a INABIO:\n{e}")

    # -------------------------
    # Export CSV personalizado
    # -------------------------
    def export_custom_csv(self):
        """Exporta CSV con campos, orden y etiquetas personalizadas."""
        try:
            # Aplicar filtros avanzados
            filtered_data = filter_videos(self.all_metadata, **self.advanced_filters)
            if not filtered_data:
                messagebox.showwarning("Advertencia", "No hay videos que coincidan con los filtros.")
                return

            # Recopilar campos seleccionados con sus posiciones y etiquetas
            selected_fields = []
            field_labels = {}
            field_columns = {}

            for field, var in self.fields_vars.items():
                if var.get():
                    selected_fields.append(field)
                    custom_label = self.label_entries[field].get().strip()
                    field_labels[field] = custom_label if custom_label else field
                    col_letter = self.column_dropdowns[field].get()
                    field_columns[field] = col_letter

            if not selected_fields:
                messagebox.showwarning("Advertencia", "Debe seleccionar al menos un campo.")
                return

            # Ordenar por letra de columna
            sorted_fields = sorted(selected_fields, key=lambda f: field_columns.get(f, "Z"))

            # Aplanar datos usando flatten_metadata (modelo nuevo)
            df_data = []
            for entry in filtered_data:
                # Saltar excluidos
                if entry.get("ui", {}).get("is_excluded", False):
                    continue

                flat = flatten_metadata(entry)
                custom_entry = {}
                for field in sorted_fields:
                    custom_label = field_labels[field]
                    if field in flat:
                        custom_entry[custom_label] = flat[field]
                    else:
                        # Fallback para campos no aplanados
                        value = entry.get(field, "")
                        if isinstance(value, dict):
                            value = str(value)
                        elif isinstance(value, list):
                            value = "|".join(str(v) for v in value)
                        custom_entry[custom_label] = value
                df_data.append(custom_entry)

            if not df_data:
                messagebox.showwarning("Advertencia", "No hay datos para exportar.")
                return

            # Guardar CSV
            output_folder = self.config_data['General']['output_folder']
            csv_path = filedialog.asksaveasfilename(
                initialdir=output_folder,
                defaultextension=".csv",
                initialfile="export_custom.csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Guardar CSV personalizado"
            )
            if not csv_path:
                return

            # Escribir con pandas o csv nativo
            try:
                import pandas as pd
                df_new = pd.DataFrame(df_data)
                df_new.to_csv(csv_path, index=False, encoding='utf-8-sig')
            except ImportError:
                # Fallback a csv nativo
                import csv
                with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=field_labels.values())
                    writer.writeheader()
                    writer.writerows(df_data)

            messagebox.showinfo("Éxito", f"CSV generado:\n{csv_path}\n\n{len(df_data)} registros.")

            if hasattr(self, 'open_after') and self.open_after.get():
                self._open_file(csv_path)

            self.cancel()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo exportar CSV:\n{e}")

    # -------------------------
    # Helpers
    # -------------------------
    def _open_file(self, path):
        """Abre archivo/carpeta con el visor del sistema."""
        try:
            if sys.platform.startswith('darwin'):
                subprocess.Popen(['open', path])
            elif os.name == 'nt':
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            print(f"⚠️ No se pudo abrir: {e}")

    def cancel(self):
        """Cierra y vuelve al menú principal."""
        self.destroy()
        try:
            from main import MainApp
            MainApp().mainloop()
        except Exception as e:
            print(f"⚠️ No se pudo abrir MainApp: {e}")


if __name__ == "__main__":
    app = ExcelExportGUI()
    app.mainloop()