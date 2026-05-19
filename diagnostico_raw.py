"""
Diagnóstico: Ver qué hay en el archivo ANTES de cualquier limpieza.
"""
import pandas as pd

# Leer el archivo CRUDO, sin tocar nada
df_raw = pd.read_excel("REPORTE EXPO W19.xlsx", sheet_name="1", header=1)
df_raw.columns = [str(c).strip() for c in df_raw.columns]

print("=" * 70)
print("📊 ARCHIVO CRUDO (sin filtros)")
print("=" * 70)
print(f"Total filas raw: {len(df_raw)}")
print()

# Buscar la columna de waybill
col_waybill = None
for c in df_raw.columns:
    if "waybill" in c.lower():
        col_waybill = c
        break

if col_waybill:
    print(f"Columna Waybill: '{col_waybill}'")
    print()
    print("Conteo de filas RAW por Waybill:")
    print(df_raw[col_waybill].value_counts(dropna=False).to_string())

print()
print("=" * 70)
print("📋 Filas donde Waybill está VACÍO/NaN (las que tu lector pierde)")
print("=" * 70)
if col_waybill:
    mask_vacio = df_raw[col_waybill].isna() | (df_raw[col_waybill].astype(str).str.strip() == "")
    df_vacio = df_raw[mask_vacio]
    print(f"Filas con Waybill vacío: {len(df_vacio)}")
    
    # Mostrar qué columnas SÍ tienen valor en esas filas
    cols_mostrar = []
    for c in ["Item", "Gross Weight (Kgs)", "Pieces", "Customer", "Container Number"]:
        if c in df_vacio.columns:
            cols_mostrar.append(c)
    
    if len(df_vacio) > 0 and cols_mostrar:
        print(f"\nPrimeras 10 filas con Waybill vacío (pero con otros datos):")
        print(df_vacio[cols_mostrar].head(10).to_string())