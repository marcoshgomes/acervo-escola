import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import cv2
from io import BytesIO
from datetime import datetime
from PIL import Image
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR (PADRÃO AEE CONECTA) ---
st.set_page_config(page_title="Acervo Sala de Leitura Cloud", layout="centered", page_icon="📚")

st.markdown(
    """
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
    """,
    unsafe_allow_html=True
)

# --- 2. CONEXÃO COM O SUPABASE ---
try:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Erro ao conectar com a Nuvem. Verifique o arquivo secrets.toml")
    st.stop()

# --- 3. CONFIGURAÇÕES DE GÊNEROS E TRADUÇÕES ---
GENEROS_BASE = ["Ficção", "Infantil", "Juvenil", "Didático", "Poesia", "Contos", "História", "Ciências", "Artes", "Gibis/HQ", "Religião", "Filosofia"]
TRADUCAO_GENEROS_API = {"Fiction": "Ficção", "Juvenile Fiction": "Ficção Juvenil", "Education": "Didático", "History": "História", "Science": "Ciências", "General": "Geral", "Research": "Pesquisa"}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS_API.get(genero_ingles, genero_ingles)

# --- 4. FUNÇÕES DE BANCO DE DADOS (SUPABASE) ---

def get_generos_da_nuvem():
    try:
        # Busca gêneros distintos na nuvem
        res = supabase.table("livros_acervo").select("genero").execute()
        df_ex = pd.DataFrame(res.data)
        generos_nuvem = df_ex['genero'].unique().tolist() if not df_ex.empty else []
    except: generos_nuvem = []
    lista = list(set(GENEROS_BASE + generos_nuvem))
    lista = [g for g in lista if g]; lista.sort(); lista.append("➕ CADASTRAR NOVO GÊNERO")
    return lista

def buscar_livro_nuvem(isbn):
    res = supabase.table("livros_acervo").select("*").eq("isbn", isbn).execute()
    return pd.DataFrame(res.data) if res.data else None

def salvar_novo_livro_nuvem(dados):
    gen = dados['genero'].strip().capitalize()
    supabase.table("livros_acervo").insert({
        "isbn": dados['isbn'],
        "titulo": dados['titulo'],
        "autor": dados['autor'],
        "sinopse": dados['sinopse'],
        "genero": gen,
        "quantidade": dados['quantidade'],
        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
    }).execute()

def atualizar_quantidade_nuvem(isbn, qtd_adicional):
    # Primeiro busca a quantidade atual
    livro = buscar_livro_nuvem(isbn)
    qtd_atual = int(livro.iloc[0]['quantidade'])
    nova_qtd = qtd_atual + qtd_adicional
    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn).execute()

def buscar_dados_google(isbn):
    url_api = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        res = requests.get(url_api, timeout=10)
        if res.status_code == 200:
            dados = res.json()
            if "items" in dados:
                info = dados["items"][0]["volumeInfo"]
                return {
                    "titulo": info.get("title", "Não encontrado"),
                    "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                    "sinopse": info.get("description", "Sem sinopse disponível"),
                    "genero_sugerido": traduzir_genero(info.get("categories", ["General"])[0])
                }
    except: return None
    return None

# --- 5. INTERFACE ---

if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0

st.sidebar.title("📚 Acervo Cloud")
menu = st.sidebar.selectbox("Navegação", ["Entrada de Livros", "Ver Acervo e Exportar"])

if menu == "Entrada de Livros":
    st.header("🚚 Entrada (Nuvem)")
    
    foto_upload = st.file_uploader("📷 Foto do código de barras", type=['png', 'jpg', 'jpeg'], key=f"up_{st.session_state.reset_count}")
    
    if foto_upload:
        with st.spinner("Analisando imagem..."):
            img_pil = Image.open(foto_upload)
            img_pil.thumbnail((800, 800))
            img_cv = np.array(img_pil.convert('RGB'))
            img_cv = img_cv[:, :, ::-1].copy()
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            detector = cv2.barcode.BarcodeDetector()
            results = detector.detectAndDecode(gray)
            codigo_lido = results[0]
            final_isbn = str(codigo_lido[0]) if isinstance(codigo_lido, (list, tuple)) and len(codigo_lido) > 0 else str(codigo_lido)

            if final_isbn and len(final_isbn) > 5:
                st.success(f"✅ Detectado: {final_isbn}")
                if st.button("Confirmar e Carregar Dados"):
                    st.session_state.isbn_detectado = final_isbn
                    st.session_state.reset_count += 1
                    st.rerun()
            else: st.warning("⚠️ Código não detectado.")

    isbn_input = st.text_input("ISBN:", value=st.session_state.isbn_detectado, key=f"field_{st.session_state.reset_count}")

    if isbn_input:
        isbn_limpo = isbn_input.strip()
        livro_nuvem = buscar_livro_nuvem(isbn_limpo)

        if livro_nuvem is not None and not livro_nuvem.empty:
            st.info(f"📖 {livro_nuvem.iloc[0]['titulo']}")
            with st.form("form_inc"):
                qtd_add = st.number_input("Adicionar exemplares?", min_value=1, value=1)
                if st.form_submit_button("Atualizar na Nuvem"):
                    atualizar_quantidade_nuvem(isbn_limpo, qtd_add)
                    st.success("Atualizado no Supabase!")
                    time.sleep(1)
                    st.session_state.isbn_detectado = ""
                    st.session_state.reset_count += 1
                    st.rerun()
        else:
            dados_api = buscar_dados_google(isbn_limpo)
            if dados_api:
                st.success("✨ Novo título identificado!")
                titulo = st.text_input("Título", dados_api['titulo'])
                autor = st.text_input("Autor", dados_api['autor'])
                lista_gen = get_generos_da_nuvem()
                idx_def = lista_gen.index(dados_api['genero_sugerido']) if dados_api['genero_sugerido'] in lista_gen else 0
                gen_sel = st.selectbox("Gênero:", options=lista_gen, index=idx_def)
                gen_final = st.text_input("Novo gênero:") if gen_sel == "➕ CADASTRAR NOVO GÊNERO" else gen_sel
                sinopse = st.text_area("Sinopse", dados_api['sinopse'], height=150)
                quantidade = st.number_input("Quantidade:", min_value=1, value=1)
                
                if st.button("🚀 Salvar na Nuvem"):
                    salvar_novo_livro_nuvem({"isbn": isbn_limpo, "titulo": titulo, "autor": autor, "sinopse": sinopse, "genero": gen_final, "quantidade": quantidade})
                    st.success("Salvo com sucesso!")
                    time.sleep(1); st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()

elif menu == "Ver Acervo e Exportar":
    st.header("📊 Acervo Cloud")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        st.metric("Títulos na Nuvem", len(df))
        st.dataframe(df[['titulo', 'autor', 'genero', 'quantidade']], width='stretch')
        if st.button("📥 Gerar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for g in sorted(df['genero'].unique()):
                    aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']].to_excel(writer, index=False, sheet_name=aba)
            st.download_button(label="Baixar Excel", data=output.getvalue(), file_name="Acervo_Nuvem.xlsx")