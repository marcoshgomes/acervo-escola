import streamlit as st
import pandas as pd
import requests
import sqlite3
import time
import numpy as np
import cv2
from io import BytesIO
from datetime import datetime
from PIL import Image

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR (PADRÃO AEE CONECTA)
# =================================================================
st.set_page_config(page_title="Acervo Sala de Leitura", layout="centered", page_icon="📚")

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

# =================================================================
# 2. CONFIGURAÇÕES DE GÊNEROS E TRADUÇÕES COMPLETAS
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
# 3. FUNÇÕES DE BANCO DE DADOS (SQLite Local)
# =================================================================

def init_db():
    conn = sqlite3.connect('acervo_local.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS livros (id INTEGER PRIMARY KEY AUTOINCREMENT, isbn TEXT, titulo TEXT, autor TEXT, sinopse TEXT, genero TEXT, quantidade INTEGER, data_cadastro TEXT)''')
    conn.commit()
    conn.close()

def get_generos_do_banco():
    conn = sqlite3.connect('acervo_local.db')
    try:
        df = pd.read_sql_query("SELECT DISTINCT genero FROM livros", conn)
        generos_existentes = df['genero'].tolist()
    except: generos_existentes = []
    conn.close()
    lista = list(set(GENEROS_BASE + generos_existentes))
    lista = [g for g in lista if g]
    lista.sort()
    lista.append("➕ CADASTRAR NOVO GÊNERO")
    return lista

def buscar_livro_db(isbn):
    conn = sqlite3.connect('acervo_local.db')
    df = pd.read_sql_query("SELECT * FROM livros WHERE isbn = ?", conn, params=(isbn,))
    conn.close()
    return df if not df.empty else None

def salvar_novo_livro(dados):
    conn = sqlite3.connect('acervo_local.db')
    c = conn.cursor()
    gen = dados['genero'].strip().capitalize()
    c.execute('INSERT INTO livros (isbn, titulo, autor, sinopse, genero, quantidade, data_cadastro) VALUES (?,?,?,?,?,?,?)',
              (dados['isbn'], dados['titulo'], dados['autor'], dados['sinopse'], gen, dados['quantidade'], datetime.now().strftime('%d/%m/%Y %H:%M')))
    conn.commit()
    conn.close()

def atualizar_quantidade(isbn, qtd):
    conn = sqlite3.connect('acervo_local.db')
    c = conn.cursor()
    c.execute('UPDATE livros SET quantidade = quantidade + ? WHERE isbn = ?', (qtd, isbn))
    conn.commit()
    conn.close()

