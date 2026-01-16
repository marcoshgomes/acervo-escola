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
st.set_page_config(page_title="BookScan Hub Pro", layout="centered", page_icon="📚")

# --- 2. MODO ESCURO E ESTILO (Usando strings simples para evitar TokenError) ---
st.markdown('<style>.stApp { background-color: #121212; color: #E0E0E0; } section[data-testid="stSidebar"] { background-color: #1B1B1B; } .stButton>button { background-color: #FFB300 !important; color: black !important; border-radius: 10px; width: 100%; } .stTextInput input, .stTextArea textarea { background-color: #1E1E1E !important; color: #FFB300 !important; }</style>', unsafe_allow_html=True)
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

# --- 3. CONEXÃO COM O SUPABASE ---
# Removido cache_resource para teste de estabilidade contra TokenError
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        return None

supabase = conectar_supabase()

# --- 4. FUNÇÕES DE BUSCA E SCANNER ---

def extrair_isbn_de_texto(texto):
    # Procura ISBN de 10 ou 13 dígitos
    padrao = re.findall(r'(\d{10,13})', str(texto))
    return padrao[0] if padrao else None

def buscar_livro_api(isbn):
    isbn = str(isbn).strip()
    # 1. Tentativa Google Books
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
    # 2. Tentativa Open Library
    try:
        r = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data", timeout=5)
        if r.status_code == 200:
            d = r.json()
            k = f"ISBN:{isbn}"
            if k in d:
                return {
                    "titulo": d[k].get("title", ""),
                    "autor": ", ".join([a['name'] for a in d[k].get("authors", [])]),
                    "sinopse": "Sumário não disponível.",
                    "genero": "Geral",
                    "fonte": "Open Library"
                }
    except: pass
    return None

def processar_imagem(uploaded_file):
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    # Tenta QR Code
    qr_det = cv2.QRCodeDetector()
    val_qr, _, _ = qr_det.detectAndDecode(img)
    if val_qr:
        isbn = extrair_isbn_de_texto(val_qr)
        return isbn if isbn else val_qr
    # Tenta Barcode
    bar_det = cv2.barcode.BarcodeDetector()
    ok, val_bar, _, _ = bar_det.detectAndDecode(img)
    if ok and val_bar:
        return val_bar[0]
    return None

# --- 5. INTERFACE DO USUÁRIO ---

if "isbn_sessao" not in st.session_state:
    st.session_state.isbn_sessao = ""

st.sidebar.title("📚 Acervo Digital")
menu = st.sidebar.selectbox("Ir para:", ["Cadastrar Livro", "Ver Acervo"])

if menu == "Cadastrar Livro":
    st.title("📷 Scanner de Acervo")
    st.write("Suporte para Código de Barras e QR Code.")
    
    arquivo = st.file_uploader("Foto do código", type=['jpg', 'jpeg', 'png'])
    if arquivo:
        res = processar_imagem(arquivo)
        if res:
            st.session_state.isbn_detectado = res
            st.success(f"Detectado: {res}")

    isbn_input = st.text_input("ISBN:", value=st.session_state.get("isbn_detectado", "")).strip()

    if isbn_input:
        if supabase:
            res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_input).execute()
            if res_db.data:
                livro = res_db.data[0]
                st.info(f"Livro: {livro['titulo']} (Já cadastrado)")
                qtd = st.number_input("Adicionar exemplares?", min_value=1, value=1)
                if st.button("➕ Atualizar"):
                    nova_qtd = int(livro['quantidade']) + qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_input).execute()
                    st.success("Atualizado!")
                    st.rerun()
            else:
                info = buscar_livro_api(isbn_input)
                if not info: info = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                
                st.write(f"### ✨ Novo Livro ({info['fonte']})")
                with st.form("form_novo"):
                    f_tit = st.text_input("Título", info['titulo'])
                    f_aut = st.text_input("Autor", info['autor'])
                    f_gen = st.text_input("Gênero", info['genero'])
                    f_sin = st.text_area("Sinopse", info['sinopse'], height=100)
                    f_qtd = st.number_input("Qtd", min_value=1, value=1)
                    if st.form_submit_button("🚀 Cadastrar na Nuvem"):
                        supabase.table("livros_acervo").insert({
                            "isbn": isbn_input, "titulo": f_tit, "autor": f_aut,
                            "genero": f_gen, "sinopse": f_sin, "quantidade": f_qtd,
                            "data_cadastro": datetime.now().isoformat()
                        }).execute()
                        st.success("Cadastrado!")
                        st.rerun()
        else:
            st.error("Supabase não conectado. Verifique os Secrets.")

else:
    st.title("📊 Acervo")
    if supabase:
        res = supabase.table("livros_acervo").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)