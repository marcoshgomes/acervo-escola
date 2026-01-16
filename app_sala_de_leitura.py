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
st.set_page_config(page_title="Acervo Sala de Leitura", layout="centered", page_icon="📚")

# Proteção contra Google Tradutor (Mantendo apenas o essencial)
st.markdown('<head><meta name="google" content="notranslate"></head>', unsafe_allow_html=True)

# --- 2. CONEXÃO SUPABASE ---
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except:
        return None

supabase = conectar_supabase()

# --- 3. FUNÇÕES DE BUSCA ---

def buscar_dados_livro(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. GOOGLE BOOKS
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

    # 2. OPEN LIBRARY
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res = requests.get(url, headers=headers, timeout=5).json()
        key = f"ISBN:{isbn_limpo}"
        if key in res:
            info = res[key]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join([a['name'] for a in info.get("authors", [])]) or "Desconhecido",
                "sinopse": "Sinopse não disponível nesta base.",
                "genero": "Geral",
                "fonte": "Open Library"
            }
    except: pass
    return None

# --- 4. SCANNER CORRIGIDO (RESOLVE O VALUEERROR) ---

def processar_imagem_hibrida(foto):
    # Redimensiona para acelerar o processamento e evitar erro de memória
    img_pil = Image.open(foto)
    img_pil.thumbnail((800, 800)) 
    img_cv = np.array(img_pil.convert('RGB'))
    img_cv = img_cv[:, :, ::-1].copy()
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # 1. Tentar QR CODE
    qr_detector = cv2.QRCodeDetector()
    val_qr, _, _ = qr_detector.detectAndDecode(gray)
    if val_qr:
        # Se for um link, extrai o ISBN dele
        isbn_link = re.findall(r'(\d{10,13})', val_qr)
        return isbn_link[0] if isbn_link else val_qr
    
    # 2. Tentar CÓDIGO DE BARRAS (Forma segura de desempacotar)
    bar_detector = cv2.barcode.BarcodeDetector()
    resultado = bar_detector.detectAndDecode(gray)
    
    # Verificação robusta do retorno do OpenCV para evitar ValueError
    if resultado is not None and len(resultado) > 0:
        codigos = resultado[0] # Lista de textos lidos
        if codigos and len(codigos) > 0 and codigos[0] != "":
            return codigos[0]
            
    return None

# --- 5. INTERFACE ---

if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""

st.sidebar.title("📚 Acervo Digital")
menu = st.sidebar.selectbox("Navegação", ["Cadastrar Livro", "Ver Acervo"])

if menu == "Cadastrar Livro":
    st.title("🚚 Entrada de Livros")
    
    foto = st.file_uploader("📷 Capture o Código de Barras ou QR Code", type=['png', 'jpg', 'jpeg'])
    
    if foto:
        with st.spinner("Lendo código..."):
            resultado = processar_imagem_hibrida(foto)
            if resultado:
                st.session_state.isbn_detectado = resultado
                st.success(f"✅ Código identificado: {resultado}")
            else:
                st.error("❌ Não foi possível ler. Tente focar melhor no código.")

    isbn_confirmado = st.text_input("Confirme o Código/ISBN:", value=st.session_state.isbn_detectado).strip()

    if isbn_confirmado:
        if not supabase:
            st.error("Erro de conexão com o banco de dados.")
        else:
            # Verifica se já existe
            res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_confirmado).execute()
            
            if res_db.data:
                item = res_db.data[0]
                st.info(f"📖 Livro: {item['titulo']}")
                add_qtd = st.number_input("Adicionar quantos exemplares ao estoque?", min_value=1, value=1)
                if st.button("➕ Atualizar Estoque"):
                    nova_qtd = int(item['quantidade']) + add_qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_confirmado).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.isbn_detectado = ""
                    time.sleep(1); st.rerun()
            else:
                # Novo livro - Busca APIs
                with st.spinner("Buscando dados bibliográficos..."):
                    dados = buscar_dados_livro(isbn_confirmado)
                    if not dados: dados = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                    
                    st.subheader(f"✨ Novo Registro (Fonte: {dados['fonte']})")
                    with st.form("form_novo"):
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
                            st.success("Livro cadastrado com sucesso!")
                            st.session_state.isbn_detectado = ""
                            time.sleep(1); st.rerun()

else:
    st.title("📊 Acervo Geral")
    if supabase:
        try:
            res = supabase.table("livros_acervo").select("*").execute()
            if res.data:
                df = pd.DataFrame(res.data)
                st.metric("Total de Títulos", len(df))
                st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
            else:
                st.info("Nenhum livro cadastrado.")
        except:
            st.error("Erro ao carregar dados.")