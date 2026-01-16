import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import cv2
from io import BytesIO
from datetime import datetime
from supabase import create_client

# ==========================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==========================================================
st.set_page_config(
    page_title="Acervo Sala de Leitura Cloud",
    page_icon="📚",
    layout="centered"
)

st.markdown("""
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
""", unsafe_allow_html=True)

# ==========================================================
# 2. SUPABASE
# ==========================================================
@st.cache_resource
def conectar_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = conectar_supabase()

# ==========================================================
# 3. GÊNEROS E TRADUÇÃO
# ==========================================================
GENEROS_BASE = [
    "Ficção", "Infantil", "Juvenil", "Didático", "Poesia",
    "Contos", "Biografia", "História", "Ciências", "Geografia",
    "Artes", "Gibis/HQ", "Aventura", "Mistério", "Religião", "Filosofia"
]

TRADUCAO_GENEROS_API = {
    "Fiction": "Ficção",
    "Juvenile Fiction": "Ficção Juvenil",
    "Juvenile Nonfiction": "Não-ficção Juvenil",
    "Education": "Didático",
    "History": "História",
    "Science": "Ciências",
    "Philosophy": "Filosofia",
    "Religion": "Religião",
    "Biography & Autobiography": "Biografia",
    "Poetry": "Poesia",
    "Art": "Artes"
}

def traduzir_genero(g):
    return TRADUCAO_GENEROS_API.get(g, g if g else "Geral")

# ==========================================================
# 4. BUSCA ONLINE (GOOGLE BOOKS + BACKUP)
# ==========================================================
def buscar_dados_online(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))

    # ---------- GOOGLE BOOKS (PRIORITÁRIO) ----------
    try:
        api_key = st.secrets["google"]["books_api_key"]
        url = (
            "https://www.googleapis.com/books/v1/volumes"
            f"?q=isbn:{isbn_limpo}&key={api_key}&langRestrict=pt"
        )

        res = requests.get(url, timeout=8)

        if res.status_code == 200:
            dados = res.json()

            if dados.get("totalItems", 0) > 0:
                info = dados["items"][0]["volumeInfo"]

                categorias = info.get("categories")
                genero_final = (
                    traduzir_genero(categorias[0])
                    if isinstance(categorias, list) and categorias
                    else "Geral"
                )

                return {
                    "titulo": info.get("title", "Título não encontrado"),
                    "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                    "sinopse": info.get("description", "Sem sinopse disponível"),
                    "genero": genero_final,
                    "fonte": "Google Books"
                }
    except Exception as e:
        st.warning(f"Google Books indisponível: {e}")

    # ---------- OPEN LIBRARY (BACKUP) ----------
    try:
        url_ol = (
            f"https://openlibrary.org/api/books"
            f"?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        )
        res = requests.get(url_ol, timeout=5)

        chave = f"ISBN:{isbn_limpo}"
        if res.status_code == 200 and chave in res.json():
            info = res.json()[chave]

            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join(
                    a["name"] for a in info.get("authors", [{"name": "Desconhecido"}])
                ),
                "sinopse": "Resumo não disponível nesta base.",
                "genero": "Geral",
                "fonte": "Open Library"
            }
    except:
        pass

    return None

# ==========================================================
# 5. INTERFACE
# ==========================================================
st.sidebar.title("📚 Acervo Cloud")
st.sidebar.success("Conectado ao Supabase")

menu = st.sidebar.selectbox(
    "Navegação",
    ["Entrada de Livros", "Ver Acervo e Exportar"]
)

# ==========================================================
# ENTRADA DE LIVROS
# ==========================================================
if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")

    isbn_input = st.text_input("Digite ou cole o ISBN:")

    if isbn_input:
        with st.spinner("Buscando dados..."):
            dados = buscar_dados_online(isbn_input)

        if dados:
            st.success(f"Dados obtidos via {dados['fonte']}")

            with st.form("novo_livro"):
                titulo = st.text_input("Título", dados["titulo"])
                autor = st.text_input("Autor", dados["autor"])
                genero = st.selectbox(
                    "Gênero",
                    options=GENEROS_BASE,
                    index=GENEROS_BASE.index(dados["genero"])
                    if dados["genero"] in GENEROS_BASE else 0
                )
                sinopse = st.text_area("Sinopse", dados["sinopse"])
                qtd = st.number_input("Quantidade", min_value=1, value=1)

                if st.form_submit_button("Salvar no Acervo"):
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_input,
                        "titulo": titulo,
                        "autor": autor,
                        "sinopse": sinopse,
                        "genero": genero,
                        "quantidade": qtd,
                        "data_cadastro": datetime.now().strftime("%d/%m/%Y %H:%M")
                    }).execute()

                    st.success("Livro cadastrado com sucesso!")
                    time.sleep(1.5)
                    st.rerun()
        else:
            st.error("Não foi possível localizar dados para este ISBN.")

# ==========================================================
# VISUALIZAÇÃO DO ACERVO
# ==========================================================
else:
    st.header("📊 Acervo Registrado")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)

    if not df.empty:
        st.dataframe(df[["titulo", "autor", "genero", "quantidade"]])

        if st.button("📥 Exportar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for g in df["genero"].unique():
                    df[df["genero"] == g].to_excel(
                        writer, index=False, sheet_name=g[:30]
                    )
            st.download_button(
                "Baixar Planilha",
                data=output.getvalue(),
                file_name="acervo_escolar.xlsx"
            )
    else:
        st.info("Nenhum livro cadastrado.")
