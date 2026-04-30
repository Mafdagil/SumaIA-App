import os
import pandas as pd
import streamlit as st
import pdfplumber
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import re
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Suma IA", layout="wide")

# --- CONEXIÓN PERMANENTE (GOOGLE SHEETS) ---
# En Streamlit Cloud, esto se configura en "Secrets"
url_sheet = "TU_URL_DE_GOOGLE_SHEETS_AQUI" # Reemplaza con tu link
conn = st.connection("gsheets", type=GSheetsConnection)

def guardar_en_nube(datos):
    # Esta función añade una fila al final de tu Google Sheet
    try:
        existente = conn.read(spreadsheet=url_sheet)
        nuevo_df = pd.concat([existente, pd.DataFrame([datos])], ignore_index=True)
        conn.update(spreadsheet=url_sheet, data=nuevo_df)
        return True
    except:
        # Si la hoja está vacía, crea la primera fila
        conn.update(spreadsheet=url_sheet, data=pd.DataFrame([datos]))
        return True

def obtener_historial():
    try:
        return conn.read(spreadsheet=url_sheet)
    except:
        return pd.DataFrame()

# --- ESTILO CSS ---
st.markdown("""
    <style>
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #064e3b 0%, #0891b2 100%) !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    [data-testid="stSidebar"] input { color: #000000 !important; }
    .suma-text { font-size: 45px; font-weight: 900; color: #1E3A8A; line-height: 1; }
    .ia-text { font-size: 50px; font-weight: 900; background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .eslogan-text { color: #475569; font-size: 1.1rem; font-style: italic; font-weight: 500; }
    .pendiente-box { color: #b91c1c; font-weight: 700; text-align: center; padding: 10px; border: 1px solid #b91c1c; border-radius: 8px; background-color: #fef2f2; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- ENCABEZADO ---
c_log, c_tit = st.columns([1, 9])
with c_log:
    if os.path.exists("logo_sumaiq.png"): st.image("logo_sumaiq.png", width=85)
with c_tit:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="margin-top:-10px;"><span class="eslogan-text">Tus gastos y nómina en perfecto orden</span></div>', unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div style="color:white; font-style:italic; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:10px; margin-bottom:20px;">Finanzas Inteligentes</div>', unsafe_allow_html=True)
    
    historial = obtener_historial()
    saldo_acumulado = historial['saldo'].iloc[-1] if not historial.empty else 0.0
    st.metric("Saldo Real en Nube", f"Bs. {saldo_acumulado:,.2f}")

    st.markdown("---")
    arch_pdf = st.file_uploader("📂 PDF Banco", type=["pdf"], accept_multiple_files=True)
    img_rec = st.file_uploader("📸 Fotos Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    if st.button("🗑️ REINICIAR TODO"):
        # Cuidado: Esto debería limpiar la hoja de Google
        conn.update(spreadsheet=url_sheet, data=pd.DataFrame(columns=['fecha','ingresos','egresos','comisiones','saldo','tipo']))
        st.rerun()

# --- CUERPO ---
t1, t2 = st.tabs(["📊 Conciliación", "🔍 Buscador Histórico"])

with t1:
    if arch_pdf:
        # ... (Aquí va tu misma lógica de pdfplumber y OCR que ya tienes)
        # Al final, el botón de guardado cambia:
        if st.button("💾 GUARDAR CIERRE PERMANENTE"):
            datos_cierre = {
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "ingresos": ing,
                "egresos": egr,
                "comisiones": com,
                "saldo": nuevo_saldo,
                "tipo": "CIERRE"
            }
            if guardar_en_nube(datos_cierre):
                st.success("✅ ¡Guardado en tu Google Sheets!")
                st.rerun()

with t2:
    st.subheader("Buscador de Reportes")
    if not historial.empty:
        # Filtros elegantes
        historial['fecha'] = pd.to_datetime(historial['fecha'])
        anio_sel = st.selectbox("Selecciona Año", historial['fecha'].dt.year.unique())
        
        df_filtrado = historial[historial['fecha'].dt.year == anio_sel]
        st.dataframe(df_filtrado, use_container_width=True)
        
        # Resumen Anual
        st.write(f"📈 Total Ingresos {anio_sel}: **Bs. {df_filtrado['ingresos'].sum():,.2f}**")
        st.write(f"📉 Total Egresos {anio_sel}: **Bs. {df_filtrado['egresos'].sum():,.2f}**")
    else:
        st.info("No hay datos guardados en la nube todavía.")
