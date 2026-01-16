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

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="BookScan Hub Pro",
    layout="centered",
    page_icon="📚"
)

# --- 2. MODO ESCURO E ESTILO (Evitando erros de string multiline) ---
def aplicar_estilo():
    # CSS injetado de forma mais segura para evitar erros de token
    estilo_css = """
    <style>
        .stApp { background-color: #121212; color: #E0E0E0; }
        section[data-testid="stSidebar"] { background-color: #1B1B1B; }
        .stButton>button { 
            background-color: #FFB300 !important; 
            color: black !important; 
            border-radius: 10px;
            width: 100%;
        }
        .stTextInput input, .stTextArea textarea {
            background-color: #1E1E1E !important;
            color: #FFB300 !important;
        }
    </style>
    """
    st.markdown(estilo_css, unsafe_allow_html=True)
    st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

aplicar_estilo()

# --- 3. CONEXÃO COM O SUPABASE ---
@st.cache_resource
def conectar_supabase():
    try:
        # Certifique-se que estes campos existem no 'Secrets' do Streamlit Cloud
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de Secrets: {e}")
        return None

supabase = conectar_supabase()

# --- 4. FUNÇÕES DE BUSCA E SCANNER ---

def extrair_isbn_de_texto(texto):
    """Procura padrões de ISBN (10 ou 13 dígitos) dentro de um link ou texto"""
    padrao = re.findall(r'(\d{10,13})', str(texto))
    return padrao[0] if padrao else None

def buscar_livro_api(isbn):
    """Busca dados com fallback automático entre Google e OpenLibrary"""
    isbn = str(isbn).strip()
    
    # 1. Tentativa Google Books (Melhor para Sinopses)
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}", timeout=5)
        if r.status_code == 200 and "items" in r.json():
            info = r.json()["items"][0]["volumeInfo"]
            return {
                "titulo": info.get("title", ""),
                "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                "sinopse": info.get("description", "Sinopse não disponível."),
                "genero": info.get("categories", ["Geral"])[0],
                "fonte": "Google Books"
            }
    except: pass

    # 2. Tentativa Open Library (Backup)
    try:
        r = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data", timeout=5)
        if r.status_code == 200:
            d = r.json()
            key = f"ISBN:{isbn}"
            if key in d:
                return {
                    "titulo": d[key].get("title", ""),
                    "autor": ", ".join([a['name'] for a in d[key].get("authors", [])]),
                    "sinopse": "Sumário não disponível.",
                    "genero": "Geral",
                    "fonte": "Open Library"
                }
    except: pass
    return None

def processar_imagem(uploaded_file):
    """Detecta Código de Barras OU QR Code"""
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    # Tenta QR Code primeiro
    qr_detector = cv2.QRCodeDetector()
    val_qr, _, _ = qr_detector.detectAndDecode(img)
    if val_qr:
        isbn = extrair_isbn_de_texto(val_qr)
        return isbn if isbn else val_qr
    
    # Tenta Barcode
    bar_detector = cv2.barcode.BarcodeDetector()
    ok, val_bar, _, _ = bar_detector.detectAndDecode(img)
    if ok and val_bar:
        return val_bar[0]
        
    return None

# --- 5. INTERFACE DO USUÁRIO ---

if "isbn_detectado" not in st.session_state:
    st.session_state.isbn_detectado = ""

st.sidebar.title("📚 Acervo Digital")
menu = st.sidebar.selectbox("Ir para:", ["Cadastrar Livro", "Ver Acervo"])

if menu == "Cadastrar Livro":
    st.title("🚚 Entrada de Volumes")
    st.info("O sistema agora aceita Código de Barras e QR Code.")
    
    # Opção de Câmera/Upload
    arquivo = st.file_uploader("Capture ou selecione a imagem do código", type=['jpg', 'jpeg', 'png'])
    
    if arquivo:
        with st.spinner("Lendo código..."):
            res = processar_imagem(arquivo)
            if res:
                st.session_state.isbn_detectado = res
                st.success(f"Código lido com sucesso: {res}")
            else:
                st.error("Não foi possível ler o código. Tente tirar a foto mais de perto e com luz.")

    # Campo de ISBN (preenchido automaticamente ou manualmente)
    isbn_confirmado = st.text_input("ISBN do Livro:", value=st.session_state.isbn_detectado).strip()

    if isbn_confirmado:
        # Checar se existe no banco
        res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_confirmado).execute()
        
        if res_db.data:
            livro = res_db.data[0]
            st.warning(f"📖 O livro '{livro['titulo']}' já está no acervo.")
            add_qtd = st.number_input("Adicionar quantos exemplares?", min_value=1, value=1)
            if st.button("Atualizar Estoque"):
                nova_qtd = int(livro['quantidade']) + add_qtd
                supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_confirmado).execute()
                st.success("Quantidade atualizada!")
                st.session_state.isbn_detectado = ""
                time.sleep(1)
                st.rerun()
        else:
            # Novo livro - Buscar na API
            with st.spinner("Buscando informações bibliográficas..."):
                info_api = buscar_livro_api(isbn_confirmado)
                if not info_api:
                    info_api = {"titulo": "", "autor": "", "sinopse": "Não encontrada", "genero": "Geral", "fonte": "Manual"}
                
                st.markdown(f"### ✨ Dados Sugeridos ({info_api['fonte']})")
                with st.form("confirmar_cadastro"):
                    f_tit = st.text_input("Título", info_api['titulo'])
                    f_aut = st.text_input("Autor", info_api['autor'])
                    f_gen = st.text_input("Gênero", info_api['genero'])
                    f_sin = st.text_area("Sumário / Sinopse", info_api['sinopse'], height=150)
                    f_qtd = st.number_input("Quantidade Inicial", min_value=1, value=1)
                    
                    if st.form_submit_button("🚀 Finalizar Cadastro na Nuvem"):
                        if not f_tit or not f_aut:
                            st.error("Título e Autor são obrigatórios.")
                        else:
                            # Tenta inserir no Supabase
                            try:
                                supabase.table("livros_acervo").insert({
                                    "isbn": isbn_confirmado,
                                    "titulo": f_tit,
                                    "autor": f_aut,
                                    "genero": f_gen,
                                    "sinopse": f_sin,
                                    "quantidade": f_qtd,
                                    "data_cadastro": datetime.now().isoformat()
                                }).execute()
                                st.success("Livro salvo com sucesso na nuvem!")
                                st.session_state.isbn_detectado = ""
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}. Verifique as permissões de RLS no Supabase.")

else:
    st.title("📊 Acervo Geral")
    try:
        res = supabase.table("livros_acervo").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.metric("Total de Títulos", len(df))
            st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
        else:
            st.info("Nenhum livro cadastrado ainda.")
    except:
        st.error("Erro ao carregar o acervo.")