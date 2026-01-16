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
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR (PADRÃO AEE CONECTA)
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
        st.error(f"⚠️ Erro de configuração na nuvem: {e}")
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
    "Research": "Pesquisa", "General": "Geral", "Art": "Artes",
    "Self-Help": "Autoajuda", "Technology & Engineering": "Tecnologia",
    "Cooking": "Culinária", "Mathematics": "Matemática", "Nature": "Natureza"
}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS_API.get(genero_ingles, genero_ingles)

# =================================================================
# 4. FUNÇÕES DE APOIO E BUSCA ROBUSTA (DUPLO SERVIÇO)
# =================================================================

def get_generos_dinamicos():
    """Busca gêneros na nuvem para evitar duplicatas na lista de seleção"""
    try:
        res = supabase.table("livros_acervo").select("genero").execute()
        generos_na_nuvem = [d['genero'] for d in res.data] if res.data else []
        lista_final = list(set(GENEROS_BASE + generos_na_nuvem))
        lista_final = [g for g in lista_final if g]
        lista_final.sort()
        lista_final.append("➕ CADASTRAR NOVO GÊNERO")
        return lista_final
    except:
        return GENEROS_BASE + ["➕ CADASTRAR NOVO GÊNERO"]

def buscar_livro_nuvem(isbn):
    """Verifica se livro já existe no Supabase"""
    try:
        res = supabase.table("livros_acervo").select("*").eq("isbn", str(isbn)).execute()
        return res.data
    except: return []

def buscar_dados_online(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    headers = {"User-Agent": "Mozilla/5.0"}

    # ===== GOOGLE BOOKS COM API KEY =====
    try:
        api_key = st.secrets["google"]["books_api_key"]
        url_google = (
            "https://www.googleapis.com/books/v1/volumes"
            f"?q=isbn:{isbn_limpo}&key={api_key}&langRestrict=pt"
        )

        res = requests.get(url_google, timeout=8)

        if res.status_code == 200:
            dados = res.json()
            if "items" in dados:
                info = dados["items"][0]["volumeInfo"]
                return {
                    "titulo": info.get("title", "Título não encontrado"),
                    "autor": ", ".join(info.get("authors", ["Desconhecido"])),
                    "sinopse": info.get("description", "Sem sinopse disponível"),
                    "genero": traduzir_genero(info.get("categories", ["General"])[0]),
                    "fonte": "Google Books (API Key)"
                }
    except Exception as e:
        st.warning(f"Google Books indisponível: {e}")

    # ===== BACKUP OPEN LIBRARY =====
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res = requests.get(url_ol, timeout=5)

        if res.status_code == 200 and f"ISBN:{isbn_limpo}" in res.json():
            info = res.json()[f"ISBN:{isbn_limpo}"]
            return {
                "titulo": info.get("title", "Título não encontrado"),
                "autor": ", ".join(a['name'] for a in info.get("authors", [{"name": "Desconhecido"}])),
                "sinopse": "Resumo não disponível nesta base.",
                "genero": "Geral",
                "fonte": "Open Library"
            }
    except:
        pass

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
    
    # --- ÁREA DO SCANNER ---
    foto_upload = st.file_uploader(
        "📷 Tire foto do código de barras", 
        type=['png', 'jpg', 'jpeg'], 
        key=f"up_{st.session_state.reset_count}"
    )
    
    if foto_upload:
        with st.spinner("Analisando imagem..."):
            file_bytes = np.asarray(bytearray(foto_upload.read()), dtype=np.uint8)
            img = cv2.imdecode(file_bytes, 1)
            # Redimensionamento para velocidade
            if img.shape[1] > 1000:
                scale = 1000 / img.shape[1]
                img = cv2.resize(img, (1000, int(img.shape[0] * scale)))
            
            detector = cv2.barcode.BarcodeDetector()
            resultado = detector.detectAndDecode(img)
            
            # Lógica de extração de texto (compatível com todas as versões do OpenCV)
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
            else:
                st.error("Não foi possível ler o código. Tente centralizar mais o código de barras.")

    st.divider()

    # --- ÁREA DE BUSCA E CADASTRO ---
    isbn_input = st.text_input(
        "ISBN Confirmado:", 
        value=st.session_state.isbn_detectado, 
        key=f"field_{st.session_state.reset_count}"
    )

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        livro_nuvem = buscar_livro_nuvem(isbn_limpo)

        if livro_nuvem:
            # --- CASO: EXISTE ---
            item = livro_nuvem[0]
            st.info(f"📖 Título: {item['titulo']} (Já cadastrado)")
            with st.form("form_incremento"):
                qtd_add = st.number_input("Adicionar quantos exemplares?", min_value=1, value=1)
                if st.form_submit_button("Atualizar Estoque na Nuvem"):
                    nova_qtd = int(item['quantidade']) + qtd_add
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!")
                    time.sleep(1.5)
                    st.session_state.isbn_detectado = ""
                    st.session_state.reset_count += 1
                    st.rerun()
        else:
            # --- CASO: NOVO ---
            with st.spinner("Buscando dados nos servidores..."):
                dados = buscar_dados_online(isbn_limpo)
                if not dados:
                    dados = {"titulo": "", "autor": "", "sinopse": "", "genero": "Geral", "fonte": "Manual"}
                
                st.success(f"Dados obtidos via: {dados['fonte']}")
                with st.form("form_novo_registro"):
                    titulo_f = st.text_input("Título", dados['titulo'])
                    autor_f = st.text_input("Autor", dados['autor'])
                    
                    lista_gen = get_generos_dinamicos()
                    idx_def = lista_gen.index(dados['genero']) if dados['genero'] in lista_gen else 0
                    gen_sel = st.selectbox("Selecione o Gênero:", options=lista_gen, index=idx_def)
                    gen_novo = st.text_input("Se escolheu 'CADASTRAR NOVO', digite aqui:")
                    
                    sinopse_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                    qtd_f = st.number_input("Quantidade inicial:", min_value=1, value=1)
                    
                    if st.form_submit_button("🚀 Salvar Novo Título no Supabase"):
                        gen_final = gen_novo.strip().capitalize() if gen_sel == "➕ CADASTRAR NOVO GÊNERO" else gen_sel
                        if gen_final in ["", "➕ CADASTRAR NOVO GÊNERO"]:
                            st.warning("Por favor, informe um gênero válido.")
                        else:
                            supabase.table("livros_acervo").insert({
                                "isbn": isbn_limpo, "titulo": titulo_f, "autor": autor_f, 
                                "sinopse": sinopse_f, "genero": gen_final, "quantidade": qtd_f,
                                "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                            }).execute()
                            st.success("Livro salvo com sucesso!")
                            time.sleep(1.5)
                            st.session_state.isbn_detectado = ""
                            st.session_state.reset_count += 1
                            st.rerun()

elif menu == "Ver Acervo e Exportar":
    st.header("📊 Acervo Registrado na Nuvem")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Títulos Diferentes", len(df))
        c2.metric("Total de Volumes", df['quantidade'].sum())
        
        st.dataframe(df[['titulo', 'autor', 'genero', 'quantidade']], width='stretch')
        
        if st.button("📥 Gerar Planilha Excel (Abas por Gênero)"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for g in sorted(df['genero'].unique()):
                    aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    # Ordem: Título, Sinopse e Autor
                    df_aba = df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']]
                    df_aba.to_excel(writer, index=False, sheet_name=aba)
            
            st.download_button(label="Baixar Excel", data=output.getvalue(), file_name="Acervo_Escolar.xlsx")
    else:
        st.info("O acervo na nuvem ainda está vazio.")