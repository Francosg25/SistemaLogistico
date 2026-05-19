"""
Diagnóstico: encontrar el peso real de las filas con 'Peso Bruto'=0.
Buscar en las otras columnas de peso del archivo.
"""
import pandas as pd

df = pd.read_excel("REPORTE EXPO W19.xlsx", sheet_name="1", header=1)
df.columns = [str(c).strip() for c in df.columns]

# Listar TODAS las columnas que contienen "weight" o "peso"
cols_peso = [c for c in df.columns if "weight" in c.lower() or "peso" in c.lower()]
print("📊 Columnas de peso en el archivo:")
for c in cols_peso:
    n_nonzero = (df[c].fillna(0) > 0).sum()
    suma = df[c].fillna(0).sum()
    print(f"   • {c!r:35s} → {n_nonzero:3d} filas con valor > 0 | Suma: {suma:,.2f}")

print()
print("🔍 Inspección de las 12 filas problemáticas (índices: [1,2,3,19,20,21,31,32,51,52,68,69]):")
indices_perdidos = [1, 2, 3, 19, 20, 21, 31, 32, 51, 52, 68, 69]

cols_mostrar = ["Waybill Number"] + cols_peso
df_perdidos = df.iloc[indices_perdidos][cols_mostrar]
print(df_perdidos.to_string())