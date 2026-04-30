import os
import pandas as pd
import streamlit as st
import pdfplumber
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import re
import sqlite3
from datetime import datetime
from io import BytesIO

# --- CONFIGURACIÓN ---
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="Suma IA", layout="wide")

# --- BASE DE DATOS ---
def obtener_ultimo_saldo():
    try:
        conn = sqlite3.connect('sumaia_history.db')
        res = conn.execute("SELECT saldo FROM finanzas ORDER BY ROWID DESC LIMIT 1").fetchone()
        conn.close()
        return res[0] if res else 0.0
    except: return 0.0

# --- ESTILO CSS ---
st.markdown("""
    <style>
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #064e3b 0%, #0891b2 100%) !important; }
    [data-testid="stSidebar"] * { color: white !important; font-weight: 600 !important; }
    
    /* Métricas principales */
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700 !important; }
    
    /* Estilo para Monto por Justificar (Rojo) */
    .pendiente-box {
        color: #e11d48;
        font-size: 1.1rem;
        font-weight: 800;
        text-align: center;
        padding: 10px;
        border: 2px solid #e11d48;
        border-radius: 10px;
        background-color: #fff1f2;
        margin-top: 10px;
    }
    
    .suma-text { font-size: 40px; font-weight: 900; color: #1E3A8A; }
    .ia-text { font-size: 44px; font-weight: 900; background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .eslogan { color: #64748b; font-style: italic; margin-top: -15px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- ENCABEZADO ---
c1, c2 = st.columns([1, 10])
with c1:
    if os.path.exists("logo_sumaiq.png"): st.image("logo_sumaiq.png", width=80)
with c2:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="eslogan">Tus gastos y nómina en perfecto orden</p>', unsafe_allow_html=True)

# --- SIDEBAR ---
if 'manual_refs' not in st.session_state: st.session_state['manual_refs'] = []
with st.sidebar:
    st.header("Panel de Control")
    saldo_anterior = obtener_ultimo_saldo()
    st.metric("Saldo Anterior", f"Bs. {saldo_anterior:,.2f}")
    
    arch_pdf = st.file_uploader("Subir PDF Banco", type=["pdf"], accept_multiple_files=True)
    img_recibos = st.file_uploader("Subir Fotos Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    with st.expander("📝 CARGA MANUAL"):
        ref_m = st.text_input("N° Referencia:")
        if st.button("➕ Añadir"):
            if ref_m: st.session_state['manual_refs'].append(re.sub(r'\D', '', ref_m))

# --- PROCESO ---
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

        # --- MEJORA OCR AGRESIVA ---
        refs_val = set(st.session_state['manual_refs'])
        if img_recibos:
            for foto in img_recibos:
                try:
                    img = Image.open(foto).convert('L')
                    img = ImageOps.autocontrast(img)
                    img = ImageEnhance.Sharpness(img).enhance(2.0)
                    # Leemos la imagen normal y luego invertida para maximizar detección
                    txt = pytesseract.image_to_string(img, config='--psm 6').upper()
                    txt += " " + pytesseract.image_to_string(ImageOps.invert(img), config='--psm 6').upper()
                    
                    nums = re.findall(r'\d{4,}', txt) # Busca números de 4+ dígitos
                    for n in nums:
                        mask = df['Ref_Limpia'].str.contains(n, na=False)
                        if mask.any(): refs_val.update(df[mask]['Ref_Limpia'].tolist())
                except: continue

        for rv in refs_val:
            df.loc[df['Ref_Limpia'].str.contains(rv, na=False), "Estatus"] = "✅ Conciliado"

        # --- CÁLCULOS ---
        mask_com = df['Descripción'].str.contains("COMISION|IVA|COM\.|COM ", na=False, case=False)
        t_ing = df[df['M_Num'] > 0]['M_Num'].sum()
        t_com = abs(df[mask_com & (df['M_Num'] < 0)]['M_Num'].sum())
        t_egr = abs(df[~mask_com & (df['M_Num'] < 0)]['M_Num'].sum())
        saldo_final = saldo_anterior + df['M_Num'].sum()
        m_pend = df[(df['Estatus'] == "❌ Pendiente") & (df['M_Num'] < 0)]['M_Num'].abs().sum()

        # --- RESUMEN REORGANIZADO ---
        st.subheader("📊 Resumen de Cierre Financiero")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("INGRESOS", f"Bs. {t_ing:,.2f}")
        c2.metric("EGRESOS", f"Bs. {t_egr:,.2f}")
        c3.metric("COMISIONES", f"Bs. {t_com:,.2f}")
        c4.metric("SALDO TOTAL", f"Bs. {saldo_final:,.2f}")

        # Monto por justificar pequeño y rojo
        st.markdown(f'<div class="pendiente-box">⚠️ MONTO POR JUSTIFICAR: Bs. {m_pend:,.2f}</div>', unsafe_allow_html=True)

        st.markdown("---")
        st.dataframe(df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].style.apply(
            lambda r: ['background-color: #fef2f2' if r['Estatus'] == "❌ Pendiente" else 'background-color: #f0fdf4']*5, axis=1), 
            use_container_width=True, hide_index=True)

        if st.button("💾 Finalizar y Guardar Mes", use_container_width=True):
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO finanzas VALUES (?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), t_ing, t_egr, t_com, saldo_final, "Cierre"))
            st.success("Guardado.")
            st.rerun()
