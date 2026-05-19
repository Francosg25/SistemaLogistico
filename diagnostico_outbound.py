"""
Diagnóstico exhaustivo de OUTBOUND para identificar qué waybill desaparece.
"""
import pandas as pd
from src.ingesta.lector_excel import cargar_outbound

# 1. Cargar igual que lo hace Streamlit
df, df_costos = cargar_outbound("REPORTE EXPO W19.xlsx")

print("=" * 70)
print("📊 1. DATOS LEÍDOS POR cargar_outbound()")
print("=" * 70)
print(f"Filas totales: {len(df)}")
print(f"Columnas: {list(df.columns)[:20]}")
print()

# 2. Listar todos los waybills únicos
print("=" * 70)
print("📋 2. WAYBILLS ÚNICOS Y CONTEO DE ITEMS")
print("=" * 70)
conteo = df.groupby("Reference").agg(
    items=("Reference", "count"),
    peso_total=("Peso Bruto", "sum"),
).sort_index()
print(conteo.to_string())
print()
print(f"Total waybills únicos: {df['Reference'].nunique()}")
print(f"Total items: {len(df)}")
print(f"Suma pesos: {df['Peso Bruto'].sum():,.2f}")
print()

# 3. Listar TODOS los items con su waybill, BU detectado y peso
print("=" * 70)
print("🔍 3. PRIMERAS 20 FILAS (con BU y peso)")
print("=" * 70)
cols_mostrar = ["Reference", "Item", "Peso Bruto"]
if "BU" in df.columns:
    cols_mostrar.append("BU")
print(df[cols_mostrar].head(20).to_string(index=False))
print()

# 4. Aplicar el procesador
print("=" * 70)
print("⚙️ 4. PROCESANDO con procesar_outbound()...")
print("=" * 70)
from src.procesamiento.procesar_outbound import procesar_outbound
resultado = procesar_outbound(df, costo_fijo=1500, df_costos=df_costos)

print()
print("📊 RESULTADOS:")
print(f"  Items procesados:    {resultado.metricas['total_items']}")
print(f"  Waybills únicos:     {resultado.metricas['total_waybills']}")
print(f"  Costo total:         ${resultado.metricas['costo_total_calculado']:,.2f}")
print(f"  Validación OK:       {resultado.metricas['validacion_ok']}")
print()
print("📋 RESUMEN POR BU:")
print(resultado.resumen_bu.to_string(index=False))
print()
print("📦 WAYBILLS PROCESADOS:")
print(resultado.resumen_waybills[
    ["Waybill Number", "BU Asignado", "# Items", "Peso Total (Kgs)", "Fix Cost", "Total Amount"]
].to_string(index=False))