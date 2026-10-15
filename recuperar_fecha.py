#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recuperar_fecha.py

Recupera la fecha y hora de captura (recorded_at) en archivos metadata.json
ya procesados, a partir del campo 'fecha_prefix' (formato AAMMDD_HHMMSS).

Uso:
    python recuperar_fecha.py metadata.json
    python recuperar_fecha.py metadata1.json metadata2.json
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


def main():
    parser = argparse.ArgumentParser(
        description="Recupera recorded_at en metadata.json a partir de fecha_prefix."
    )
    parser.add_argument("archivos", nargs="+", help="Uno o más metadata.json de entrada")
    parser.add_argument("-o", "--salida", default=None,
                        help="Ruta de salida (solo válido con un único archivo de entrada)")
    args = parser.parse_args()

    if args.salida and len(args.archivos) > 1:
        print("Error: --salida solo se puede usar con un único archivo de entrada.")
        sys.exit(1)

    for ruta in args.archivos:
        try:
            salida, s = procesar_archivo(ruta, args.salida)
            print(f"✔ {ruta} -> {salida}")
            print(f"   Entradas: {s['total']} | completadas: {s['completadas']} | "
                  f"ya tenían fecha: {s['ya_tenian']} | sin fecha válida: {s['sin_fecha_valida']}")
        except Exception as e:
            print(f"✘ {ruta}: {e}")


if __name__ == "__main__":
    main()
