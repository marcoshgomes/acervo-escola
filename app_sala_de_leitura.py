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

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR
# =================================================================
st.set_page_config(page_title="Acervo Sala de Leitura Cloud", layout="centered", page_icon="📚")

st.markdown("""
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
""", unsafe_allow_html=True)

# =================================================================
# 2. CONEXÃO COM O BANCO DE DADOS (SUPABASE)
# =================================================================
@st.cache_resource
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"⚠️ Erro de conexão na nuvem: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. DICIONÁRIO DE TRADUÇÃO COMPLETO
# =================================================================
GENEROS_BASE = [
    "Ficção", "Infantil", "Juvenil", "Didático", "Poesia", 
    "Contos", "Biografia", "História", "Ciências", "Geografia", 
    "Artes", "Gibis/HQ", "Aventura", "Mistério", "Religião", "Filosofia"
]

TRADUCAO_GENEROS_API = {
    "Fiction": "Ficção", "Juvenile Fiction": "Ficção Juvenil", 
    "Juvenile Nonfiction": "Não-ficção Juvenil", "Education": "Didático", 
    "History": "História", "Science": "Ciências", "Philosophy": "Filosofia", 
    "Religion": "Religião", "Computers": "Informática", 
    "Biography & Autobiography": "Biografia", "Poetry": "Poesia", 
    "Drama": "Teatro", "Social Science": "Ciências Sociais", 
    "Research": "Pesquisa", "General": "Geral"
}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS_API.get(genero_ingles, genero_ingles)

# =================================================================
# 4. FUNÇÕES DE APOIO E BUSCA (CORREÇÃO GOOGLE CLOUD)
# =================================================================

def get_generos_dinamicos():
    try:
        res = supabase.table("livros_acervo").select("genero").execute()
        generos_na_nuvem = [d['genero'] for d in res.data] if res.data else []
        lista_final = list(set(GENEROS_BASE + generos_na_nuvem))
        lista_final = [g for g in lista_final if g]; lista_final.sort()
        lista_final.append("➕ CADASTRAR NOVO GÊNERO")
        return lista_final
    except: return GENEROS_BASE + ["➕ CADASTRAR NOVO GÊNERO"]

def buscar_livro_nuvem(isbn):
    try:
        res = supabase.table("livros_acervo").select("*").eq("isbn", str(isbn)).execute()
        return res.data
    except: return []

def buscar_dados_online(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    
    # Headers para simular um navegador real (Evita bloqueio do Google na nuvem)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    # 1. TENTATIVA: GOOGLE BOOKS COM API KEY E HEADERS
    try:
        api_key = st.secrets["google"]["books_api_key"]
        url_google = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key}"
        
        res = requests.get(url_google, headers=headers, timeout=10)

        if res.status_code == 200:
            dados = res.json()
            if "items" in dados:
                info = dados["items"][0]["volumeInfo"]
                return {
                    "titulo": info.get("title", "Título não encontrado"),
                    "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                    "sinopse": info.get("description", "Sem sinopse disponível"),
                    "genero": traduzir_genero(info.get("categories", ["General"])[0]),
                    "fonte": "Google Books (Cloud Verified)"
                }
            else:
                # Se o Google responder 200 mas sem itens, tentamos o backup
                st.write("🔍 Google não encontrou detalhes, tentando base de backup...")
    except Exception as e:
        st.warning(f"Google Books temporariamente instável na nuvem.")

    # 2. BACKUP: OPEN LIBRARY
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res_ol = requests.get(url_ol, headers=headers, timeout=8)

        if res_ol.status_code == 200:
            dados_ol = res_ol.json()
            key = f"ISBN:{isbn_limpo}"
            if key in dados_ol:
                info = dados_ol[key]
                return {
                    "titulo": info.get("title", "Título não encontrado"),
                    "autor": ", ".join([a['name'] for a in info.get("authors", [{"name": "Desconhecido"}])]),
                    "sinopse": "Resumo não disponível na base de backup.",
                    "genero": "Geral",
                    "fonte": "Open Library"
                }
    except: pass

    return None

# =================================================================
# 5. INTERFACE DO USUÁRIO
# =================================================================

