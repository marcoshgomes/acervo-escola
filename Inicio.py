import streamlit as st

# --- 1. CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Portal Sala de Leitura", layout="centered", page_icon="📚")

if "perfil" not in st.session_state:
    st.session_state.perfil = "Aluno"

# --- 2. LÓGICA DE LOGIN ---
SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def verificar_senha():
    senha = st.session_state.pwd_input.strip()
    if senha == SENHA_DIRETOR: st.session_state.perfil = "Diretor"
    elif senha == SENHA_PROFESSOR: st.session_state.perfil = "Professor"
    else: st.error("Senha inválida")

# --- 3. DEFINIÇÃO DA NAVEGAÇÃO ---
# Criamos as páginas apontando para os arquivos na pasta /pages
pg_cadastro = st.Page("pages/Cadastro.py", title="Entrada de Livros", icon="🚚", default=(st.session_state.perfil == "Aluno"))
pg_acervo = st.Page("pages/Acervo.py", title="Gestão de Acervo", icon="📊")
pg_emprestimos = st.Page("pages/Emprestimos.py", title="Controle de Empréstimos", icon="📑")
# Página de boas vindas
def welcome():
    st.title("📚 Sistema Sala de Leitura")
    st.write(f"Você está logado como: **{st.session_state.perfil}**")
    if st.session_state.perfil == "Aluno":
        st.info("Use o menu lateral para cadastrar livros.")
    else:
        st.success(f"Nível {st.session_state.perfil} ativo. Todos os módulos liberados.")
        if st.button("🚪 Sair / Logout"):
            st.session_state.perfil = "Aluno"
            st.rerun()

pg_welcome = st.Page(welcome, title="Painel de Acesso", icon="🏠", default=(st.session_state.perfil != "Aluno"))

# Monta o menu dinâmico
if st.session_state.perfil == "Aluno":
    nav = st.navigation({
        "Geral": [pg_welcome, pg_cadastro]
    })
else:
    nav = st.navigation({
        "Geral": [pg_welcome, pg_cadastro],
        "Administração": [pg_acervo, pg_emprestimos]
    })

# --- 4. BARRA LATERAL (LOGIN) ---
st.sidebar.title("Configurações")
if st.session_state.perfil == "Aluno":
    with st.sidebar.expander("🔐 Acesso Gestor / Professor"):
        st.text_input("Senha:", type="password", key="pwd_input", on_change=verificar_senha)

# Executa a navegação
nav.run()