import os
import pandas as pd
import streamlit as st
import pdfplumber
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import sqlite3
from datetime import datetime
from io import BytesIO

# Configuración OCR para Nube (Linux) y Local (Windows)
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="Suma IA", layout="wide")

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('sumaia_history.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS finanzas 
                 (fecha TEXT, ingresos REAL, egresos REAL, comisiones REAL, saldo REAL, notas TEXT)''')
    conn.close()

def obtener_ultimo_saldo():
    try:
        conn = sqlite3.connect('sumaia_history.db')
        res = conn.execute("SELECT saldo FROM finanzas ORDER BY ROWID DESC LIMIT 1").fetchone()
        conn.close()
        return res[0] if res else 0.0
    except: return 0.0

init_db()

# --- ESTILO VISUAL ELEGANTE ---
st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-image: linear-gradient(180deg, #064e3b 0%, #0891b2 100%) !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    
    /* Números de métricas más pequeños y elegantes */
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 600 !important; color: #1e293b !important; }
    [data-testid="stMetricLabel"] { font-size: 0.9rem !important; text-transform: uppercase; letter-spacing: 1px; }
    
    .suma-text { font-size: 40px !important; font-weight: 900; color: #1E3A8A; }
    .ia-text { font-size: 44px !important; font-weight: 900; background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    </style>
    """, unsafe_allow_html=True)

# --- ENCABEZADO ---
col1, col2 = st.columns([1, 5])
with col1:
    if os.path.exists("logo_sumaiq.png"): st.image("logo_sumaiq.png", width=80)
with col2:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)

# --- SIDEBAR ---
if 'manual_refs' not in st.session_state: st.session_state['manual_refs'] = []

with st.sidebar:
    st.header("Control de Cierre")
    saldo_anterior = obtener_ultimo_saldo()
    st.metric("Saldo Anterior Acumulado", f"Bs. {saldo_anterior:,.2f}")
    
    if saldo_anterior == 0:
        nuevo_inicial = st.number_input("Establecer Saldo Inicial (Bs.):", value=0.0)
        if st.button("🚀 Cargar Saldo"):
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO finanzas VALUES (?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), 0.0, 0.0, 0.0, nuevo_inicial, "Saldo Inicial"))
            st.rerun()

    st.markdown("---")
    archivos_banco = st.file_uploader("Subir PDF Banco", type=["pdf"], accept_multiple_files=True)
    fotos_recibos = st.file_uploader("Subir Fotos Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    with st.expander("📝 CARGA MANUAL"):
        ref_input = st.text_input("N° Referencia:")
        if st.button("Añadir Referencia"):
            if ref_input: st.session_state['manual_refs'].append(re.sub(r'\D', '', ref_input))
            st.success("Referencia añadida")

    if st.button("🗑️ Reiniciar Historial"):
        if os.path.exists('sumaia_history.db'): os.remove('sumaia_history.db')
        st.session_state['manual_refs'] = []
        st.rerun()

# --- PROCESAMIENTO ---
if archivos_banco:
    filas = []
    for archivo in archivos_banco:
        with pdfplumber.open(archivo) as pdf:
            for page in pdf.pages:
                tabla = page.extract_table()
                if tabla:
                    for fila in tabla:
                        if fila and len(fila) >= 5 and any(c.isdigit() for c in str(fila)):
                            if "Fecha" not in str(fila): filas.append(fila[:5])
    
    if filas:
        df = pd.DataFrame(filas, columns=["Fecha", "Referencia", "Descripción", "Monto", "Balance"])
        
        def limpiar_m(v):
            if not v: return 0.0
            s = str(v).strip().upper().replace('BS.', '').replace(' ', '')
            if ',' in s and '.' in s: s = s.replace('.', '')
            s = s.replace(',', '.')
            return pd.to_numeric(re.sub(r'[^\d.]', '', s), errors='coerce') or 0.0
        
        df['M_Num'] = df['Monto'].apply(lambda x: -limpiar_m(x) if '-' in str(x) else limpiar_m(x))
        df['Ref_Limpia'] = df['Referencia'].astype(str).str.replace(r'\D', '', regex=True)
        df["Estatus"] = "❌ Pendiente"

        # Conciliación con OCR Mejorado
        refs_val = set(st.session_state['manual_refs'])
        if fotos_recibos:
            for foto in fotos_recibos:
                try:
                    img = Image.open(foto).convert('L')
                    img = ImageEnhance.Contrast(img).enhance(2.0) # Mejora lectura
                    txt = pytesseract.image_to_string(img, config='--psm 6').upper()
                    nums = re.findall(r'\d{5,}', txt)
                    for n in nums:
                        mask = df['Ref_Limpia'].str.contains(n, na=False)
                        if mask.any(): refs_val.update(df[mask]['Ref_Limpia'].tolist())
                except: continue

        for rv in refs_val:
            df.loc[df['Ref_Limpia'].str.contains(rv, na=False), "Estatus"] = "✅ Conciliado"

        # Totales
        t_ing = df[df['M_Num'] > 0]['M_Num'].sum()
        t_egr = abs(df[df['M_Num'] < 0]['M_Num'].sum())
        # El Saldo Final considera el Saldo Anterior Acumulado
        saldo_banco_actual = df['M_Num'].sum()
        saldo_total_sistema = saldo_anterior + saldo_banco_actual
        m_pend = df[(df['Estatus'] == "❌ Pendiente") & (df['M_Num'] < 0)]['M_Num'].abs().sum()

        # --- RESULTADOS ---
        st.subheader("📊 Resumen de Cierre Financiero")
        c1, c2, c3 = st.columns(3)
        c1.metric("Por Justificar", f"Bs. {m_pend:,.2f}", "Faltan Recibos", delta_color="inverse")
        c2.metric("Total Ingresos", f"Bs. {t_ing:,.2f}")
        c3.metric("Saldo Acumulado Final", f"Bs. {saldo_total_sistema:,.2f}")

        st.markdown("---")
        st.dataframe(df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].style.apply(
            lambda r: ['background-color: #fef2f2' if r['Estatus'] == "❌ Pendiente" else 'background-color: #f0fdf4']*5, axis=1), 
            use_container_width=True, hide_index=True)

        if st.button("💾 Guardar y Acumular Saldo para Siguiente Mes"):
            conn = sqlite3.connect('sumaia_history.db')
            with conn:
                conn.execute("INSERT INTO finanzas VALUES (?,?,?,?,?,?)", 
                            (datetime.now().strftime("%Y-%m-%d %H:%M"), t_ing, t_egr, 0.0, saldo_total_sistema, "Cierre Mensual"))
            st.success("✅ Saldo acumulado correctamente en el historial.")
            st.rerun()
