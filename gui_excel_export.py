import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import json
import pandas as pd
from config_utils import load_config
import string
import subprocess
import sys

# ←←← NUEVO: importar módulo de filtrado
from filter_utils import (
    filter_videos,
    get_unique_tags,
    get_unique_values,
    get_unique_behaviors
)
# →→→


class ExcelExportGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Exportar metadata a Excel")
        self.geometry("800x600")  # ← ligeramente más ancho para filtros

        self.config_data = load_config()

        # ←←← NUEVO: cargar archivo consolidado
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
        # →→→

        self.fields_vars = {}
        self.column_dropdowns = {}
        self.checkbuttons = {}
        self.available_letters = list(string.ascii_uppercase)

        # -------------------------
        # Frame superior: opciones y filtros
        # -------------------------
        top_frame = tk.Frame(self)
        top_frame.pack(fill="x", padx=10, pady=5)

        # Opción: Predeterminados / Todos
        options_frame = tk.Frame(top_frame)
        options_frame.pack(side="left", padx=10)
        self.selection_option = tk.StringVar(value="predeterminados")
        tk.Radiobutton(options_frame, text="Predeterminados",
                       variable=self.selection_option, value="predeterminados",
                       command=self.refresh_fields).pack(side="left", padx=10)
        tk.Radiobutton(options_frame, text="Todos",
                       variable=self.selection_option, value="todos",
                       command=self.refresh_fields).pack(side="left", padx=10)

        # ←←← NUEVO: Botón para filtros avanzados
        tk.Button(top_frame, text="Filtros avanzados...", 
                  command=self.open_advanced_filters).pack(side="right", padx=10)
        self.advanced_filters = {}  # almacenará los filtros seleccionados
        # →→→

        # -------------------------
        # Opción Append / Nuevo archivo
        # -------------------------
        file_frame = tk.Frame(self)
        file_frame.pack(pady=5, fill="x", padx=10)
        tk.Label(file_frame, text="Si existe archivo Excel:").pack(anchor="w")
        self.file_option = tk.StringVar(value="nuevo")
        tk.Radiobutton(file_frame, text="Generar nuevo", variable=self.file_option, value="nuevo").pack(anchor="w")
        tk.Radiobutton(file_frame, text="Agregar al existente", variable=self.file_option, value="append").pack(anchor="w")

        # -------------------------
        # Checkbox abrir archivo al finalizar
        # -------------------------
        self.open_after = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text="Abrir archivo al finalizar", variable=self.open_after).pack(pady=5)

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
        # Botones
        # -------------------------
        buttons_frame = tk.Frame(self)
        buttons_frame.pack(pady=10)

        tk.Button(buttons_frame, text="Cancelar", command=self.cancel).pack(side="left", padx=5)
        tk.Button(buttons_frame, text="Exportar a Excel", command=self.export_excel).pack(side="left", padx=5)

        # Inicializar campos
        self.refresh_fields()

    # -------------------------
    # ←←← NUEVO: Ventana de filtros avanzados
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
                cb.grid(row=i//3, column=i%3, sticky="w", padx=5)
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
                cb.grid(row=i//3, column=i%3, sticky="w", padx=5)
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

        # Sesión
        session_opt = self.session_var.get()
        if session_opt == "last":
            filters["session_filter"] = "last"
        elif session_opt == "specific":
            spec_id = self.session_entry.get().strip()
            filters["session_filter"] = f"specific:{spec_id}" if spec_id else "all"
        else:
            filters["session_filter"] = "all"

        # Tags
        if hasattr(self, 'tag_vars'):
            selected_tags = [t for t, var in self.tag_vars.items() if var.get()]
            if selected_tags:
                filters["tags"] = selected_tags

        # Operadores
        if hasattr(self, 'op_vars'):
            selected_ops = [o for o, var in self.op_vars.items() if var.get()]
            if selected_ops:
                filters["operators"] = selected_ops

        self.advanced_filters = filters
    # →→→ FIN NUEVO

    # -------------------------
    # Refrescar checkboxes y dropdowns
    # -------------------------
    def refresh_fields(self):
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        self.fields_vars.clear()
        self.column_dropdowns.clear()
        self.checkbuttons.clear()
        self.available_letters = list(string.ascii_uppercase)

        if self.selection_option.get() == "todos":
            fields_list = list(self.config_data["MetadataSettings"]["model"].keys())
        else:
            fields_list = self.config_data["MetadataSettings"]["ExcelFieldsDefault"]

        for field in fields_list:
            row = tk.Frame(self.fields_frame)
            row.pack(fill="x", pady=2)

            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(row, text=field, variable=var,
                                command=lambda f=field, v=var: self.toggle_column_dropdown(f, v))
            cb.pack(side="left", padx=5)
            self.fields_vars[field] = var
            self.checkbuttons[field] = cb

            col_var = tk.StringVar()
            dropdown = ttk.Combobox(row, textvariable=col_var, width=5, state="readonly")
            dropdown['values'] = list(string.ascii_uppercase)
            dropdown.pack(side="left", padx=5)

            if self.available_letters:
                col_var.set(self.available_letters.pop(0))

            self.column_dropdowns[field] = dropdown

            if not var.get():
                dropdown.pack_forget()
                cb.config(fg="gray60")

    def toggle_column_dropdown(self, field, var):
        dropdown = self.column_dropdowns[field]
        cb = self.checkbuttons[field]
        if var.get():
            dropdown.pack(side="left", padx=5)
            cb.config(fg="black")
        else:
            dropdown.pack_forget()
            cb.config(fg="gray60")

    # -------------------------
    # Exportar Excel (ACTUALIZADO)
    # -------------------------
    def export_excel(self):
        try:
            # ←←← NUEVO: aplicar filtros antes de exportar
            filtered_data = filter_videos(self.all_metadata, **self.advanced_filters)
            if not filtered_data:
                messagebox.showwarning("Advertencia", "No hay videos que coincidan con los filtros.")
                return
            # →→→

            selected_fields = [f for f, var in self.fields_vars.items() if var.get()]
            df_data = []
            for entry in filtered_data:  # ← usa filtered_data, no all_metadata
                flat_entry = {}
                for f in selected_fields:
                    value = entry.get(f, "")
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    flat_entry[f] = value
                df_data.append(flat_entry)

            if not df_data:
                df_data.append({f: "" for f in selected_fields})

            df_new = pd.DataFrame(df_data)

            output_folder = self.config_data['General']['output_folder']
            if self.file_option.get() == "nuevo":
                excel_path = filedialog.asksaveasfilename(
                    initialdir=output_folder,
                    defaultextension=".xlsx",
                    filetypes=[("Excel files", "*.xlsx")],
                    title="Guardar Excel como"
                )
                if not excel_path:
                    return
                df_new.to_excel(excel_path, index=False)
            else:
                excel_path = os.path.join(output_folder, "datos_camadas_trampa.xlsx")
                if os.path.exists(excel_path):
                    df_existente = pd.read_excel(excel_path)
                    df_combined = pd.concat([df_existente, df_new], ignore_index=True)
                    df_combined.to_excel(excel_path, index=False)
                else:
                    df_new.to_excel(excel_path, index=False)

            messagebox.showinfo("Éxito", f"Archivo Excel generado:\n{excel_path}")

            if self.open_after.get():
                if sys.platform.startswith('darwin'):
                    subprocess.Popen(['open', excel_path])
                elif os.name == 'nt':
                    os.startfile(excel_path)
                else:
                    subprocess.Popen(['xdg-open', excel_path])

            self.destroy()
            from main import MainApp
            MainApp().mainloop()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar a Excel:\n{e}")

    def cancel(self):
        self.destroy()
        from main import MainApp
        MainApp().mainloop()


if __name__ == "__main__":
    app = ExcelExportGUI()
    app.mainloop()