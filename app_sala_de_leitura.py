import streamlit as st
import pandas as pd
import requests
import numpy as np
import cv2
import re
from io import BytesIO
from datetime import datetime
from PIL import Image
from supabase import create_client, Client

# --- TENTA IMPORTAR BIBLIOTECAS ESPECIAIS ---
try:
    import pytesseract
    from pyzbar import pyzbar
    LIBS_OK = True
except ImportError:
    LIBS_OK = False

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="BookScan Hub Pro", layout="centered", page_icon="📚")
st.markdown('<head><meta name="google" content="notranslate"></head>', unsafe_allow_html=True)

def conectar_supabase():
    try:
        return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    except: return None

supabase = conectar_supabase()

if not LIBS_OK:
    st.error("🔌 O servidor ainda está instalando as ferramentas de leitura (Tesseract/ZBar). Por favor, aguarde 1 minuto e recarregue a página.")
    st.stop()

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

# --- 3. SCANNER (BARRAS + QR + OCR) ---
def processar_imagem_completo(foto):
    img_pil = Image.open(foto)
    img_pil.thumbnail((1000, 1000)) 
    img_cv = np.array(img_pil.convert('RGB'))
    img_cv = img_cv[:, :, ::-1].copy()
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # A. Scanner de Barras e QR
    objetos_lidos = pyzbar.decode(img_cv)
    for obj in objetos_lidos:
        codigo = obj.data.decode("utf-8")
        isbn_no_link = re.findall(r'(\d{10,13})', codigo)
        res = isbn_no_link[0] if isbn_no_link else codigo
        if len(res) >= 10: return res

    # B. OCR (Leitura dos números escritos)
    # Melhora o contraste para os números
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
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
    st.title("📷 Cadastro via Câmera")
    st.info("Aponte para o código de barras ou para os números do ISBN.")
    
    foto = st.file_uploader("Capturar imagem", type=['png', 'jpg', 'jpeg'])
    
    if foto:
        with st.spinner("Analisando código e números..."):
            resultado = processar_imagem_completo(foto)
            if resultado:
                st.session_state.isbn_detectado = resultado
                st.success(f"✅ Identificado: {resultado}")
            else:
                st.error("❌ Não foi possível ler. Tente uma foto mais nítida apenas dos números.")

    isbn_input = st.text_input("Confirme o Código/ISBN:", value=st.session_state.isbn_detectado).strip()

    if isbn_input:
        if supabase:
            res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_input).execute()
            if res_db.data:
                item = res_db.data[0]
                st.info(f"📖 Livro: {item['titulo']}")
                add_qtd = st.number_input("Adicionar ao estoque?", min_value=1, value=1)
                if st.button("➕ Atualizar"):
                    nova_qtd = int(item['quantidade']) + add_qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_input).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.isbn_detectado = ""; time.sleep(1); st.rerun()
            else:
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
                                st.session_state.isbn_detectado = ""; time.sleep(1); st.rerun()
                    else:
                        st.error("⚠️ Livro não encontrado nas bases oficiais.")
                        if st.button("Limpar"):
                            st.session_state.isbn_detectado = ""; st.rerun()
else:
    st.title("📊 Acervo Geral")
    if supabase:
        res = supabase.table("livros_acervo").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.metric("Total de Livros", len(df))
            st.dataframe(df[['isbn', 'titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)