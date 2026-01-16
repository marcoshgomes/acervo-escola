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

# --- 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR ---
st.set_page_config(page_title="Acervo Sala de Leitura Cloud", layout="centered", page_icon="📚")

st.markdown("""
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO COM O SUPABASE ---
@st.cache_resource
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de conexão com a nuvem: {e}")
        return None

supabase = conectar_supabase()

# --- 3. TRADUÇÕES ---
GENEROS_BASE = ["Ficção", "Infantil", "Juvenil", "Didático", "Poesia", "História", "Ciências", "Artes", "Gibis/HQ", "Religião"]
TRADUCAO_GENEROS = {"Fiction": "Ficção", "Juvenile Fiction": "Ficção Juvenil", "Education": "Didático", "History": "História", "Science": "Ciências", "General": "Geral"}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS.get(genero_ingles, genero_ingles)

# --- 4. FUNÇÕES DE BUSCA (AQUI ESTÁ A MUDANÇA) ---

def buscar_dados_livro(isbn):
    """Tenta Google Books e depois Open Library como backup"""
    isbn = str(isbn).strip()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 1. TENTA GOOGLE BOOKS
    try:
        url_google = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        res = requests.get(url_google, headers=headers, timeout=5)
        if res.status_code == 200:
            dados = res.json()
            if "items" in dados:
                info = dados["items"][0]["volumeInfo"]
                return {
                    "titulo": info.get("title", "Título não encontrado"),
                    "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                    "sinopse": info.get("description", "Sem sinopse disponível"),
                    "genero": traduzir_genero(info.get("categories", ["General"])[0]),
                    "fonte": "Google Books"
                }
    except: pass

    # 2. TENTA OPEN LIBRARY (BACKUP GRATUITO)
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        res = requests.get(url_ol, headers=headers, timeout=5)
        if res.status_code == 200:
            dados = res.json()
            key = f"ISBN:{isbn}"
            if key in dados:
                info = dados[key]
                return {
                    "titulo": info.get("title", "Título não encontrado"),
                    "autor": ", ".join([a['name'] for a in info.get("authors", [{"name": "Desconhecido"}])]),
                    "sinopse": "Sumário não disponível nesta base.",
                    "genero": "Geral",
                    "fonte": "Open Library"
                }
    except: pass

    return None

def get_generos_dinamicos():
    try:
        res = supabase.table("livros_acervo").select("genero").execute()
        generos_nuvem = [d['genero'] for d in res.data] if res.data else []
        lista = list(set(GENEROS_BASE + generos_nuvem))
        lista = [g for g in lista if g]; lista.sort(); lista.append("➕ CADASTRAR NOVO GÊNERO")
        return lista
    except: return GENEROS_BASE + ["➕ CADASTRAR NOVO GÊNERO"]

# --- 5. INTERFACE ---
if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0

st.sidebar.title("📚 Acervo Cloud")
if supabase: st.sidebar.success("✅ Supabase Conectado")

menu = st.sidebar.selectbox("Navegação", ["Entrada de Livros", "Ver Acervo e Exportar"])

if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    foto_upload = st.file_uploader("📷 Foto do código de barras", type=['png', 'jpg', 'jpeg'], key=f"up_{st.session_state.reset_count}")
    
    if foto_upload:
        with st.spinner("Analisando código..."):
            file_bytes = np.asarray(bytearray(foto_upload.read()), dtype=np.uint8)
            img = cv2.imdecode(file_bytes, 1)
            # Redimensionamento
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
            else: st.error("Não detectamos o código. Tente centralizar mais.")

    st.divider()

    isbn_input = st.text_input("ISBN Confirmado:", value=st.session_state.isbn_detectado, key=f"field_{st.session_state.reset_count}")

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        # Verifica se já existe
        res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res_check.data:
            # --- JÁ EXISTE ---
            item = res_check.data[0]
            st.info(f"📖 Título: {item['titulo']} (Já cadastrado)")
            with st.form("form_inc"):
                qtd_add = st.number_input("Adicionar exemplares?", min_value=1, value=1)
                if st.form_submit_button("Atualizar na Nuvem"):
                    nova_qtd = int(item['quantidade']) + qtd_add
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!")
                    time.sleep(1); st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()
        else:
            # --- NOVO LIVRO (API) ---
            with st.spinner("Buscando dados em servidores bibliográficos..."):
                dados = buscar_dados_livro(isbn_limpo)
                if not dados:
                    dados = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                
                st.write(f"### ✨ Novo Cadastro (Fonte: {dados['fonte']})")
                with st.form("form_novo"):
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    lista_gen = get_generos_dinamicos()
                    idx_def = lista_gen.index(dados['genero']) if dados['genero'] in lista_gen else 0
                    g_sel = st.selectbox("Gênero", options=lista_gen, index=idx_def)
                    g_novo = st.text_input("Se cadastrou novo, digite aqui:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                    q_f = st.number_input("Quantidade inicial", min_value=1, value=1)
                    
                    if st.form_submit_button("🚀 Salvar no Supabase"):
                        g_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                        if g_final in ["", "➕ CADASTRAR NOVO GÊNERO"]:
                            st.warning("Especifique um gênero.")
                        else:
                            supabase.table("livros_acervo").insert({
                                "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                                "sinopse": s_f, "genero": g_final, "quantidade": q_f,
                                "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                            }).execute()
                            st.success("Salvo com sucesso!")
                            time.sleep(1); st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()

elif menu == "Ver Acervo e Exportar":
    st.header("📊 Acervo Nuvem")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Títulos", len(df)); c2.metric("Volumes", df['quantidade'].sum())
        st.dataframe(df[['titulo', 'autor', 'genero', 'quantidade']], width='stretch')
        if st.button("📥 Gerar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for g in sorted(df['genero'].unique()):
                    aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']].to_excel(writer, index=False, sheet_name=aba)
            st.download_button(label="Baixar Excel", data=output.getvalue(), file_name="Acervo.xlsx")