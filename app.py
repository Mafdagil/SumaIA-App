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

# 1. CONFIGURACIÓN OCR
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="Suma IA - Gestión de Finanzas", layout="wide", page_icon="🏦")

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
        return res[0] if res else None
    except: return None

init_db()

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    /* Intento de forzar color del panel */
    [data-testid="stSidebar"] {
        background-color: #064e3b !important;
        background-image: linear-gradient(180deg, #064e3b 0%, #0891b2 100%) !important;
    }
    [data-testid="stSidebar"] * { color: white !important; }
    
    /* Textos Marca */
    .suma-text { font-size: 48px !important; font-weight: 900 !important; color: #1E3A8A; }
    .ia-text { 
        font-size: 52px !important; font-weight: 900 !important; 
        background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); 
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; 
    }
    .eslogan { color: #0891b2 !important; font-weight: bold; font-style: italic; }
    
    /* Caja de Métricas */
    [data-testid="stMetric"] {
        background-color: #f0f9ff;
        border: 1px solid #bae6fd;
        border-radius: 10px;
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- ENCABEZADO ---
col_logo, col_tit = st.columns([1, 8])
logo_path = "logo_sumaiq.png"
with col_logo:
    if os.path.exists(logo_path): st.image(Image.open(logo_path), width=80)
with col_tit:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="eslogan">Tus gastos y nómina en perfecto orden</p>', unsafe_allow_html=True)

# --- SIDEBAR ---
if 'manual_refs' not in st.session_state: st.session_state['manual_refs'] = []
if 'reset_cnt' not in st.session_state: st.session_state['reset_cnt'] = 0

with st.sidebar:
    st.header("Panel de Control")
    saldo_db = obtener_ultimo_saldo()
    if saldo_db is None:
        m_ini = st.number_input("Saldo Inicial:", value=0.0)
        if st.button("🚀 Iniciar"):
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO finanzas VALUES (?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), 0.0, 0.0, 0.0, m_ini, "Inicio"))
            st.rerun()
    else:
        st.metric("Saldo Actual", f"Bs. {saldo_db:,.2f}")

    st.markdown("---")
    archivos_banco = st.file_uploader("PDF Banco", type=["pdf"], accept_multiple_files=True, key=f"b_{st.session_state.reset_cnt}")
    fotos_recibos = st.file_uploader("Fotos Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True, key=f"i_{st.session_state.reset_cnt}")
    
    if st.button("🗑️ Borrar Todo"):
        if os.path.exists('sumaia_history.db'): os.remove('sumaia_history.db')
        st.session_state['manual_refs'] = []; st.session_state['reset_cnt'] += 1; st.rerun()

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

        # Conciliación OCR
        refs_val = set(st.session_state['manual_refs'])
        if fotos_recibos:
            for foto in fotos_recibos:
                try:
                    txt = pytesseract.image_to_string(Image.open(foto)).upper()
                    nums = re.findall(r'\d{5,}', txt)
                    for n in nums:
                        mask = df['Ref_Limpia'].str.contains(n, na=False)
                        if mask.any(): refs_val.update(df[mask]['Ref_Limpia'].tolist())
                except: continue

        for rv in refs_val:
            df.loc[df['Ref_Limpia'].str.contains(rv, na=False), "Estatus"] = "✅ Conciliado"

        # --- AQUÍ ESTÁ EL CÁLCULO DEL MONTO PENDIENTE ---
        m_pend = df[(df['Estatus'] == "❌ Pendiente") & (df['M_Num'] < 0)]['M_Num'].abs().sum()

        # Mostrar Resultados
        st.markdown("### 📊 Resumen de Cierre")
        c1, c2, c3 = st.columns(3)
        c1.metric("Monto por Justificar", f"Bs. {m_pend:,.2f}", delta="- Faltan Recibos", delta_color="inverse")
        c2.metric("Total Ingresos", f"Bs. {df[df['M_Num']>0]['M_Num'].sum():,.2f}")
        c3.metric("Saldo Final", f"Bs. {df['M_Num'].sum():,.2f}")

        st.markdown("---")
        st.subheader("📝 Detalle de Movimientos")
        st.dataframe(df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].style.apply(
            lambda r: ['background-color: #fef2f2' if r['Estatus'] == "❌ Pendiente" else 'background-color: #f0fdf4']*5, axis=1), 
            use_container_width=True, hide_index=True)

        # Exportación
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as wr:
            df.to_excel(wr, index=False)
        st.download_button("📥 Descargar Excel", output.getvalue(), "Reporte.xlsx", use_container_width=True)
else:
    st.info("Sube los archivos para procesar.")
