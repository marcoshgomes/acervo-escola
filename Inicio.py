import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Portal Sala de Leitura", layout="centered", page_icon="📚")

# Proteção contra tradutor
st.markdown("""<head><meta name="google" content="notranslate"></head>
    <script>document.documentElement.lang = 'pt-br'; document.documentElement.classList.add('notranslate');</script>""", unsafe_allow_html=True)

# Inicializa o estado do perfil
if "perfil" not in st.session_state:
    st.session_state.perfil = "Aluno"
if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

# --- 2. CONEXÃO SUPABASE ---
@st.cache_resource
def conectar_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

supabase = conectar_supabase()

# --- 3. FUNÇÃO DA TELA DE ENTRADA (CONTEÚDO DA HOME) ---
def tela_entrada_livros():
    st.header("🚚 Registro de Novos Volumes")
    st.info("Alunos e Professores: utilizem o campo abaixo para cadastrar livros ou atualizar o estoque.")

    isbn_input = st.text_input("Digite o Código ISBN:", key=f"field_{st.session_state.reset_count}")

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res.data:
            item = res.data[0]
            st.success(f"📖 Livro Localizado: {item['titulo']}")
            with st.form("f_inc"):
                add = st.number_input("Volumes novos:", 1)
                if st.form_submit_button("Atualizar Estoque"):
                    supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + add}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.reset_count += 1
                    time.sleep(1); st.rerun()
        else:
            with st.spinner("Buscando no Google Books..."):
                try:
                    api_key = st.secrets["google"]["books_api_key"]
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key}"
                    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
                    info = resp["items"][0]["volumeInfo"]
                    dados = {"t": info.get("title", ""), "a": ", ".join(info.get("authors", ["Pendente"])), "s": info.get("description", "Pendente")}
                except: dados = {"t": "", "a": "Pendente", "s": "Pendente"}
                
                with st.form("f_novo"):
                    t_f = st.text_input("Título", dados['t'])
                    a_f = st.text_input("Autor", dados['a'])
                    s_f = st.text_area("Sinopse", dados['s'])
                    q_f = st.number_input("Quantidade inicial", 1)
                    if st.form_submit_button("🚀 Salvar no Banco"):
                        supabase.table("livros_acervo").insert({
                            "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                            "sinopse": s_f, "genero": "Geral", "quantidade": q_f, 
                            "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                        }).execute()
                        st.success("Salvo com sucesso!"); st.session_state.reset_count += 1; time.sleep(1); st.rerun()

# --- 4. LÓGICA DE NAVEGAÇÃO E LOGIN NA SIDEBAR ---
st.sidebar.title("📚 Acervo Mara Cristina")
st.sidebar.write(f"Usuário: **{st.session_state.perfil}**")

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

# Sistema de Login (com chave única para evitar erro de duplicidade)
if st.session_state.perfil == "Aluno":
    with st.sidebar.expander("👤 Acesso Gestor / Professor"):
        senha = st.text_input("Senha:", type="password", key="login_key")
        if st.button("Entrar", key="btn_login"):
            if senha == SENHA_DIRETOR: 
                st.session_state.perfil = "Diretor"
                st.rerun()
            elif senha == SENHA_PROFESSOR: 
                st.session_state.perfil = "Professor"
                st.rerun()
            else: st.error("Senha inválida")
else:
    if st.sidebar.button("🚪 Sair do Perfil", key="btn_logout"):
        st.session_state.perfil = "Aluno"
        st.rerun()

# --- 5. CONFIGURAÇÃO DAS PÁGINAS ---
# Criamos a página inicial usando a função que definimos acima
pg_home = st.Page(tela_entrada_livros, title="Entrada de Livros", icon="🚚", default=True)

# Páginas dos arquivos na pasta /pages
pg_acervo = st.Page("pages/Acervo.py", title="Gestão de Acervo", icon="📊")
pg_emprestimos = st.Page("pages/Emprestimos.py", title="Controle de Empréstimos", icon="📑")

# Monta o menu baseado no perfil
if st.session_state.perfil == "Aluno":
    nav = st.navigation([pg_home])
else:
    nav = st.navigation([pg_home, pg_acervo, pg_emprestimos])

# Executa a navegação
nav.run()