def buscar_dados_google(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        res = requests.get(url, timeout=10)
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

# =================================================================
# 4. INTERFACE DO USUÁRIO
# =================================================================

init_db()

# Session State para controle de limpeza
if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0

st.sidebar.title("📚 Gestão de Acervo")
menu = st.sidebar.selectbox("Navegação", ["Entrada de Livros", "Ver Acervo e Exportar"])

if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    # 1. ÁREA DE SCANNER OTIMIZADA
    foto_upload = st.file_uploader(
        "📷 Clique para tirar foto do código de barras", 
        type=['png', 'jpg', 'jpeg'],
        key=f"uploader_{st.session_state.reset_count}"
    )
    
    if foto_upload:
        with st.spinner("Lendo código rapidamente..."):
            # Usando PIL para abrir e redimensionar antes de passar para o OpenCV
            img_pil = Image.open(foto_upload)
            img_pil.thumbnail((800, 800)) # Reduz para no máx 800px (muito mais rápido)
            
            # Converte para formato OpenCV
            img_cv = np.array(img_pil.convert('RGB'))
            img_cv = img_cv[:, :, ::-1].copy() # RGB para BGR
            
            # Converte para Cinza (Barcode Detector trabalha melhor assim)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            detector = cv2.barcode.BarcodeDetector()
            results = detector.detectAndDecode(gray)
            
            codigo_lido = results[0]
            final_isbn = str(codigo_lido[0]) if isinstance(codigo_lido, (list, tuple)) and len(codigo_lido) > 0 else str(codigo_lido)

            if final_isbn and len(final_isbn) > 5:
                st.success(f"✅ Código detectado: {final_isbn}")
                if st.button("Confirmar e Carregar Dados"):
                    st.session_state.isbn_detectado = final_isbn
                    st.session_state.reset_count += 1
                    st.rerun()
            else:
                st.warning("⚠️ Código não detectado. Tente focar melhor e aproximar o celular.")

    st.divider()

    # 2. ÁREA DE DADOS
    isbn_input = st.text_input(
        "Confirme o ISBN abaixo:", 
        value=st.session_state.isbn_detectado,
        key=f"isbn_field_{st.session_state.reset_count}"
    )

    if isbn_input:
        isbn_limpo = isbn_input.strip()
        livro_no_banco = buscar_livro_db(isbn_limpo)

        if livro_no_banco is not None:
            # --- LIVRO JÁ EXISTE ---
            st.info(f"📖 Título: {livro_no_banco.iloc[0]['titulo']}")
            st.write(f"Estoque atual: **{livro_no_banco.iloc[0]['quantidade']}** volumes.")
            with st.form("form_inc"):
                qtd_add = st.number_input("Volumes adicionais:", min_value=1, value=1)
                if st.form_submit_button("Atualizar Estoque"):
                    atualizar_quantidade(isbn_limpo, qtd_add)
                    st.success("Estoque atualizado!")
                    time.sleep(1.5)
                    st.session_state.isbn_detectado = ""
                    st.session_state.reset_count += 1
                    st.rerun()
        else:
            # --- NOVO LIVRO ---
            with st.spinner("Buscando dados no Google Books..."):
                dados_api = buscar_dados_google(isbn_limpo)
                if dados_api:
                    st.success(f"✨ Novo título: {dados_api['titulo']}")
                    titulo = st.text_input("Título", dados_api['titulo'])
                    autor = st.text_input("Autor", dados_api['autor'])
                    lista_gen = get_generos_do_banco()
                    idx_def = lista_gen.index(dados_api['genero_sugerido']) if dados_api['genero_sugerido'] in lista_gen else 0
                    gen_sel = st.selectbox("Selecione o Gênero:", options=lista_gen, index=idx_def)
                    
                    gen_final = gen_sel
                    if gen_sel == "➕ CADASTRAR NOVO GÊNERO":
                        gen_final = st.text_input("Nome do novo gênero:")

                    sinopse = st.text_area("Sinopse", dados_api['sinopse'], height=150)
                    quantidade = st.number_input("Quantidade inicial:", min_value=1, value=1)
                    
                    if st.button("🚀 Confirmar Cadastro Completo"):
                        if gen_final in ["", "➕ CADASTRAR NOVO GÊNERO"]:
                            st.warning("Especifique um gênero.")
                        else:
                            salvar_novo_livro({"isbn": isbn_limpo, "titulo": titulo, "autor": autor, "sinopse": sinopse, "genero": gen_final, "quantidade": quantidade})
                            st.success("Livro cadastrado!")
                            time.sleep(1.5)
                            st.session_state.isbn_detectado = ""
                            st.session_state.reset_count += 1
                            st.rerun()
                else: st.error("Livro não encontrado.")

elif menu == "Ver Acervo e Exportar":
    st.header("📊 Acervo")
    conn = sqlite3.connect('acervo_local.db')
    df = pd.read_sql_query("SELECT * FROM livros", conn)
    conn.close()

    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("Títulos", len(df))
        c2.metric("Volumes", df['quantidade'].sum())
        
        st.dataframe(df[['titulo', 'autor', 'genero', 'quantidade']], width='stretch')
        
        if st.button("📥 Gerar Planilha Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for g in sorted(df['genero'].unique()):
                    aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    df_aba = df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']]
                    df_aba.to_excel(writer, index=False, sheet_name=aba)
            st.download_button(label="Baixar Excel", data=output.getvalue(), file_name="Acervo.xlsx")
    else: st.info("Acervo vazio.")