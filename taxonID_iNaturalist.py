"""
update_inaturalist_ids.py - Busca taxonID_iNaturalist para especies que no lo tienen
Usa la API de iNaturalist para completar el species_master_ecuador.json
"""
import json
import requests
import time
import os
from pathlib import Path

def search_inaturalist(scientific_name):
    """Busca un taxón en iNaturalist y retorna el taxonID."""
    try:
        url = "https://api.inaturalist.org/v1/taxa"
        params = {
            "q": scientific_name,
            "is_active": "true",
            "per_page": 1
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])
        
        if results:
            # Buscar coincidencia exacta o muy cercana
            for result in results:
                result_name = result.get("name", "")
                if result_name.lower() == scientific_name.lower():
                    return result.get("id", "")
            
            # Si no hay coincidencia exacta, retornar el primer resultado
            return results[0].get("id", "")
        
        return ""
    except Exception as e:
        print(f"⚠️ Error buscando {scientific_name}: {e}")
        return ""

def update_species_master():
    """Actualiza species_master_ecuador.json con taxonID_iNaturalist."""
    master_path = Path("config/paises/species_master_ecuador.json")
    
    if not master_path.exists():
        print(f"❌ No existe {master_path}")
        return
    
    print(f"📖 Cargando {master_path}...")
    with open(master_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    species_list = data.get("species", [])
    total = len(species_list)
    
    print(f"🔍 Procesando {total} especies...")
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for i, species in enumerate(species_list, 1):
        scientific_name = species.get("scientificName", "")
        inat_id = species.get("taxonID_iNaturalist", "")
        
        # Saltar si ya tiene taxonID_iNaturalist
        if inat_id:
            skipped_count += 1
            continue
        
        # Saltar especies especiales (custom:empty, custom:setup, etc.)
        if scientific_name.startswith("custom:") or scientific_name in [
            "Disparo vacío", "No identificado", "Configuración/Setup", "Animal desconocido"
        ]:
            skipped_count += 1
            continue
        
        print(f"[{i}/{total}] Buscando: {scientific_name}...", end=" ")
        
        # Buscar en iNaturalist
        inaturalist_id = search_inaturalist(scientific_name)
        
        if inaturalist_id:
            species["taxonID_iNaturalist"] = str(inaturalist_id)
            updated_count += 1
            print(f"✅ ID: {inaturalist_id}")
        else:
            error_count += 1
            print("❌ No encontrado")
        
        # Rate limit: esperar 1 segundo entre búsquedas
        time.sleep(1)
    
    # Guardar cambios
    print(f"\n💾 Guardando cambios en {master_path}...")
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Resumen:")
    print(f"   - Total especies: {total}")
    print(f"   - Actualizadas: {updated_count}")
    print(f"   - Saltadas (ya tenían ID): {skipped_count}")
    print(f"   - No encontradas: {error_count}")
    print(f"\n📁 Archivo actualizado: {master_path}")

if __name__ == "__main__":
    print("=" * 70)
    print("ACTUALIZAR taxonID_iNaturalist EN species_master_ecuador.json")
    print("=" * 70)
    print()
    print("⚠️  Este script buscará en la API de iNaturalist los IDs faltantes.")
    print("⚠️  Puede tardar varios minutos dependiendo de la cantidad de especies.")
    print("⚠️  Asegúrate de tener conexión a internet.")
    print()
    
    response = input("¿Deseas continuar? (s/n): ").strip().lower()
    if response == "s":
        update_species_master()
    else:
        print("❌ Operación cancelada.")