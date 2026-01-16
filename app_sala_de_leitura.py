import streamlit as st
import pandas as pd
import requests
import numpy as np
import cv2
import re
import pytesseract  # Para ler os números escritos
from pyzbar import pyzbar  # Scanner muito mais potente que o anterior
from io import BytesIO
from datetime import datetime
from PIL import Image
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="BookScan Hub Pro", layout="centered", page_icon="📚")
st.markdown('<head><meta name="google" content="notranslate"></head>', unsafe_allow_html=True)

def conectar_supabase():
    try:
        return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    except: return None

supabase = conectar_supabase()

# --- 2. INTELIGÊNCIA DE BUSCA (GOOGLE -> OPEN LIBRARY) ---

def buscar_dados_livro(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    if len(isbn_limpo) < 10: return None
    
    # 1. GOOGLE BOOKS
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}"
        res = requests.get(url, timeout=5).json()
        if "items" in res:
            info = res["items"][0]["volumeInfo"]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                "sinopse": info.get("description", "Sinopse não disponível."),
                "genero": info.get("categories", ["Geral"])[0],
                "fonte": "Google Books"
            }
    except: pass

    # 2. OPEN LIBRARY
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res = requests.get(url, timeout=5).json()
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

# --- 3. SCANNER SUPER POTENTE (BARRAS + QR + OCR) ---

def processar_imagem_completo(foto):
    img_pil = Image.open(foto)
    img_pil.thumbnail((1200, 1200)) # Qualidade maior para o OCR
    img_cv = np.array(img_pil.convert('RGB'))
    img_cv = img_cv[:, :, ::-1].copy()
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # A. Tenta ler Código de Barras e QR Code com PyZbar (Melhor do mercado)
    objetos_lidos = pyzbar.decode(img_cv)
    for obj in objetos_lidos:
        codigo = obj.data.decode("utf-8")
        isbn_no_link = re.findall(r'(\d{10,13})', codigo)
        res = isbn_no_link[0] if isbn_no_link else codigo
        if len(res) >= 10: return res

    # B. Se falhar, tenta ler os NÚMEROS escritos (OCR)
    # Aplica um filtro para destacar números
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    texto_extraido = pytesseract.image_to_string(thresh, config='--psm 6 digits')
    numeros_achados = re.findall(r'(\d{10,13})', texto_extraido)
    
    if numeros_achados:
        return numeros_achados[0]
        
    return None

# --- 4. INTERFACE ---

if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""

st.sidebar.title("📚 Acervo Digital")
menu = st.sidebar.selectbox("Menu:", ["Scanner de Livros", "Ver Acervo"])

if menu == "Scanner de Livros":
    st.title("📷 Cadastro Inteligente")
    st.info("Dica: Se o código de barras não ler, aponte para os números do ISBN abaixo dele.")
    
    foto = st.file_uploader("Capturar imagem", type=['png', 'jpg', 'jpeg'])
    
    if foto:
        with st.spinner("Analisando imagem e textos..."):
            resultado = processar_imagem_completo(foto)
            if resultado:
                st.session_state.isbn_detectado = resultado
                st.success(f"✅ Identificado: {resultado}")
            else:
                st.error("❌ Não foi possível identificar o código ou os números.")

    isbn_input = st.text_input("Confirme o Código/ISBN:", value=st.session_state.isbn_detectado).strip()

    if isbn_input:
        if supabase:
            res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_input).execute()
            
            if res_db.data:
                # --- JÁ EXISTE ---
                item = res_db.data[0]
                st.info(f"📖 Livro: {item['titulo']}")
                add_qtd = st.number_input("Adicionar ao estoque?", min_value=1, value=1)
                if st.button("➕ Atualizar"):
                    nova_qtd = int(item['quantidade']) + add_qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_input).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.isbn_detectado = ""
                    time.sleep(1); st.rerun()
            else:
                # --- BUSCA NAS APIs ---
                with st.spinner("Buscando dados bibliográficos..."):
                    dados = buscar_dados_livro(isbn_input)
                    if dados:
                        st.subheader(f"✨ Encontrado via {dados['fonte']}")
                        with st.form("form_save"):
                            f_tit = st.text_input("Título", dados['titulo'])
                            f_aut = st.text_input("Autor", dados['autor'])
                            f_gen = st.text_input("Gênero", dados['genero'])
                            f_sin = st.text_area("Sinopse", dados['sinopse'], height=150)
                            f_qtd = st.number_input("Qtd Inicial", min_value=1, value=1)
                            if st.form_submit_button("🚀 Salvar na Nuvem"):
                                supabase.table("livros_acervo").insert({
                                    "isbn": isbn_input, "titulo": f_tit, "autor": f_aut,
                                    "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                                    "data_cadastro": datetime.now().isoformat()
                                }).execute()
                                st.success("Cadastrado com sucesso!")
                                st.session_state.isbn_detectado = ""
                                time.sleep(1); st.rerun()
                    else:
                        st.error("⚠️ Livro não encontrado nas bases oficiais (Google/OpenLibrary).")
                        if st.button("Tentar outro código"):
                            st.session_state.isbn_detectado = ""
                            st.rerun()
        else:
            st.error("Erro de banco de dados.")

else:
    st.title("📊 Acervo Geral")
    if supabase:
        res = supabase.table("livros_acervo").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.metric("Total de Livros", len(df))
            st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)