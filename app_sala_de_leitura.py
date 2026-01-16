import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import cv2
import re
from io import BytesIO
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="BookScan Hub - Sala de Leitura",
    layout="centered",
    page_icon="📚",
    initial_sidebar_state="expanded"
)

# --- ESTILO DARK MODE CUSTOMIZADO (ESTILO LOVABLE) ---
st.markdown("""
    <style>
        /* Fundo principal e cores de texto */
        .stApp { background-color: #121212; color: #E0E0E0; }
        .stButton>button { background-color: #FFB300; color: #000; border-radius: 8px; border: none; font-weight: bold; }
        .stButton>button:hover { background-color: #FF8F00; color: #fff; }
        .stTextInput>div>div>input { background-color: #1E1E1E; color: #FFB300; border-color: #333; }
        section[data-testid="stSidebar"] { background-color: #1B1B1B; }
        .stMetric { background-color: #1E1E1E; padding: 15px; border-radius: 10px; border: 1px solid #333; }
        /* Anti-tradutor */
        head { display: none; }
    </style>
    <head><meta name="google" content="notranslate"></head>
""", unsafe_allow_html=True)

# --- CONEXÃO COM O SUPABASE ---
@st.cache_resource
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.sidebar.error("⚠️ Erro nos Secrets do Supabase")
        return None

supabase = conectar_supabase()

# --- FUNÇÕES DE LÓGICA ---

def extrair_isbn_de_texto(texto):
    """Tenta achar um ISBN de 10 ou 13 dígitos em uma URL ou texto de QR Code"""
    match = re.search(r'(\d{10,13})', texto)
    return match.group(1) if match else None

def buscar_dados_livro(isbn):
    """Busca com Fallback (Google -> OpenLibrary) e suporte a Sumário"""
    isbn = str(isbn).strip()
    
    # 1. GOOGLE BOOKS (Melhor para sinopses e categorias)
    try:
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}", timeout=5)
        if res.status_code == 200:
            dados = res.json()
            if "items" in dados:
                info = dados["items"][0]["volumeInfo"]
                return {
                    "titulo": info.get("title", "Título Desconhecido"),
                    "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                    "sinopse": info.get("description", "Sinopse indisponível no Google Books."),
                    "genero": info.get("categories", ["Geral"])[0],
                    "fonte": "Google Books"
                }
    except: pass

    # 2. OPEN LIBRARY (Backup)
    try:
        res = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data", timeout=5)
        if res.status_code == 200:
            dados = res.json()
            key = f"ISBN:{isbn}"
            if key in dados:
                info = dados[key]
                return {
                    "titulo": info.get("title", "Título Desconhecido"),
                    "autor": ", ".join([a['name'] for a in info.get("authors", [])]) or "Desconhecido",
                    "sinopse": "Sinopse não encontrada (Open Library).",
                    "genero": "Geral",
                    "fonte": "Open Library"
                }
    except: pass
    return None

def detectar_codigo(image_file):
    """Detecta tanto Barcode quanto QR Code"""
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    # 1. Tentar QR Code Primeiro
    qr_detector = cv2.QRCodeDetector()
    val, pts, st_qr = qr_detector.detectAndDecode(img)
    if val:
        isbn_tentativa = extrair_isbn_de_texto(val)
        return isbn_tentativa if isbn_tentativa else val

    # 2. Tentar Código de Barras
    barcode_detector = cv2.barcode.BarcodeDetector()
    ok, decoded_info, decoded_type, _ = barcode_detector.detectAndDecode(img)
    if ok and decoded_info:
        return decoded_info[0]
        
    return None

# --- INTERFACE PRINCIPAL ---
if "isbn_sessao" not in st.session_state: st.session_state.isbn_sessao = ""

st.sidebar.title("📚 BookScan Hub")
menu = st.sidebar.radio("Menu", ["Escanear Livro", "Acervo Completo"])

if menu == "Escanear Livro":
    st.title("📷 Scanner de Acervo")
    st.write("Aponte para o **Código de Barras** ou **QR Code** do livro.")
    
    arquivo_foto = st.file_uploader("Upload da foto", type=['jpg', 'jpeg', 'png'])
    
    if arquivo_foto:
        codigo = detectar_codigo(arquivo_foto)
        if codigo:
            st.session_state.isbn_sessao = codigo
            st.success(f"Código Identificado: {codigo}")
        else:
            st.error("❌ Não foi possível ler o código. Tente uma foto mais nítida.")

    isbn_confirmado = st.text_input("Confirme o ISBN/Código:", value=st.session_state.isbn_sessao)

    if isbn_confirmado:
        # Busca no banco para ver se atualiza estoque ou cadastra novo
        try:
            res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_confirmado).execute()
            
            if res_db.data:
                item = res_db.data[0]
                st.info(f"📖 Livro encontrado: **{item['titulo']}**")
                qtd = st.number_input("Quantos exemplares adicionar?", min_value=1, value=1)
                if st.button("➕ Atualizar Estoque"):
                    nova_qtd = int(item['quantidade']) + qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_confirmado).execute()
                    st.success("Estoque atualizado na nuvem!")
                    st.session_state.isbn_sessao = ""
            else:
                # Busca API
                with st.spinner("Buscando metadados..."):
                    info = buscar_dados_livro(isbn_confirmado)
                    if not info:
                        info = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                    
                    st.warning(f"✨ Novo livro detectado via {info['fonte']}")
                    with st.form("novo_livro"):
                        tit = st.text_input("Título", info['titulo'])
                        aut = st.text_input("Autor", info['autor'])
                        gen = st.text_input("Gênero", info['genero'])
                        sin = st.text_area("Sinopse / Sumário", info['sinopse'])
                        qtd_ini = st.number_input("Quantidade", min_value=1, value=1)
                        
                        if st.form_submit_button("🚀 Cadastrar na Nuvem"):
                            supabase.table("livros_acervo").insert({
                                "isbn": isbn_confirmado, "titulo": tit, "autor": aut,
                                "genero": gen, "sinopse": sin, "quantidade": qtd_ini,
                                "data_cadastro": datetime.now().isoformat()
                            }).execute()
                            st.success("Livro cadastrado com sucesso!")
                            st.session_state.isbn_sessao = ""
        except Exception as e:
            st.error(f"Erro na nuvem: {e}. Verifique as permissões (RLS) no Supabase.")

elif menu == "Acervo Completo":
    st.title("📊 Gestão de Acervo")
    res = supabase.table("livros_acervo").select("*").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        col1, col2 = st.columns(2)
        col1.metric("Total de Títulos", len(df))
        col2.metric("Total de Exemplares", df['quantidade'].sum())
        st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
    else:
        st.info("O acervo está vazio.")