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
st.set_page_config(page_title="BookScan Hub", layout="centered", page_icon="📚")

# Proteção contra Google Tradutor
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

# --- 3. FUNÇÕES DE BUSCA (ORDEM: GOOGLE -> OPEN LIBRARY) ---

def buscar_dados_livro(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # --- 1ª TENTATIVA: GOOGLE BOOKS ---
    try:
        url_g = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}"
        res_g = requests.get(url_g, headers=headers, timeout=5).json()
        if "items" in res_g:
            info = res_g["items"][0]["volumeInfo"]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                "sinopse": info.get("description", "Sinopse não disponível."),
                "genero": info.get("categories", ["Geral"])[0],
                "fonte": "Google Books"
            }
    except:
        pass

    # --- 2ª TENTATIVA: OPEN LIBRARY (Fallback) ---
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res_ol = requests.get(url_ol, headers=headers, timeout=5).json()
        key = f"ISBN:{isbn_limpo}"
        if key in res_ol:
            info = res_ol[key]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join([a['name'] for a in info.get("authors", [])]) or "Desconhecido",
                "sinopse": "Sinopse não disponível (Open Library).",
                "genero": "Geral",
                "fonte": "Open Library"
            }
    except:
        pass

    return None

# --- 4. SCANNER MELHORADO (FILTRA ERROS DE LEITURA) ---

def processar_imagem_hibrida(foto):
    img_pil = Image.open(foto)
    img_pil.thumbnail((1000, 1000)) 
    img_cv = np.array(img_pil.convert('RGB'))
    img_cv = img_cv[:, :, ::-1].copy()
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # 1. Tenta QR CODE
    qr_detector = cv2.QRCodeDetector()
    val_qr, _, _ = qr_detector.detectAndDecode(gray)
    if val_qr:
        isbn_link = re.findall(r'(\d{10,13})', val_qr)
        res_qr = isbn_link[0] if isbn_link else val_qr
        if len(res_qr) >= 10: # Valida se é um código real
            return res_qr
    
    # 2. Tenta CÓDIGO DE BARRAS
    bar_detector = cv2.barcode.BarcodeDetector()
    resultado = bar_detector.detectAndDecode(gray)
    
    if resultado is not None and len(resultado) > 0:
        codigos = resultado[0]
        if codigos and len(codigos) > 0:
            codigo_final = codigos[0].strip()
            # IMPORTANTE: Só aceita se tiver 10 ou 13 dígitos (padrão ISBN)
            if len(codigo_final) >= 10:
                return codigo_final
            
    return None

# --- 5. INTERFACE ---

if "isbn_detectado" not in st.session_state: 
    st.session_state.isbn_detectado = ""

st.sidebar.title("📚 Acervo Sala de Leitura")
menu = st.sidebar.selectbox("Navegação", ["Scanner Celular", "Ver Acervo"])

if menu == "Scanner Celular":
    st.title("📷 Cadastro via Câmera")
    st.write("Use esta tela para cadastrar livros que possuem registro oficial.")
    
    foto = st.file_uploader("Capture a foto do código (Barras ou QR)", type=['png', 'jpg', 'jpeg'])
    
    if foto:
        with st.spinner("Lendo código..."):
            resultado = processar_imagem_hibrida(foto)
            if resultado:
                st.session_state.isbn_detectado = resultado
                st.success(f"✅ Código identificado: {resultado}")
            else:
                st.error("❌ Código não reconhecido ou incompleto. Tente enquadrar apenas o código de barras.")

    isbn_input = st.text_input("Confirme o Código/ISBN:", value=st.session_state.isbn_detectado).strip()

    if isbn_input:
        if not supabase:
            st.error("Erro de conexão com o Supabase.")
        else:
            # 1. Verifica se já existe no banco (para atualizar estoque)
            res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_input).execute()
            
            if res_db.data:
                item = res_db.data[0]
                st.info(f"📖 Livro já existente: **{item['titulo']}**")
                qtd_add = st.number_input("Adicionar exemplares ao estoque?", min_value=1, value=1)
                if st.button("➕ Atualizar Quantidade"):
                    nova_qtd = int(item['quantidade']) + qtd_add
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_input).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.isbn_detectado = ""
                    time.sleep(1); st.rerun()
            else:
                # 2. Se não existe, busca nas APIs (Google -> OpenLibrary)
                with st.spinner("Buscando dados nas APIs oficiais..."):
                    dados = buscar_dados_livro(isbn_input)
                    
                    if dados:
                        # ENCONTROU NA API: MOSTRA O FORMULÁRIO PARA SALVAR
                        st.success(f"✨ Dados encontrados via {dados['fonte']}")
                        with st.form("form_cadastro_api"):
                            f_tit = st.text_input("Título", dados['titulo'])
                            f_aut = st.text_input("Autor", dados['autor'])
                            f_gen = st.text_input("Gênero", dados['genero'])
                            f_sin = st.text_area("Sinopse", dados['sinopse'], height=150)
                            f_qtd = st.number_input("Quantidade Inicial", min_value=1, value=1)
                            
                            if st.form_submit_button("🚀 Confirmar e Salvar na Nuvem"):
                                supabase.table("livros_acervo").insert({
                                    "isbn": isbn_input, "titulo": f_tit, "autor": f_aut,
                                    "genero": f_gen, "sinopse": f_sin, "quantidade": f_qtd,
                                    "data_cadastro": datetime.now().isoformat()
                                }).execute()
                                st.success("Livro cadastrado com sucesso!")
                                st.session_state.isbn_detectado = ""
                                time.sleep(1); st.rerun()
                    else:
                        # NÃO ENCONTROU EM NENHUMA API
                        st.error("⚠️ Este livro não foi encontrado no Google Books nem no Open Library.")
                        st.info("Para este exemplar, utilize o cadastro manual via Computador.")
                        if st.button("Limpar e tentar outro"):
                            st.session_state.isbn_detectado = ""
                            st.rerun()

else:
    st.title("📊 Acervo Geral (Nuvem)")
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
            st.error("Erro ao carregar dados do banco.")