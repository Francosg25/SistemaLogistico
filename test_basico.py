"""
═══════════════════════════════════════════════════════════════
TEST_BASICO.PY — Diagnóstico + Prueba de Cascada de BU
═══════════════════════════════════════════════════════════════
"""
import sys
from pathlib import Path
import pandas as pd

from src.utils.config_loader import get_config
from src.ingesta.detector_archivo import detectar_tipo_archivo, detectar_fila_header
from src.ingesta.mapeo_columnas import aplicar_mapeo
from src.reglas.inferir_bu import inferir_bu


# ════════════════════════════════════════════════════════════
# 1) CONFIG
# ════════════════════════════════════════════════════════════
print("=" * 70)
print("🔍 PASO 1 — CONFIG")
print("=" * 70)
cfg = get_config()
print(f"✅ Config: {cfg.ruta}")
print(f"   SEA=${cfg.get('costos.sea.valor')} | "
      f"LAND=${cfg.get('costos.land.valor')} | "
      f"OUTBOUND=${cfg.get('costos.outbound.valor')}")
print()


# ════════════════════════════════════════════════════════════
# 2) DETECTAR ARCHIVO
# ════════════════════════════════════════════════════════════
ARCHIVO = "REPORTE EXPO W19.xlsx"   # Cambia por tu archivo

print("=" * 70)
print(f"🔍 PASO 2 — DETECCIÓN DE '{ARCHIVO}'")
print("=" * 70)

if not Path(ARCHIVO).exists():
    print(f"🔴 ARCHIVO NO EXISTE: {ARCHIVO}")
    print(f"   Archivos disponibles:")
    for f in Path.cwd().glob("*.xlsx"):
        print(f"     • {f.name}")
    sys.exit(1)

resultado = detectar_tipo_archivo(ARCHIVO)
print(f"✅ Tipo:       {resultado.tipo}")
print(f"   Confianza:  {resultado.confianza:.0%}")
print(f"   Hoja:       {resultado.hoja_elegida}")
print(f"   Fila header: {resultado.fila_header}")

if resultado.tipo == "desconocido":
    sys.exit(1)
print()


# ════════════════════════════════════════════════════════════
# 3) LEER + MAPEAR + INFERIR BU
# ════════════════════════════════════════════════════════════
print("=" * 70)
print(f"🧠 PASO 3 — CASCADA DE BU (4 NIVELES)")
print("=" * 70)

# Leer la hoja correcta con el header detectado
df = pd.read_excel(
    ARCHIVO,
    sheet_name=resultado.hoja_elegida,
    header=resultado.fila_header,
)
df.columns = [str(c).strip() for c in df.columns]

# Mapeo a columnas canónicas
res_mapeo = aplicar_mapeo(df, resultado.tipo, renombrar=True)
df_canon = res_mapeo.df

# Limpiar filas completamente vacías
df_canon = df_canon.dropna(how="all").reset_index(drop=True)

print(f"📊 DataFrame: {df_canon.shape[0]} filas × {df_canon.shape[1]} cols")
print(f"   Columnas canónicas: {res_mapeo.encontradas}")
print()

# Aplicar cascada de BU
df_con_bu, reporte = inferir_bu(
    df_canon,
    operacion=resultado.tipo,
)

print(f"🎯 RESULTADOS DE LA CASCADA:")
print(f"   Total items:              {reporte.total_items}")
print(f"   ✅ Nivel 1 (Item Code):    {reporte.nivel_1_item_code}")
print(f"   ✅ Nivel 2 (Subinventory): {reporte.nivel_2_subinventory}")
print(f"   ✅ Nivel 3 (Regex):        {reporte.nivel_3_regex}")
print(f"   ✅ Nivel 4 (Miscelaneus):  {reporte.nivel_4_miscelaneus}")
print(f"   🔴 Nivel 4 (SIN_BU):       {reporte.nivel_4_sin_bu}")
print(f"   🔄 Ambiguos resueltos:     {reporte.ambiguos_resueltos}")
print(f"   📈 Cobertura:              {reporte.cobertura_pct}%")
print()

print(f"🏷️ DISTRIBUCIÓN POR BU FINAL:")
for bu, count in sorted(
    reporte.bus_finales.items(), key=lambda x: -x[1]
):
    icono = "🔴" if bu == "SIN_BU" else "🟢"
    print(f"   {icono} {bu:15s}: {count:4d} items")

if reporte.items_sin_bu:
    print(f"\n⚠️ ITEMS SIN BU ({len(reporte.items_sin_bu)} únicos):")
    for item in reporte.items_sin_bu[:10]:
        print(f"     • {item}")
    if len(reporte.items_sin_bu) > 10:
        print(f"     ... y {len(reporte.items_sin_bu) - 10} más")