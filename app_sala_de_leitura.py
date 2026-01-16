import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import cv2  # OpenCV para leitura de código de barras
from io import BytesIO
from datetime import datetime
from PIL import Image
from supabase import create_client, Client

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR (PADRÃO AEE CONECTA)
# =================================================================
st.set_page_config(page_title="Acervo Sala de Leitura Cloud", layout="centered", page_icon="📚")

# Bloqueia o tradutor automático que pode quebrar o app
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
    """Tenta conectar ao Supabase usando as chaves dos Secrets"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"⚠️ Erro de conexão com a nuvem: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. TRADUÇÕES E CONFIGURAÇÕES DE GÊNEROS
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
    "Self-Help": "Autoajuda", "Technology & Engineering": "Tecnologia"
}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS_API.get(genero_ingles, genero_ingles)

# =================================================================
# 4. FUNÇÕES DE APOIO (BANCO DE DADOS E API)
# =================================================================

def get_generos_dinamicos():
    """Busca gêneros que já estão no Supabase para evitar duplicidade"""
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

def buscar_livro_no_supabase(isbn):
    """Verifica se o ISBN já existe na nuvem"""
    try:
        res = supabase.table("livros_acervo").select("*").eq("isbn", str(isbn)).execute()
        return res.data
    except:
        return []

def buscar_dados_google(isbn):
    """Consulta bibliografia no Google Books"""
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
    except:
        return None
    return None

# =================================================================
# 5. INTERFACE DO APLICATIVO
# =================================================================

# Controle de estado para limpeza de tela
if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0

st.sidebar.title("📚 Acervo Cloud")
if supabase: st.sidebar.success("✅ Supabase Conectado")
else: st.sidebar.error("❌ Erro na Nuvem")

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
            img_pil = Image.open(foto_upload)
            img_pil.thumbnail((800, 800)) # Otimização de velocidade
            img_cv = np.array(img_pil.convert('RGB'))
            img_cv = img_cv[:, :, ::-1].copy() # RGB para BGR
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            detector = cv2.barcode.BarcodeDetector()
            results = detector.detectAndDecode(gray)
            
            codigo_lido = results[0]
            # Trata se o retorno for lista ou string simples
            final_isbn = str(codigo_lido[0]) if isinstance(codigo_lido, (list, tuple)) and len(codigo_lido) > 0 else str(codigo_lido)

            if final_isbn and len(final_isbn) > 5:
                st.success(f"✅ Código detectado: {final_isbn}")
                if st.button("Confirmar e Carregar Dados"):
                    st.session_state.isbn_detectado = final_isbn
                    st.session_state.reset_count += 1
                    st.rerun()
            else:
                st.warning("⚠️ Código não lido. Tente focar melhor.")

    st.divider()

    # --- ÁREA DE CADASTRO ---
    isbn_input = st.text_input(
        "ISBN Confirmado:", 
        value=st.session_state.isbn_detectado, 
        key=f"field_{st.session_state.reset_count}"
    )

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        livro_nuvem = buscar_livro_no_supabase(isbn_limpo)

        if livro_nuvem:
            # --- CASO: LIVRO JÁ EXISTE NO SUPABASE ---
            item = livro_nuvem[0]
            st.info(f"📖 Título: {item['titulo']}")
            st.write(f"Estoque atual: **{item['quantidade']}** volumes.")
            with st.form("form_estoque"):
                qtd_add = st.number_input("Adicionar quantos novos volumes?", min_value=1, value=1)
                if st.form_submit_button("Atualizar na Nuvem"):
                    nova_qtd = int(item['quantidade']) + qtd_add
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado com sucesso!")
                    time.sleep(1.5)
                    st.session_state.isbn_detectado = ""
                    st.session_state.reset_count += 1
                    st.rerun()
        else:
            # --- CASO: NOVO LIVRO (BUSCA NO GOOGLE) ---
            with st.spinner("Buscando dados no Google Books..."):
                dados = buscar_dados_google(isbn_limpo)
                if not dados:
                    dados = {"titulo": "", "autor": "", "sinopse": "", "genero_sugerido": "Geral"}
                
                st.write("### ✨ Novo Cadastro")
                # Formulário para garantir que a tela não recarregue enquanto digita
                with st.form("form_novo_livro"):
                    titulo_f = st.text_input("Título", dados['titulo'])
                    autor_f = st.text_input("Autor", dados['autor'])
                    
                    lista_gen = get_generos_dinamicos()
                    idx_def = lista_gen.index(dados['genero_sugerido']) if dados['genero_sugerido'] in lista_gen else 0
                    gen_sel = st.selectbox("Gênero", options=lista_gen, index=idx_def)
                    gen_novo = st.text_input("Se escolheu 'CADASTRAR NOVO', digite aqui:")
                    
                    sinopse_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                    qtd_f = st.number_input("Quantidade inicial", min_value=1, value=1)
                    
                    if st.form_submit_button("🚀 Salvar Novo Título no Supabase"):
                        gen_final = gen_novo.strip().capitalize() if gen_sel == "➕ CADASTRAR NOVO GÊNERO" else gen_sel
                        
                        if gen_final == "" or gen_final == "➕ CADASTRAR NOVO GÊNERO":
                            st.warning("Por favor, informe um gênero válido.")
                        else:
                            try:
                                supabase.table("livros_acervo").insert({
                                    "isbn": isbn_limpo, "titulo": titulo_f, "autor": autor_f, 
                                    "sinopse": sinopse_f, "genero": gen_final, "quantidade": qtd_f,
                                    "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                                }).execute()
                                st.success("Livro salvo na nuvem!")
                                time.sleep(1.5)
                                st.session_state.isbn_detectado = ""
                                st.session_state.reset_count += 1
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")

elif menu == "Ver Acervo e Exportar":
    st.header("📊 Acervo Registrado (Nuvem)")
    try:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            c1, c2 = st.columns(2)
            c1.metric("Títulos Diferentes", len(df))
            c2.metric("Total de Volumes", df['quantidade'].sum())
            
            st.dataframe(df[['titulo', 'autor', 'genero', 'quantidade']], width='stretch')
            
            if st.button("📥 Gerar Planilha Excel"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for g in sorted(df['genero'].unique()):
                        aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                        # Ordem solicitada: Título, Sinopse, Autor
                        df_aba = df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']]
                        df_aba.to_excel(writer, index=False, sheet_name=aba)
                
                st.download_button(label="Baixar Excel", data=output.getvalue(), file_name="Acervo_Sala_Leitura.xlsx")
        else:
            st.info("O banco de dados na nuvem está vazio.")
    except Exception as e:
        st.error(f"Erro ao carregar acervo: {e}")