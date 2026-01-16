import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import cv2
import re
from io import BytesIO
from datetime import datetime
from PIL import Image
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BookScan Hub Cloud", layout="centered", page_icon="📚")

# --- 2. MODO ESCURO CUSTOMIZADO (ESTILO LOVABLE) ---
st.markdown('<style>.stApp { background-color: #121212; color: #E0E0E0; } section[data-testid="stSidebar"] { background-color: #1B1B1B; } .stButton>button { background-color: #FFB300 !important; color: black !important; border-radius: 10px; width: 100%; border: none; font-weight: bold; } .stTextInput input, .stTextArea textarea { background-color: #1E1E1E !important; color: #FFB300 !important; border-color: #333 !important; } .stMetric { background-color: #1E1E1E; padding: 15px; border-radius: 10px; border: 1px solid #333; } [data-testid="stHeader"] { background: rgba(0,0,0,0); } </style>', unsafe_allow_html=True)
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

# --- 3. CONEXÃO SUPABASE ---
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        return None

supabase = conectar_supabase()

# --- 4. FUNÇÕES DE BUSCA (API & NUVEM) ---

def buscar_dados_livro(isbn):
    """Busca dados com fallback entre Google Books e Open Library"""
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. TENTA GOOGLE BOOKS
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}"
        res = requests.get(url, headers=headers, timeout=5).json()
        if "items" in res:
            info = res["items"][0]["volumeInfo"]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                "sinopse": info.get("description", "Sem sinopse disponível"),
                "genero": info.get("categories", ["Geral"])[0],
                "fonte": "Google Books"
            }
    except: pass

    # 2. TENTA OPEN LIBRARY
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res = requests.get(url, headers=headers, timeout=5).json()
        key = f"ISBN:{isbn_limpo}"
        if key in res:
            info = res[key]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join([a['name'] for a in info.get("authors", [])]) or "Desconhecido",
                "sinopse": "Sinopse não disponível.",
                "genero": "Geral",
                "fonte": "Open Library"
            }
    except: pass
    return None

# --- 5. LÓGICA DE SCANNER (HÍBRIDO: BARCODE + QRCODE) ---

def processar_imagem_hibrida(foto):
    """Lógica da Versão 2: Redimensionamento + Grayscale para máxima eficiência"""
    img_pil = Image.open(foto)
    img_pil.thumbnail((1000, 1000))
    img_cv = np.array(img_pil.convert('RGB'))
    img_cv = img_cv[:, :, ::-1].copy() # RGB para BGR
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Tentativa 1: QR CODE (Novo Requisito)
    qr_detector = cv2.QRCodeDetector()
    val_qr, _, _ = qr_detector.detectAndDecode(gray)
    if val_qr:
        # Tenta extrair ISBN se o QR for um link
        isbn_extraido = re.findall(r'(\d{10,13})', val_qr)
        return isbn_extraido[0] if isbn_extraido else val_qr
    
    # Tentativa 2: CÓDIGO DE BARRAS (Lógica Versão 2)
    bar_detector = cv2.barcode.BarcodeDetector()
    ok, decoded_info, _, _ = bar_detector.detectAndDecode(gray)
    if ok and decoded_info:
        return decoded_info[0]
        
    return None

# --- 6. INTERFACE ---
if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0

st.sidebar.title("📚 Acervo Cloud Pro")
menu = st.sidebar.selectbox("Navegação", ["Entrada de Livros", "Ver Acervo"])

if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    foto = st.file_uploader("📷 Escanear Código (Barras ou QR)", type=['png', 'jpg', 'jpeg'], key=f"u_{st.session_state.reset_count}")
    
    if foto:
        with st.spinner("Lendo imagem..."):
            resultado = processar_imagem_hibrida(foto)
            if resultado:
                st.session_state.isbn_detectado = resultado
                st.success(f"✅ Código lido: {resultado}")
            else:
                st.error("❌ Não detectamos código. Aproxime mais a câmera.")

    st.divider()
    
    isbn_confirmado = st.text_input("Confirme o Código/ISBN:", value=st.session_state.isbn_detectado).strip()

    if isbn_confirmado:
        if not supabase:
            st.error("Erro: Supabase não configurado nos Secrets.")
        else:
            # Verifica se já existe na nuvem
            res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_confirmado).execute()
            
            if res_check.data:
                item = res_check.data[0]
                st.info(f"📖 Livro: {item['titulo']} (Já cadastrado)")
                add_qtd = st.number_input("Adicionar exemplares?", min_value=1, value=1)
                if st.button("➕ Atualizar na Nuvem"):
                    nova_qtd = int(item['quantidade']) + add_qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_confirmado).execute()
                    st.success("Estoque Atualizado!")
                    st.session_state.isbn_detectado = ""; st.rerun()
            else:
                # Novo livro - Busca APIs
                with st.spinner("Buscando dados bibliográficos..."):
                    dados = buscar_dados_livro(isbn_confirmado)
                    if not dados: dados = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                    
                    st.warning(f"✨ Novo Registro via {dados['fonte']}")
                    with st.form("novo_cadastro"):
                        f_tit = st.text_input("Título", dados['titulo'])
                        f_aut = st.text_input("Autor", dados['autor'])
                        f_gen = st.text_input("Gênero", dados['genero'])
                        f_sin = st.text_area("Sinopse / Sumário", dados['sinopse'], height=150)
                        f_qtd = st.number_input("Quantidade Inicial", min_value=1, value=1)
                        
                        if st.form_submit_button("🚀 Salvar na Nuvem"):
                            supabase.table("livros_acervo").insert({
                                "isbn": isbn_confirmado, "titulo": f_tit, "autor": f_aut,
                                "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                                "data_cadastro": datetime.now().isoformat()
                            }).execute()
                            st.success("Cadastrado com sucesso!")
                            st.session_state.isbn_detectado = ""; st.rerun()

elif menu == "Ver Acervo":
    st.title("📊 Acervo Geral")
    if supabase:
        res = supabase.table("livros_acervo").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            c1, c2 = st.columns(2)
            c1.metric("Títulos", len(df))
            c2.metric("Total Volumes", df['quantidade'].sum())
            st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)