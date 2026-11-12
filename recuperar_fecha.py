#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recuperar_fecha.py

Recupera la fecha y hora de captura (recorded_at) en archivos metadata.json
ya procesados, a partir del campo 'fecha_prefix' (formato AAMMDD_HHMMSS).

Uso:
    - Doble clic o 'python recuperar_fecha.py': se abre un panel para
      seleccionar uno o más metadata.json.
    - También acepta rutas por línea de comandos:
          python recuperar_fecha.py metadata.json
          python recuperar_fecha.py metadata.json -o metadata_corregido.json

Salida:
    Por defecto, <nombre>_fecha.json junto al archivo original.
    El archivo original nunca se modifica.
    Solo se completan los recorded_at vacíos; los que ya tienen valor se respetan.
"""

import argparse
import json
import os
import sys
from datetime import datetime


def fecha_prefix_a_iso(fecha_prefix):
    """Convierte 'AAMMDD_HHMMSS' (o 'AAMMDD HHMMSS') a 'AAAA-MM-DDTHH:MM:SS'. Devuelve '' si no es válido."""
    if not isinstance(fecha_prefix, str):
        return ""
    texto = fecha_prefix.strip().replace(" ", "_")
    try:
        dt = datetime.strptime(texto, "%y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return ""


def recuperar_fechas(metadata_list):
    """
    Completa recorded_at (nivel superior y dentro de 'metadata') en cada entrada.
    Devuelve (metadata_list, stats).
    """
    stats = {"total": 0, "completadas": 0, "ya_tenian": 0, "sin_fecha_valida": 0}

    for entry in metadata_list:
        stats["total"] += 1

        meta = entry.get("metadata")
        valor_meta = meta.get("recorded_at", "") if isinstance(meta, dict) else ""
        valor_top = entry.get("recorded_at", "")
        existente = valor_meta or valor_top

        if existente:
            nuevo = existente
            stats["ya_tenian"] += 1
        else:
            nuevo = fecha_prefix_a_iso(entry.get("fecha_prefix", ""))
            if not nuevo:
                stats["sin_fecha_valida"] += 1
                continue
            stats["completadas"] += 1

        entry["recorded_at"] = nuevo
        if isinstance(meta, dict):
            meta["recorded_at"] = nuevo

    return metadata_list, stats


def procesar_archivo(ruta_entrada, ruta_salida=None):
    with open(ruta_entrada, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("El JSON debe contener una lista de entradas.")

    data, stats = recuperar_fechas(data)

    if ruta_salida is None:
        base, ext = os.path.splitext(ruta_entrada)
        ruta_salida = f"{base}_fecha{ext or '.json'}"

    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return ruta_salida, stats


def _formatear_resultado(ruta, salida, s):
    return (f"✔ {ruta}\n   -> {salida}\n"
            f"   Entradas: {s['total']} | completadas: {s['completadas']} | "
            f"ya tenían fecha: {s['ya_tenian']} | sin fecha válida: {s['sin_fecha_valida']}")


def main_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    rutas = filedialog.askopenfilenames(
        parent=root,
        title="Seleccionar metadata.json (se puede elegir más de uno)",
        filetypes=[("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")]
    )
    if not rutas:
        root.destroy()
        return

    resultados = []
    for ruta in rutas:
        try:
            salida, s = procesar_archivo(ruta)
            resultados.append(_formatear_resultado(ruta, salida, s))
        except Exception as e:
            resultados.append(f"✘ {ruta}\n   {e}")

    messagebox.showinfo("Recuperación de fechas", "\n\n".join(resultados), parent=root)
    root.destroy()


def main_cli(argv):
    parser = argparse.ArgumentParser(
        description="Recupera recorded_at en metadata.json a partir de fecha_prefix."
    )
    parser.add_argument("archivos", nargs="+", help="Uno o más metadata.json de entrada")
    parser.add_argument("-o", "--salida", default=None,
                        help="Ruta de salida (solo válido con un único archivo de entrada)")
    args = parser.parse_args(argv)

    if args.salida and len(args.archivos) > 1:
        print("Error: --salida solo se puede usar con un único archivo de entrada.")
        sys.exit(1)

    for ruta in args.archivos:
        try:
            salida, s = procesar_archivo(ruta, args.salida)
            print(_formatear_resultado(ruta, salida, s))
        except Exception as e:
            print(f"✘ {ruta}: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main_cli(sys.argv[1:])
    else:
        main_gui()
