"""
scripts/generar_maestro_bu_sea.py
═══════════════════════════════════════════════════════════════
Genera src/config/maestro_bu_sea.json desde la hoja MAESTRO_BU_SEA.

🆕 Versión interactiva: detecta automáticamente los .xlsx
   de la carpeta y te pregunta cuál usar.
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import json
from pathlib import Path

HOJA = "MAESTRO_BU_SEA"
SALIDA_JSON = "src/config/maestro_bu_sea.json"


def elegir_archivo() -> str:
    """Detecta los .xlsx en la carpeta actual y deja al usuario elegir uno."""
    archivos = sorted(Path(".").glob("*.xlsx"))
    
    if not archivos:
        print("❌ No se encontraron archivos .xlsx en esta carpeta.")
        print(f"   Carpeta actual: {Path('.').resolve()}")
        exit(1)
    
    print("\n📂 Archivos Excel encontrados en esta carpeta:")
    print("─" * 70)
    for i, archivo in enumerate(archivos, 1):
        tamano_mb = archivo.stat().st_size / (1024 * 1024)
        print(f"   {i}. {archivo.name}  ({tamano_mb:.1f} MB)")
    print("─" * 70)
    
    while True:
        try:
            opcion = input(
                f"\n👉 Escribe el número del archivo que TIENE la hoja '{HOJA}': "
            ).strip()
            idx = int(opcion) - 1
            if 0 <= idx < len(archivos):
                return str(archivos[idx])
            else:
                print(f"⚠️ Número fuera de rango. Elige entre 1 y {len(archivos)}.")
        except ValueError:
            print("⚠️ Por favor escribe solo un número.")


def main():
    archivo_excel = elegir_archivo()
    
    print(f"\n📂 Archivo elegido: {archivo_excel}")
    print(f"📑 Hoja:            {HOJA}")
    
    # ─── TABLA 1: Item Code → BU (filas 7+, columnas C y D) ───
    try:
        df_items = pd.read_excel(
            archivo_excel,
            sheet_name=HOJA,
            header=None,
            usecols="C:D",
            skiprows=6,    # Saltar hasta fila 7
            nrows=400,     # Rango amplio para captar todos
        )
    except Exception as e:
        print(f"\n❌ Error leyendo la hoja '{HOJA}': {e}")
        print(f"   Verifica que el archivo TENGA esa hoja.")
        exit(1)
    
    df_items.columns = ["Item Code", "BU"]
    df_items = df_items.dropna(subset=["Item Code", "BU"])
    df_items["Item Code"] = df_items["Item Code"].astype(str).str.strip()
    df_items["BU"] = df_items["BU"].astype(str).str.strip()
    df_items = df_items[df_items["Item Code"] != ""]
    df_items = df_items[df_items["BU"] != ""]
    df_items = df_items[df_items["BU"] != "SIN_BU"]
    df_items = df_items.drop_duplicates(subset=["Item Code"], keep="first")
    
    mapa_items = dict(zip(df_items["Item Code"], df_items["BU"]))
    
    # ─── TABLA 3: Subinventory → BU (filas 16+, columnas H y I) ───
    try:
        df_subinv = pd.read_excel(
            archivo_excel,
            sheet_name=HOJA,
            header=None,
            usecols="H:I",
            skiprows=15,
            nrows=50,
        )
        df_subinv.columns = ["Subinventory", "BU"]
        df_subinv = df_subinv.dropna(subset=["Subinventory", "BU"])
        df_subinv["Subinventory"] = df_subinv["Subinventory"].astype(str).str.strip()
        df_subinv["BU"] = df_subinv["BU"].astype(str).str.strip()
        df_subinv = df_subinv[df_subinv["Subinventory"] != ""]
        df_subinv = df_subinv[df_subinv["BU"] != ""]
        df_subinv = df_subinv[df_subinv["BU"] != "AMBIGUO"]  # Excluir multi-BU
        df_subinv = df_subinv.drop_duplicates(subset=["Subinventory"], keep="first")
        mapa_subinv = dict(zip(df_subinv["Subinventory"], df_subinv["BU"]))
    except Exception as e:
        print(f"⚠️ Sin tabla fallback de Subinventory: {e}")
        mapa_subinv = {}
    
    # ─── Guardar JSON ───
    salida = {
        "version": "1.0",
        "fecha_actualizacion": "2026-05-18",
        "archivo_origen": archivo_excel,
        "items_count": len(mapa_items),
        "subinv_count": len(mapa_subinv),
        "mapa_item_code_a_bu": mapa_items,
        "mapa_subinventory_a_bu": mapa_subinv,
    }
    
    Path(SALIDA_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA_JSON, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ {SALIDA_JSON} generado:")
    print(f"   • {len(mapa_items)} items mapeados")
    print(f"   • {len(mapa_subinv)} subinventories de fallback")
    print(f"\n📊 BUs encontrados: {sorted(set(mapa_items.values()))}")


if __name__ == "__main__":
    main()