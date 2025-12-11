#!/usr/bin/env python3
"""
gui_analysis.py

Módulo standalone para análisis rápido de metadata de cámaras trampa.
- Dashboard 2x2 con mini-gráficos (pie, time series, rose, rayleigh)
- Panel lateral con filtros dinámicos: fuente (todo / última sesión), sitio, especie, rango de fechas
- Controles de propiedades: grosor de línea y tamaño de fuente
- Click en mini-gráfico abre ventana ampliada con export PNG y tabla (.xlsx)
- Exportar todas las tablas a un único .xlsx con hoja por gráfico
- Fecha en formato YYYY-MM-DD

Dependencias:
- pandas, matplotlib, openpyxl, tkinter
- config_utils (de tu proyecto)
"""

import os
import json
from datetime import datetime, date
import math

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from config_utils import load_config

# ---------------------------
# Helpers
# ---------------------------
def safe_load_json(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []

def parse_recorded_at(x):
    if pd.isna(x):
        return pd.NaT
    if isinstance(x, (int, float)):
        try:
            return pd.to_datetime(x)
        except Exception:
            return pd.NaT
    try:
        return pd.to_datetime(x)
    except Exception:
        try:
            return pd.to_datetime(x, format="%Y-%m-%d %H:%M:%S")
        except Exception:
            return pd.NaT

def extract_species_list(tags_field):
    if isinstance(tags_field, list):
        return [t for t in tags_field if t]
    if isinstance(tags_field, str):
        return [t.strip() for t in tags_field.split(",") if t.strip()]
    return []

def hours_to_radians(hours):
    return np.deg2rad(np.array(hours) * 15.0)

def human_date(d: date):
    return d.strftime("%Y-%m-%d")

# ---------------------------
# Analysis GUI
# ---------------------------
class AnalysisGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Análisis rápido - Cámaras Trampa")
        self.geometry("1100x700")

        # Load config and data
        self.config_data = load_config()
        self.output_folder = self.config_data["General"].get("output_folder")
        os.makedirs(self.output_folder, exist_ok=True)

        # ←←← CAMBIO: usar archivo consolidado en lugar del json_file antiguo
        consolidated_path = os.path.join(self.output_folder, "consolidated", "all_sessions_metadata.json")
        raw = safe_load_json(consolidated_path)
        # →→→
        self.df_original = self._build_dataframe(raw)
        self.df = self.df_original.copy()

        # GUI state
        self.linewidth = tk.DoubleVar(value=2.0)
        self.fontsize = tk.IntVar(value=10)
        self.data_source = tk.StringVar(value="todo")  # 'todo' or 'ultima'

        # Date slider indexes
        self.unique_dates = []  # sorted list of dates (date objects)
        self.date_min_idx = tk.IntVar(value=0)
        self.date_max_idx = tk.IntVar(value=0)

        # Selected filters
        self.selected_sites = []
        self.selected_species = []

        # Matplotlib figures / canvases
        self.figures = [None] * 4
        self.canvases = [None] * 4

        self._build_ui()
        self._apply_data_source()

    def _build_dataframe(self, raw_list):
        if not raw_list:
            return pd.DataFrame()
        df = pd.DataFrame(raw_list)
        df["tags_list"] = df.get("tags", pd.Series([[]]*len(df))).apply(extract_species_list)
        df["recorded_at_dt"] = df.get("recorded_at", pd.Series([None]*len(df))).apply(parse_recorded_at)
        df["recorded_date"] = df["recorded_at_dt"].dt.date
        df["recorded_hour"] = df["recorded_at_dt"].dt.hour
        df_exploded = df.explode("tags_list")
        df_exploded.rename(columns={"tags_list": "species"}, inplace=True)
        return df_exploded

    # ---------------------------
    # UI Construction
    # ---------------------------
    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Left panel
        left = ttk.Frame(self, width=320)
        left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False)

        ttk.Label(left, text="Fuente de datos:").pack(anchor="w", pady=(10,0), padx=10)
        rb_frame = ttk.Frame(left)
        rb_frame.pack(anchor="w", padx=10)
        ttk.Radiobutton(rb_frame, text="Todo el JSON", variable=self.data_source, value="todo", command=self._apply_data_source).pack(anchor="w")
        ttk.Radiobutton(rb_frame, text="Última sesión", variable=self.data_source, value="ultima", command=self._apply_data_source).pack(anchor="w")

        ttk.Label(left, text="Sitios:").pack(anchor="w", pady=(10,0), padx=10)
        self.site_listbox = tk.Listbox(left, selectmode="multiple", exportselection=False, height=6)
        self.site_listbox.pack(fill="x", padx=10)
        self.site_listbox.bind("<<ListboxSelect>>", lambda e: self._on_site_select())

        ttk.Label(left, text="Especies:").pack(anchor="w", pady=(10,0), padx=10)
        self.species_listbox = tk.Listbox(left, selectmode="multiple", exportselection=False, height=6)
        self.species_listbox.pack(fill="x", padx=10)
        self.species_listbox.bind("<<ListboxSelect>>", lambda e: self._on_species_select())

        ttk.Label(left, text="Rango de fechas:").pack(anchor="w", pady=(10,0), padx=10)
        slider_frame = ttk.Frame(left)
        slider_frame.pack(fill="x", padx=10)
        self.scale_min = ttk.Scale(slider_frame, from_=0, to=0, command=lambda v: self._on_slider_change('min'))
        self.scale_min.pack(fill="x")
        self.scale_max = ttk.Scale(slider_frame, from_=0, to=0, command=lambda v: self._on_slider_change('max'))
        self.scale_max.pack(fill="x")
        self.date_label = ttk.Label(left, text="YYYY-MM-DD → YYYY-MM-DD")
        self.date_label.pack(anchor="center", pady=4)

        ttk.Label(left, text="Propiedades de gráficos:").pack(anchor="w", pady=(10,0), padx=10)
        ttk.Label(left, text="Grosor de línea:").pack(anchor="w", padx=10)
        ttk.Scale(left, from_=0.5, to=5.0, variable=self.linewidth, orient="horizontal", command=lambda v: self.update_plots()).pack(fill="x", padx=10)
        ttk.Label(left, text="Tamaño de fuente:").pack(anchor="w", padx=10, pady=(6,0))
        ttk.Scale(left, from_=8, to=20, variable=self.fontsize, orient="horizontal", command=lambda v: self.update_plots()).pack(fill="x", padx=10)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", padx=10, pady=12)
        ttk.Button(btn_frame, text="Actualizar gráficos", command=self.update_plots).pack(side="left")
        ttk.Button(btn_frame, text="Exportar todas tablas (.xlsx)", command=self.export_all_tables).pack(side="left", padx=6)
        ttk.Button(left, text="Exportar todos PNG", command=self.export_all_pngs).pack(fill="x", padx=10)
        ttk.Button(left, text="Volver al menú principal", command=self._back_to_main).pack(fill="x", padx=10, pady=(6,10))

        # Right panel (dashboard)
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure((0,1), weight=1)
        right.rowconfigure((0,1), weight=1)

        self.plot_frames = []
        titles = ["Frecuencia de especies", "Dinámica temporal", "Distribución horaria", "Rayleigh"]
        for i in range(4):
            frame = ttk.Frame(right, relief="ridge", padding=4)
            r = 0 if i < 2 else 1
            c = i if i < 2 else i - 2
            frame.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=titles[i]).pack(anchor="w")
            fig = Figure(figsize=(3.1, 2.6), dpi=90)
            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas.get_tk_widget().pack(fill="both", expand=True)
            canvas.mpl_connect('button_press_event', lambda event, idx=i: self._on_plot_click(event, idx))
            self.figures[i] = fig
            self.canvases[i] = canvas
            self.plot_frames.append(frame)

    # ---------------------------
    # Data source
    # ---------------------------
    def _apply_data_source(self):
        if self.data_source.get() == 'ultima':
            last_session_id = self.config_data.get("LastSession", {}).get("session_id")
            if last_session_id:
                df = self.df_original[self.df_original.get('session_id') == last_session_id].copy()
            else:
                df = self.df_original.copy()
        else:
            df = self.df_original.copy()
        self.df = df
        self._populate_filters()
        self.update_plots()

    def _populate_filters(self):
        sites = sorted([s for s in self.df.get('site', pd.Series()) if s and not pd.isna(s)])
        unique_sites = sorted(list(dict.fromkeys(sites)))
        self.site_listbox.delete(0, tk.END)
        for s in unique_sites:
            self.site_listbox.insert(tk.END, s)

        species = sorted([s for s in self.df.get('species', pd.Series()) if s and not pd.isna(s)])
        unique_species = sorted(list(dict.fromkeys(species)))
        self.species_listbox.delete(0, tk.END)
        for sp in unique_species:
            self.species_listbox.insert(tk.END, sp)

        dates = sorted([d for d in self.df.get('recorded_date').dropna().unique()])
        if not dates:
            self.unique_dates = []
            self.scale_min.configure(from_=0, to=0)
            self.scale_max.configure(from_=0, to=0)
            self.date_label.config(text="YYYY-MM-DD → YYYY-MM-DD")
            return
        self.unique_dates = [d if isinstance(d,date) else pd.to_datetime(d).date() for d in dates]
        n = len(self.unique_dates)-1
        self.scale_min.configure(from_=0, to=n)
        self.scale_max.configure(from_=0, to=n)
        self.scale_min.set(0)
        self.scale_max.set(n)
        self.date_min_idx.set(0)
        self.date_max_idx.set(n)
        self._update_date_label()

    def _on_site_select(self):
        self.selected_sites = [self.site_listbox.get(i) for i in self.site_listbox.curselection()]
        self.update_plots()

    def _on_species_select(self):
        self.selected_species = [self.species_listbox.get(i) for i in self.species_listbox.curselection()]
        self.update_plots()

    def _on_slider_change(self, which):
        try:
            min_idx = int(round(self.scale_min.get()))
            max_idx = int(round(self.scale_max.get()))
        except Exception:
            return
        if min_idx > max_idx:
            if which=='min': min_idx=max_idx; self.scale_min.set(min_idx)
            else: max_idx=min_idx; self.scale_max.set(max_idx)
        self.date_min_idx.set(min_idx)
        self.date_max_idx.set(max_idx)
        self._update_date_label()
        self.update_plots()

    def _update_date_label(self):
        if not self.unique_dates:
            self.date_label.config(text="YYYY-MM-DD → YYYY-MM-DD")
            return
        dmin = self.unique_dates[self.date_min_idx.get()]
        dmax = self.unique_dates[self.date_max_idx.get()]
        self.date_label.config(text=f"{human_date(dmin)} → {human_date(dmax)}")

    # ---------------------------
    # Plot helpers
    # ---------------------------
    def _filter_df(self):
        df = self.df.copy()
        if self.unique_dates:
            dmin = self.unique_dates[self.date_min_idx.get()]
            dmax = self.unique_dates[self.date_max_idx.get()]
            df = df[(df['recorded_date']>=dmin) & (df['recorded_date']<=dmax)]
        if self.selected_sites:
            df = df[df['site'].isin(self.selected_sites)]
        if self.selected_species:
            df = df[df['species'].isin(self.selected_species)]
        return df

    def update_plots(self):
        df = self._filter_df()
        for fig in self.figures: fig.clf()
        # Pie
        ax0 = self.figures[0].add_subplot(111)
        self._draw_pie(ax0, df)
        self.canvases[0].draw()
        # Time series
        ax1 = self.figures[1].add_subplot(111)
        self._draw_time_series(ax1, df)
        self.canvases[1].draw()
        # Rose
        ax2 = self.figures[2].add_subplot(111, projection='polar')
        self._draw_rose(ax2, df)
        self.canvases[2].draw()
        # Rayleigh
        ax3 = self.figures[3].add_subplot(111, projection='polar')
        self._draw_rayleigh(ax3, df)
        self.canvases[3].draw()

    def _draw_pie(self, ax, df):
        ax.clear()
        counts = df['species'].value_counts()
        if counts.empty:
            ax.text(0.5,0.5,'No hay datos', ha='center', va='center')
            return
        ax.pie(counts.values, labels=counts.index.tolist(), autopct='%1.1f%%', textprops={'fontsize':self.fontsize.get()})
        ax.set_title('Especies', fontsize=self.fontsize.get()+2)

    def _draw_time_series(self, ax, df):
        ax.clear()
        if df.empty: 
            ax.text(0.5,0.5,'No hay datos', ha='center', va='center')
            return
        if not self.selected_species:
            species_list = df['species'].dropna().unique()
        else:
            species_list = self.selected_species
        for sp in species_list:
            sub = df[df['species']==sp]
            ts = sub.groupby('recorded_date').size().sort_index()
            ax.plot(ts.index, ts.values, label=sp, linewidth=self.linewidth.get())
        ax.set_xlabel('Fecha', fontsize=self.fontsize.get())
        ax.set_ylabel('Detecciones', fontsize=self.fontsize.get())
        ax.tick_params(axis='x', rotation=30)
        # Dynamic time locator
        if df.empty: return
        dates = df['recorded_date']
        delta = (dates.max() - dates.min()).days
        if delta <=31:
            ax.xaxis.set_major_locator(mdates.DayLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        elif delta<=90:
            ax.xaxis.set_major_locator(mdates.WeekdayLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.legend(fontsize=self.fontsize.get())
        ax.grid(True, which='both', axis='x', linestyle='--', linewidth=0.5)
        ax.set_title('Detecciones', fontsize=self.fontsize.get()+2)

    def _draw_rose(self, ax, df):
        ax.clear()
        hours = df['recorded_hour'].dropna().astype(int)
        if hours.empty:
            ax.text(0.5,0.5,'No hay datos', ha='center', va='center')
            return
        bins = np.arange(0,25)
        counts,_ = np.histogram(hours, bins=bins)
        angles = hours_to_radians(bins[:-1])
        width = 2*math.pi/24
        ax.bar(angles, counts, width=width, align='edge')
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)
        ax.set_title('Actividad horaria', fontsize=self.fontsize.get()+2)

    def _draw_rayleigh(self, ax, df):
        ax.clear()
        hours = df['recorded_hour'].dropna().astype(int)
        if hours.empty:
            ax.text(0.5,0.5,'No hay datos', ha='center', va='center')
            return
        thetas = hours_to_radians(hours)
        ax.plot(thetas, np.ones_like(thetas), linestyle='None', marker='o', markersize=4)
        x = np.cos(thetas).mean(); y=np.sin(thetas).mean()
        r = math.hypot(x,y)
        theta_mean = math.atan2(y,x)
        ax.arrow(theta_mean,0,0,r,width=0.03,length_includes_head=True)
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)
        ax.set_title('Rayleigh (vector medio)', fontsize=self.fontsize.get()+2)

    # ---------------------------
    # Plot click
    # ---------------------------
    def _on_plot_click(self, event, idx):
        self._open_large_plot(idx)

    def _open_large_plot(self, idx):
        df = self._filter_df()
        top = tk.Toplevel(self)
        top.title(f"Gráfico {idx}")
        top.geometry("900x650")

        fig = Figure(figsize=(8,6), dpi=100)
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.get_tk_widget().pack(fill='both', expand=True)

        if idx==0:
            ax = fig.add_subplot(111); self._draw_pie(ax, df); sheet_name='Especies'
        elif idx==1:
            ax = fig.add_subplot(111); self._draw_time_series(ax, df); sheet_name='Detecciones_por_dia'
        elif idx==2:
            ax = fig.add_subplot(111, projection='polar'); self._draw_rose(ax, df); sheet_name='Actividad_horaria'
        else:
            ax = fig.add_subplot(111, projection='polar'); self._draw_rayleigh(ax, df); sheet_name='Rayleigh'

        title_filters=[]
        if self.selected_sites: title_filters.append("Sitio: "+",".join(self.selected_sites))
        if self.unique_dates:
            dmin = self.unique_dates[self.date_min_idx.get()]
            dmax = self.unique_dates[self.date_max_idx.get()]
            title_filters.append(f"Fechas: {human_date(dmin)} → {human_date(dmax)}")
        if title_filters: fig.suptitle(" - ".join(title_filters), fontsize=self.fontsize.get()+4)

        btn_frame = ttk.Frame(top); btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="Guardar PNG", command=lambda:self._save_fig(fig)).pack(side='left', padx=6, pady=6)
        ttk.Button(btn_frame, text="Exportar tabla (.xlsx)", command=lambda:self._export_table_for_plot(df,sheet_name)).pack(side='left', padx=6)
        ttk.Button(btn_frame, text="Cerrar", command=top.destroy).pack(side='right', padx=6)

        canvas.draw()

    def _save_fig(self, fig):
        path = filedialog.asksaveasfilename(initialdir=self.output_folder, defaultextension='.png', filetypes=[('PNG','*.png')])
        if not path: return
        fig.savefig(path)
        messagebox.showinfo('Guardado', f'Imagen guardada en:\n{path}')

    # ---------------------------
    # Export tables
    # ---------------------------
    def _export_table_for_plot(self, df, sheet_name):
        if sheet_name=='Especies':
            table=df[['session_id','site','camera','recorded_at_dt','species']].copy()
        elif sheet_name=='Detecciones_por_dia':
            table=df.groupby('recorded_date').size().reset_index(name='detections')
        else:
            table=df[['session_id','site','camera','recorded_at_dt','recorded_hour']].copy()
        if 'recorded_at_dt' in table.columns:
            table['recorded_at_dt']=table['recorded_at_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
        if 'recorded_date' in table.columns:
            table['recorded_date']=table['recorded_date'].apply(lambda x:x.strftime('%Y-%m-%d'))
        default=os.path.join(self.output_folder,f"{sheet_name}.xlsx")
        path=filedialog.asksaveasfilename(initialdir=self.output_folder, defaultextension='.xlsx', initialfile=os.path.basename(default), filetypes=[('Excel','*.xlsx')])
        if not path: return
        try: table.to_excel(path,index=False); messagebox.showinfo('Exportado',f'Tabla exportada a:\n{path}')
        except Exception as e: messagebox.showerror('Error', f'No se pudo exportar:\n{e}')

    def export_all_tables(self):
        df = self._filter_df()
        default = os.path.join(self.output_folder, 'analisis_tablas.xlsx')
        path = filedialog.asksaveasfilename(initialdir=self.output_folder, defaultextension='.xlsx', initialfile=os.path.basename(default), filetypes=[('Excel','*.xlsx')])
        if not path: return
        try:
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                t0=df[['session_id','site','camera','recorded_at_dt','species']].copy()
                t0['recorded_at_dt']=t0['recorded_at_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
                t0.to_excel(writer,sheet_name='Especies',index=False)
                t1=df.groupby('recorded_date').size().reset_index(name='detections')
                t1['recorded_date']=t1['recorded_date'].apply(lambda x:x.strftime('%Y-%m-%d'))
                t1.to_excel(writer,sheet_name='Detecciones_por_dia',index=False)
                t2=df[['session_id','site','camera','recorded_at_dt','recorded_hour']].copy()
                t2['recorded_at_dt']=t2['recorded_at_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
                t2.to_excel(writer,sheet_name='Actividad_horaria',index=False)
                t3=df[['session_id','site','camera','recorded_at_dt','recorded_hour']].copy()
                t3['recorded_at_dt']=t3['recorded_at_dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
                t3.to_excel(writer,sheet_name='Rayleigh',index=False)
            messagebox.showinfo('Exportado', f'Archivo Excel creado:\n{path}')
        except Exception as e: messagebox.showerror('Error', f'No se pudo exportar:\n{e}')

    def export_all_pngs(self):
        base=os.path.join(self.output_folder,'plot')
        df=self._filter_df()
        names=['Especies','Detecciones_por_dia','Actividad_horaria','Rayleigh']
        for i in range(4):
            fig=Figure(figsize=(8,6),dpi=100)
            if i==0: ax=fig.add_subplot(111); self._draw_pie(ax,df)
            elif i==1: ax=fig.add_subplot(111); self._draw_time_series(ax,df)
            elif i==2: ax=fig.add_subplot(111,projection='polar'); self._draw_rose(ax,df)
            else: ax=fig.add_subplot(111,projection='polar'); self._draw_rayleigh(ax,df)
            path=f"{base}_{names[i]}.png"
            try: fig.savefig(path)
            except Exception: pass
        messagebox.showinfo('Exportado', f'PNG generados en carpeta:\n{self.output_folder}')

    def _back_to_main(self):
        try:
            from main import MainApp
            self.destroy()
            MainApp().mainloop()
        except Exception:
            self.destroy()


if __name__=='__main__':
    app = AnalysisGUI()
    app.mainloop()
