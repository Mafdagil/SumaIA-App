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

# --- FUNCIONES DE FORMATO ---
def formato_bs(valor):
    try:
        val_num = float(valor)
        num_f = f"{abs(val_num):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"Bs. {num_f}" if val_num >= 0 else f"-Bs. {num_f}"
    except: return "Bs. 0,00"

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

# --- ESTILO VISUAL PREMIUM ---
st.markdown("""
    <style>
    /* Ajustes de página */
    .block-container { padding-top: 1.5rem !important; padding-left: 1.5rem !important; }
    [data-testid="stSidebar"] { background-color: #1a1c23 !important; }
    
    /* Logotipo Suma IA a la izquierda */
    .suma-text { font-size: 45px !important; font-weight: 900 !important; color: #1E3A8A; letter-spacing: -2px; }
    .ia-text { 
        font-size: 50px !important; font-weight: 900 !important; 
        background: linear-gradient(90deg, #10B981 0%, #06B6D4 100%); 
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-left: 5px;
    }
    .eslogan { font-size: 16px !important; color: #64748b !important; font-style: italic; margin-top: -12px; }

    /* TARJETAS MÉTRICAS COMPACTAS */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-top: 4px solid #10B981;
        border-radius: 12px;
        padding: 12px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .metric-label { font-size: 10px; color: #64748b; text-transform: uppercase; font-weight: 700; margin-bottom: 2px; }
    .metric-value { font-size: 17px; font-weight: 800; color: #1e293b; }
    
    /* Expander blanco y letras negras para visibilidad */
    .streamlit-expanderHeader {
        background-color: #ffffff !important; border-radius: 8px !important;
    }
    .streamlit-expanderHeader p {
        color: #000000 !important; font-weight: 700 !important; font-size: 13px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Encabezado alineado a la izquierda
c_logo, c_tit = st.columns([1, 8])
logo_path = "logo_sumaiq.png"
with c_logo:
    if os.path.exists(logo_path): st.image(Image.open(logo_path), width=85)
with c_tit:
    st.markdown('<div><span class="suma-text">SUMA</span><span class="ia-text">IA</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="eslogan">Tus gastos y nómina en perfecto orden</p>', unsafe_allow_html=True)

# --- SIDEBAR (Tablero Izquierdo) ---
if 'manual_refs' not in st.session_state: st.session_state['manual_refs'] = []
if 'reset_cnt' not in st.session_state: st.session_state['reset_cnt'] = 0

with st.sidebar:
    st.header("Control Maestro")
    
    # --- CUADRO DE CARGA MANUAL DESPLEGABLE ---
    with st.expander("🚀 CONFIGURAR SALDO INICIAL", expanded=False):
        m_inicial = st.number_input("Establecer Saldo Base (Bs.):", value=0.0, step=100.0)
        if st.button("💾 Guardar Saldo Base", use_container_width=True):
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO finanzas VALUES (?,?,?,?,?,?)", 
                                   (datetime.now().strftime("%Y-%m-%d %H:%M"), 0.0, 0.0, 0.0, m_inicial, "Inicio Manual"))
            st.success("Saldo base establecido.")
            st.rerun()

    saldo_db = obtener_ultimo_saldo()
    if saldo_db is not None:
        st.markdown(f"<p style='color:#fde047; font-size:14px; font-weight:bold;'>Saldo Arrastrado: {formato_bs(saldo_db)}</p>", unsafe_allow_html=True)

    st.markdown("---")
    archivos_banco = st.file_uploader("📂 PDF Banco", type=["pdf"], accept_multiple_files=True, key=f"b_{st.session_state.reset_cnt}")
    fotos_recibos = st.file_uploader("📸 Recibos", type=["jpg", "png", "jpeg"], accept_multiple_files=True, key=f"i_{st.session_state.reset_cnt}")
    
    with st.expander("📝 REF. MANUAL"):
        ref_m = st.text_input("Agregar Referencia:")
        if st.button("➕ Forzar", use_container_width=True):
            if ref_m: st.session_state['manual_refs'].append(re.sub(r'\D', '', str(ref_m)))
        if st.button("🗑️ Reiniciar Todo", use_container_width=True):
            if os.path.exists('sumaia_history.db'): os.remove('sumaia_history.db')
            st.session_state['manual_refs'] = []; st.session_state['reset_cnt'] += 1; st.rerun()
    
    notas_auditor = st.text_area("Notas:")
    save_trigger = st.button("💾 GUARDAR CIERRE", type="primary", use_container_width=True)

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
            val = pd.to_numeric(re.sub(r'[^\d.]', '', s), errors='coerce') or 0.0
            return -val if '-' in str(v) else val
        
        df['M_Num'], df['Bal_Num'] = df['Monto'].apply(limpiar_m), df['Balance'].apply(limpiar_m)
        df['Ref_Limpia'] = df['Referencia'].astype(str).str.replace(r'\D', '', regex=True)
        df["Estatus"] = "❌ Pendiente"

        # Lógica de Conciliación
        refs_validas = set(st.session_state['manual_refs'])
        if fotos_recibos:
            for foto in fotos_recibos:
                try:
                    img = Image.open(foto).convert('L').resize((Image.open(foto).width*3, Image.open(foto).height*3))
                    txt = pytesseract.image_to_string(img, config='--psm 6').upper()
                    nums_f = re.findall(r'\d+', txt)
                    montos_f = [abs(limpiar_m(m)) for m in re.findall(r'\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}', txt)]
                    for n in nums_f:
                        if len(n) >= 5:
                            mask = df['Ref_Limpia'].str.contains(n, na=False)
                            if mask.any(): refs_validas.update(df[mask]['Ref_Limpia'].tolist())
                    for m_f in montos_f:
                        if m_f > 10.0:
                            mask_m = df['M_Num'].abs().between(m_f-0.05, m_f+0.05)
                            if mask_m.any(): refs_validas.update(df[mask_m]['Ref_Limpia'].tolist())
                except: continue

        for rv in refs_validas:
            df.loc[df['Ref_Limpia'].str.contains(rv, na=False), "Estatus"] = "✅ Conciliado"

        # Cálculos de Resumen
        mask_com = (df['Descripción'].str.contains("COMISION|IVA|COM\.|COM ", na=False, case=False)) & (df['M_Num'] < 0)
        t_com, t_ing = df[mask_com]['M_Num'].sum(), df[df['M_Num'] > 0]['M_Num'].sum()
        t_egr_neto, s_final = df[(~mask_com) & (df['M_Num'] < 0)]['M_Num'].sum(), df['Bal_Num'].iloc[-1]
        monto_pj = df[(df['Estatus'] == "❌ Pendiente") & (df['M_Num'] < 0)]['M_Num'].abs().sum()

        # --- TABLERO DE TARJETAS COMPACTAS ---
        st.markdown("### Resumen del Periodo")
        cols = st.columns(4)
        labels = ["Ingresos (+)", "Egresos Netos (-)", "Comisiones Bancarias", "Saldo en Banco"]
        vals = [t_ing, abs(t_egr_neto), abs(t_com), s_final]
        
        for i, col in enumerate(cols):
            with col:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">{labels[i]}</div>
                        <div class="metric-value">{formato_bs(vals[i])}</div>
                    </div>
                """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="background-color: #fef2f2; border: 1px solid #fecaca; padding: 8px; border-radius: 10px; text-align: center; margin-top: 15px;">
                <span style="color: #991b1b; font-weight: bold; font-size: 12px;">⚠️ POR JUSTIFICAR: </span>
                <span style="color: #ef4444; font-weight: 900; font-size: 15px;">{formato_bs(monto_pj)}</span>
            </div>
        """, unsafe_allow_html=True)

        st.subheader("📝 Detalle de Movimientos")
        st.dataframe(df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].style.apply(lambda r: ['background-color: #f0fdf4' if r['Estatus'] == "✅ Conciliado" else 'background-color: #fef2f2']*5, axis=1), use_container_width=True, hide_index=True)

        # Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame({"Concepto": ["Ingresos", "Egresos", "Comisiones", "Saldo", "PENDIENTE"], "Monto": [formato_bs(t_ing), formato_bs(abs(t_egr_neto)), formato_bs(abs(t_com)), formato_bs(s_final), formato_bs(monto_pj)]}).to_excel(writer, sheet_name='Resumen', index=False)
            df_det = df[["Fecha", "Referencia", "Descripción", "Monto", "Estatus"]].copy()
            df_det['Monto'] = df['M_Num'].apply(formato_bs)
            df_det.to_excel(writer, sheet_name='Detalle', index=False)
        st.download_button("📥 Descargar Reporte Excel", output.getvalue(), f"Cierre_{datetime.now().strftime('%Y%m%d')}.xlsx", use_container_width=True)

        if save_trigger:
            conn = sqlite3.connect('sumaia_history.db')
            with conn: conn.execute("INSERT INTO finanzas VALUES (?,?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M"), t_ing, abs(t_egr_neto), abs(t_com), s_final, notas_auditor))
            st.success("✅ Cierre Guardado exitosamente.")
else:
    st.info("👋 Sube tus documentos para comenzar el análisis automático.")
