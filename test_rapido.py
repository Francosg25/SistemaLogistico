import pandas as pd
from modules.outbound import procesar_outbound

def ejecutar_prueba():
    print("1. Generando datos simulados (Mock Data)...")
    
    # Simulamos el DataFrame que normalmente entregaría el módulo de ingesta
    mock_data = {
        'Reference': [
            'FG-R-2208LE26.M46/M45',  # Caso A: Debe extraer M45
            'FG-R-2202LE26.M19',      # Caso B: Debe extraer M19
            'FG-R-2212LE26.M01/M45',  # Caso C: Debe extraer M45 y agrupar con el Caso A
            'REF-SIN-PUNTO'           # Caso Edge: Debe retornar SIN_BU
        ],
        'Gross Weight': [100.0, 200.0, 50.0, 0.0], # Pesos para probar el prorrateo
        'Customer': ['Cliente A', 'Cliente B', 'Cliente A', 'Cliente C'],
        'ADDRESS': ['Direccion 1', 'Direccion 2', 'Direccion 1', 'Direccion 3']
    }
    
    df_mock = pd.DataFrame(mock_data)
    
    print("2. Ejecutando módulo Outbound...")
    try:
        # Inyectamos el DataFrame simulado
        resultados = procesar_outbound(df_mock, costo_fijo=1500.0)
        
        print("\n=== RESULTADO 1: Inferencia y Prorrateo (Detalle) ===")
        columnas_clave = ['Reference', 'BU_Inferred', 'Gross Weight', '%Proportion', 'Calc_Exp']
        print(resultados['detalle'][columnas_clave])
        
        print("\n=== RESULTADO 2: Consolidación Final (Resumen BU) ===")
        print(resultados['resumen_bu'])
        
        print("\n✅ Prueba finalizada con éxito.")
        
    except Exception as e:
        print(f"\n❌ Error durante la ejecución: {e}")

if __name__ == "__main__":
    ejecutar_prueba()