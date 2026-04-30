import os
import pandas as pd
import streamlit as st
import pdfplumber
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import re
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor # Para leer en paralelo

# --- CONFIGURACIÓN OCR ---
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="Suma IA", layout="wide", page_icon="🏦")

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('sumaia_history.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS cierres 
                 (fecha TEXT, ingresos REAL, egresos REAL, comisiones REAL, saldo REAL, tipo TEXT)''')
    conn.close()

def obtener_ultimo_saldo():
    try:
        conn = sqlite3.connect('sumaia_history.db')
        res = conn.execute("SELECT saldo FROM cierres ORDER BY ROWID DESC LIMIT 1").fetchone()
        conn.close()
        return res[0] if res else 0.0
    except: return 0.0

init_db()

# --- FUNCIÓN DE LECTURA VELOZ (OCR) ---
def leer_recibo_veloz(foto):
    try:
        img = Image.open(foto).convert('L')
        # Reducimos el escalado a 2x (equilibrio entre velocidad y precisión)
        img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        # Una sola pasada con PSM 6 es la más rápida y efectiva para recibos
        txt = pytesseract.image_to_string(img, config='--psm 6').upper()
        return re.findall(r'\d{5,}', txt)
    except:
        return []

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #064e3b 0%, #0891b2 100%) !important; }
    [data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] .streamlit-expanderHeader p {
        color: #FFFFFF !important; font-weight: 600 !important;
    }
    .suma-text { font-size: 42px; font-weight: 900; color: #1E3A8A; line-height: 0.7; }
    .ia-text { font-size: 46px; font-weight: 900; background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .eslogan-text { color: #475569; font-size: 0.9rem; font-style: italic; font-weight: 500; display: block; margin-top: -2px; }
    [data-testid="stMetric"] { background-color: #ffffff !important; border: 1px solid #e2e8f0 !important; border-radius: 12px !important; padding: 12px !important; border-top: 3px solid #10B981 !important; }
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; font-weight: 700 !important; color: #0f172a !important; }
    .pendiente-container { display: flex; justify-content: flex-end; margin: 5px 0; }
    .pendiente-text { color: #b91c1c; font-size: 0.85rem; font-weight: 700; padding: 5px 10px; border: 1px solid #b91c1c; border-radius: 6px; background-color: #fef2f2; }
    </style>
    """, unsafe_allow_html=True)

# --- ENCABEZADO ---
c_log, c_tit = st.columns([0.15, 0.85])
with c_log:
    if os.path.exists("logo_sumaiq.png"): st.image("logo_sumaiq.png", width=80)
with c_tit:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)
    st.markdown('<span class="eslogan-text">Tus gastos y nómina en perfecto orden</span>', unsafe_allow_html=True)

# --- SIDEBAR ---
if 'manual_refs' not in st.session_state: st.session_state['manual_refs'] = []

with st.sidebar:
    st.markdown('<div style="color:white; text-align:center; font-style:italic; border-bottom:1px solid rgba(255,255,255,0.3); padding-bottom:8px; margin-bottom:15px;">Finanzas Inteligentes</div>', unsafe_allow_html=True)
    saldo_acumulado = obtener_ultimo_saldo()
    st.metric("Saldo Anterior", f"Bs. {saldo_acumulado:,.2f}")

    if saldo_acumulado == 0:
        with st.expander("⚙️ CONFIGURACIÓN INICIAL"):
            base = st.number_input("Establecer Saldo Inicial:", value=0.0)
            if st.button("🚀 Cargar Primer Saldo", use_container_width=True):
                conn = sqlite3.connect('sumaia_history.db')
                with conn: conn.execute("INSERT INTO cierres VALUES (?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), 0.0, 0.0, 0.0, base, "INICIAL"))
                st.rerun()

    st.markdown("---")
    arch_pdf = st.file_uploader("📂 Subir PDF Banco", type=["pdf"], accept_multiple_files=True)
    img_rec = st.file_uploader("📸 Subir Fotos Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    with st.expander("📝 CARGA MANUAL DE REFERENCIAS"):
        ref_m = st.text_input("N° Referencia:")
        if st.button("➕ Añadir", use_container_width=True):
            if ref_m: st.session_state['manual_refs'].append(re.sub(r'\D', '', ref_m))

    if st.button("🗑️ REINICIAR TODO", use_container_width=True):
        if os.path.exists('sumaia_history.db'): os.remove('sumaia_history.db')
        st.session_state['manual_refs'] = []; st.rerun()

# --- PROCESAMIENTO ---
if arch_pdf:
    filas = []
    for archivo in arch_pdf:
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

        # --- CONCILIACIÓN EN PARALELO (MÁS RÁPIDA) ---
        refs_val = set(st.session_state['manual_refs'])
        if img_rec:
            with ThreadPoolExecutor() as executor:
                resultados = list(executor.map(leer_recibo_veloz, img_rec))
                for lista_refs in resultados:
                    for n in lista_refs:
                        mask = df['Ref_Limpia'].str.contains(n, na=False)
                        if mask.any(): refs_val.update(df[mask]['Ref_Limpia'].tolist())

        for rv in refs_val:
            df.loc[df['Ref_Limpia'].str.contains(rv, na=False), "Estatus"] = "✅ Conciliado"

        # CÁLCULOS
        ing = df[df['M_Num'] > 0]['M_Num'].sum()
        com = abs(df[df['Descripción'].str.contains("COMISION|IVA", na=False, case=False)]['M_Num'].sum())
        egr = abs(df[(df['M_Num'] < 0) & (~df['Descripción'].str.contains("COMISION|IVA", na=False, case=False))]['M_Num'].sum())
        saldo_f = saldo_acumulado + df['M_Num'].sum()
        pend = df[(df['Estatus'] == "❌ Pendiente") & (df['M_Num'] < 0)]['M_Num'].abs().sum()

        st.markdown("#### Resumen del Periodo")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("INGRESOS", f"Bs. {ing:,.2f}")
        c2.metric("EGRESOS", f"Bs. {egr:,.2f}")
        c3.metric("COMISIONES", f"Bs. {com:,.2f}")
        c4.metric("SALDO FINAL", f"Bs. {saldo_f:,.2f}")

        st.markdown(f'<div class="pendiente-container"><div class="pendiente-text">Por Justificar: Bs. {pend:,.2f}</div></div>', unsafe_allow_html=True)
        
        st.dataframe(df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].style.apply(
            lambda r: ['background-color: #fef2f2' if r['Estatus'] == "❌ Pendiente" else 'background-color: #f0fdf4']*5, axis=1), 
            use_container_width=True, hide_index=True)

        if st.button("💾 CERRAR MES Y GUARDAR", use_container_width=True):
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO cierres VALUES (?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), ing, egr, com, saldo_f, "CIERRE"))
            st.success("Guardado."); st.rerun()

