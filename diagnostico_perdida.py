"""
Diagnóstico: descubrir EXACTAMENTE dónde se pierden 12 filas
entre el archivo raw (71 filas) y lo que llega al procesador (59 filas).
"""
import pandas as pd
from src.ingesta.normalizador import (
    eliminar_filas_vacias,
    eliminar_filas_totales,
)

# Paso 0: Leer crudo
df = pd.read_excel("REPORTE EXPO W19.xlsx", sheet_name="1", header=1)
df.columns = [str(c).strip() for c in df.columns]
print(f"📊 PASO 0 — Filas raw: {len(df)}")

# Paso 1: Después de aplicar mapeo de columnas
from src.ingesta.mapeo_columnas import mapear_columnas_dataframe
df_mapped, _, _ = mapear_columnas_dataframe(df, "outbound", usar_nombres_legacy=True)
print(f"📊 PASO 1 — Filas tras mapeo: {len(df_mapped)}")

# Paso 2: Aplicar eliminar_filas_vacias con criticas
print(f"\n🔍 PASO 2 — Aplicar eliminar_filas_vacias(['Reference', 'Item'])")
print(f"   Antes: {len(df_mapped)}")
df_v1 = eliminar_filas_vacias(df_mapped.copy(), ["Reference", "Item"])
print(f"   Después: {len(df_v1)}  → ELIMINADAS: {len(df_mapped) - len(df_v1)}")

# Paso 3: Aplicar eliminar_filas_totales
print(f"\n🔍 PASO 3 — Aplicar eliminar_filas_totales('Reference')")
print(f"   Antes: {len(df_v1)}")
df_v2 = eliminar_filas_totales(df_v1.copy(), "Reference")
print(f"   Después: {len(df_v2)}  → ELIMINADAS: {len(df_v1) - len(df_v2)}")

# Paso 4: Filtrar por peso > 0
print(f"\n🔍 PASO 4 — Filtrar Peso Bruto > 0")
print(f"   Antes: {len(df_v2)}")
df_v3 = df_v2[df_v2["Peso Bruto"].notna() & (df_v2["Peso Bruto"] > 0)]
print(f"   Después: {len(df_v3)}  → ELIMINADAS: {len(df_v2) - len(df_v3)}")

# Comparar con expected
print(f"\n{'='*70}")
print(f"📊 RESULTADO FINAL: {len(df_v3)} filas")
print(f"   Esperado: 71 filas (todas las del raw)")
print(f"   Diferencia: {71 - len(df_v3)}")
print(f"{'='*70}")

# Ver qué filas se perdieron (comparando contra raw original)
if len(df_v3) < 71:
    indices_finales = set(df_v3.index)
    indices_originales = set(df_mapped.index)
    perdidos = indices_originales - indices_finales
    print(f"\n🔴 Filas PERDIDAS (índices): {sorted(perdidos)[:20]}")
    
    if perdidos:
        print(f"\n📋 Contenido de las primeras 5 filas perdidas:")
        cols_mostrar = ["Reference", "Item", "Peso Bruto"]
        # Agregar Waybill Number si existe
        if "Waybill Number" in df_mapped.columns:
            cols_mostrar.insert(0, "Waybill Number")
        cols_mostrar = [c for c in cols_mostrar if c in df_mapped.columns]
        print(df_mapped.loc[list(perdidos)[:5], cols_mostrar].to_string())