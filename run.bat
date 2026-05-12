@echo off
echo ============================================
echo  CONSOLIDACION LOGISTICA - INICIANDO...
echo ============================================

REM Verificar si existe el entorno virtual
if not exist "venv\" (
    echo Creando entorno virtual...
    python -m venv venv
)

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Instalar dependencias si es la primera vez
if not exist "venv\installed.flag" (
    echo Instalando dependencias...
    pip install -r requirements.txt
    type nul > venv\installed.flag
)

REM Ejecutar la aplicación (UI Streamlit)
echo Lanzando interfaz...
streamlit run src/ui/app.py

pause