if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0

st.sidebar.title("📚 Acervo Cloud")
if supabase: st.sidebar.success("✅ Conectado ao Supabase")

menu = st.sidebar.selectbox("Navegação", ["Entrada de Livros", "Ver Acervo e Exportar"])

if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    foto_upload = st.file_uploader("📷 Foto do código de barras", type=['png', 'jpg', 'jpeg'], key=f"up_{st.session_state.reset_count}")
    
    if foto_upload:
        with st.spinner("Analisando imagem..."):
            file_bytes = np.asarray(bytearray(foto_upload.read()), dtype=np.uint8)
            img = cv2.imdecode(file_bytes, 1)
            if img.shape[1] > 1000:
                scale = 1000 / img.shape[1]
                img = cv2.resize(img, (1000, int(img.shape[0] * scale)))
            
            detector = cv2.barcode.BarcodeDetector()
            resultado = detector.detectAndDecode(img)
            
            codigo_lido = ""
            if resultado and len(resultado) > 0:
                for item in resultado:
                    if isinstance(item, (list, tuple, np.ndarray)) and len(item) > 0:
                        if isinstance(item[0], str) and len(item[0]) > 5:
                            codigo_lido = item[0]
                            break

            if codigo_lido:
                st.success(f"✅ Código detectado: {codigo_lido}")
                if st.button("Confirmar e Carregar Dados"):
                    st.session_state.isbn_detectado = codigo_lido
                    st.session_state.reset_count += 1
                    st.rerun()

    st.divider()

    isbn_input = st.text_input("ISBN Confirmado:", value=st.session_state.isbn_detectado, key=f"field_{st.session_state.reset_count}")

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        livro_nuvem = buscar_livro_nuvem(isbn_limpo)

        if livro_nuvem:
            item = livro_nuvem[0]
            st.info(f"📖 {item['titulo']} (Já cadastrado)")
            with st.form("form_inc"):
                qtd_add = st.number_input("Adicionar exemplares?", min_value=1, value=1)
                if st.form_submit_button("Atualizar Estoque na Nuvem"):
                    nova_qtd = int(item['quantidade']) + qtd_add
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!")
                    time.sleep(1.5)
                    st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()
        else:
            with st.spinner("Buscando dados no Google Books..."):
                dados = buscar_dados_online(isbn_limpo)
                if not dados:
                    dados = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                
                st.success(f"Informações via: {dados['fonte']}")
                with st.form("form_novo_registro"):
                    titulo_f = st.text_input("Título", dados['titulo'])
                    autor_f = st.text_input("Autor", dados['autor'])
                    lista_gen = get_generos_dinamicos()
                    idx_def = lista_gen.index(dados['genero']) if dados['genero'] in lista_gen else 0
                    gen_sel = st.selectbox("Gênero", options=lista_gen, index=idx_def)
                    gen_novo = st.text_input("Novo Gênero (se aplicável):")
                    sinopse_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                    qtd_f = st.number_input("Quantidade inicial", min_value=1, value=1)
                    
                    if st.form_submit_button("🚀 Salvar no Supabase"):
                        gen_final = gen_novo.strip().capitalize() if gen_sel == "➕ CADASTRAR NOVO GÊNERO" else gen_sel
                        supabase.table("livros_acervo").insert({
                            "isbn": isbn_limpo, "titulo": titulo_f, "autor": autor_f, 
                            "sinopse": sinopse_f, "genero": gen_final, "quantidade": qtd_f,
                            "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                        }).execute()
                        st.success("Salvo com sucesso!")
                        time.sleep(1.5); st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()

elif menu == "Ver Acervo e Exportar":
    st.header("📊 Acervo Nuvem")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Títulos", len(df)); c2.metric("Volumes", df['quantidade'].sum())
        # Ajustado para largura total
        st.dataframe(df[['titulo', 'autor', 'genero', 'quantidade']], width=None)
        if st.button("📥 Gerar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for g in sorted(df['genero'].unique()):
                    aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']].to_excel(writer, index=False, sheet_name=aba)
            st.download_button(label="Baixar Excel", data=output.getvalue(), file_name="Acervo.xlsx")