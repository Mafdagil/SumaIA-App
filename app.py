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

# --- CONFIGURACIÓN OCR ---
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="Suma IA", layout="wide", page_icon="🏦")

# --- BASE DE DATOS (Mantenemos local por ahora hasta conectar Google) ---
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

# --- ESTILO VISUAL (CONTRASTE Y DISEÑO) ---
st.markdown("""
    <style>
    /* PANEL LATERAL */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #064e3b 0%, #0891b2 100%) !important;
    }
    /* Letras blancas puras sobre el fondo de color */
    [data-testid="stSidebar"] .stMarkdown p, 
    [data-testid="stSidebar"] label, 
    [data-testid="stSidebar"] h2 {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    /* Frase Elegante */
    .frase-ia {
        color: #FFFFFF; font-size: 1.2rem; font-style: italic;
        text-align: center; border-bottom: 1px solid rgba(255,255,255,0.3);
        padding-bottom: 15px; margin-bottom: 20px; font-weight: 300;
    }

    /* CUERPO PRINCIPAL */
    .suma-text { font-size: 45px; font-weight: 900; color: #1E3A8A; line-height: 1; }
    .ia-text { font-size: 50px; font-weight: 900; background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .eslogan-container { margin-top: -10px; margin-bottom: 20px; }
    .eslogan-text { color: #475569; font-size: 1rem; font-style: italic; font-weight: 500; }

    /* Monto por justificar pequeño y rojo */
    .pendiente-text {
        color: #b91c1c; font-size: 0.95rem; font-weight: 700;
        text-align: center; padding: 8px; border: 1.5px solid #b91c1c;
        border-radius: 8px; background-color: #fef2f2; width: fit-content; margin: 10px auto;
    }
    </style>
    """, unsafe_allow_html=True)

# --- ENCABEZADO ---
c_log, c_tit = st.columns([1, 9])
with c_log:
    if os.path.exists("logo_sumaiq.png"): st.image("logo_sumaiq.png", width=85)
with c_tit:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="eslogan-container"><span class="eslogan-text">Tus gastos y nómina en perfecto orden</span></div>', unsafe_allow_html=True)

# --- SIDEBAR (PANEL DE CONTROL) ---
if 'manual_refs' not in st.session_state: st.session_state['manual_refs'] = []

with st.sidebar:
    st.markdown('<div class="frase-ia">Finanzas Inteligentes</div>', unsafe_allow_html=True)
    
    saldo_acumulado = obtener_ultimo_saldo()
    st.metric("Saldo Anterior Acumulado", f"Bs. {saldo_acumulado:,.2f}")

    if saldo_acumulado == 0:
        st.markdown("### ⚙️ Configuración Inicial")
        base = st.number_input("Saldo Inicial de Cuenta:", value=0.0)
        if st.button("🚀 Cargar Primer Saldo", use_container_width=True):
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO cierres VALUES (?,?,?,?,?,?)", 
                                   (datetime.now().strftime("%Y-%m-%d %H:%M"), 0.0, 0.0, 0.0, base, "INICIAL"))
            st.rerun()

    st.markdown("---")
    arch_pdf = st.file_uploader("📂 Subir PDF Banco", type=["pdf"], accept_multiple_files=True)
    img_rec = st.file_uploader("📸 Subir Fotos Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    st.markdown("---")
    ref_m = st.text_input("N° Referencia Manual:")
    if st.button("➕ Añadir Referencia", use_container_width=True):
        if ref_m: st.session_state['manual_refs'].append(re.sub(r'\D', '', ref_m))

    if st.button("🗑️ REINICIAR TODO", use_container_width=True):
        if os.path.exists('sumaia_history.db'): os.remove('sumaia_history.db')
        st.session_state['manual_refs'] = []
        st.rerun()

# --- CUERPO PRINCIPAL ---
tab1, tab2 = st.tabs(["📊 Conciliación Mensual", "📅 Historial Anual"])

with tab1:
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

            # OCR AGRESIVO (Doble lectura)
            refs_val = set(st.session_state['manual_refs'])
            if img_rec:
                for foto in img_rec:
                    try:
                        img = Image.open(foto).convert('L')
                        img = ImageOps.autocontrast(img)
                        # Lectura normal e invertida para no fallar
                        txt = pytesseract.image_to_string(img, config='--psm 6').upper()
                        txt += " " + pytesseract.image_to_string(ImageOps.invert(img), config='--psm 6').upper()
                        
                        nums = re.findall(r'\d{4,}', txt)
                        for n in nums:
                            mask = df['Ref_Limpia'].str.contains(n, na=False)
                            if mask.any(): refs_val.update(df[mask]['Ref_Limpia'].tolist())
                    except: continue

            for rv in refs_val:
                df.loc[df['Ref_Limpia'].str.contains(rv, na=False), "Estatus"] = "✅ Conciliado"

            # RESUMEN (Orden: Ingresos, Egresos, Comisiones, Saldo)
            mask_com = df['Descripción'].str.contains("COMISION|IVA|COM\.|COM ", na=False, case=False)
            ing = df[df['M_Num'] > 0]['M_Num'].sum()
            com = abs(df[mask_com & (df['M_Num'] < 0)]['M_Num'].sum())
            egr = abs(df[~mask_com & (df['M_Num'] < 0)]['M_Num'].sum())
            nuevo_saldo = saldo_acumulado + df['M_Num'].sum()
            pend = df[(df['Estatus'] == "❌ Pendiente") & (df['M_Num'] < 0)]['M_Num'].abs().sum()

            st.subheader("📋 Resumen del Periodo")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("INGRESOS", f"Bs. {ing:,.2f}")
            c2.metric("EGRESOS", f"Bs. {egr:,.2f}")
            c3.metric("COMISIONES", f"Bs. {com:,.2f}")
            c4.metric("SALDO FINAL", f"Bs. {nuevo_saldo:,.2f}")

            # Monto por justificar pequeño y rojo
            st.markdown(f'<div class="pendiente-text">Monto por Justificar: Bs. {pend:,.2f}</div>', unsafe_allow_html=True)
            
            st.dataframe(df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].style.apply(
                lambda r: ['background-color: #fef2f2' if r['Estatus'] == "❌ Pendiente" else 'background-color: #f0fdf4']*5, axis=1), 
                use_container_width=True, hide_index=True)

            if st.button("💾 CERRAR MES Y GUARDAR HISTORIAL", use_container_width=True):
                conn = sqlite3.connect('sumaia_history.db')
                with conn: conn.execute("INSERT INTO cierres VALUES (?,?,?,?,?,?)", 
                                       (datetime.now().strftime("%Y-%m-%d %H:%M"), ing, egr, com, nuevo_saldo, "CIERRE"))
                st.success("Cierre guardado correctamente.")
                st.rerun()

with tab2:
    st.subheader("📚 Historial de Movimientos Guardados")
    try:
        conn = sqlite3.connect('sumaia_history.db')
        hist_df = pd.read_sql_query("SELECT * FROM cierres", conn)
        conn.close()
        if not hist_df.empty:
            st.dataframe(hist_df, use_container_width=True, hide_index=True)
            st.markdown("---")
            st.write(f"📊 **Resumen Anual:** Ingresos totales de Bs. {hist_df['ingresos'].sum():,.2f}")
        else: st.info("No hay datos guardados todavía.")
    except: st.write("Historial listo.")
