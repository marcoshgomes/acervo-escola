import streamlit as st

# --- 1. CONFIGURAÇÃO INICIAL (DEVE SER A PRIMEIRA LINHA) ---
st.set_page_config(page_title="Portal Sala de Leitura", layout="centered", page_icon="📚")

# Proteção contra tradutor
st.markdown("""<head><meta name="google" content="notranslate"></head>
    <script>document.documentElement.lang = 'pt-br'; document.documentElement.classList.add('notranslate');</script>""", unsafe_allow_html=True)

# Inicializa o perfil se não existir
if "perfil" not in st.session_state:
    st.session_state.perfil = "Aluno"

# --- 2. LÓGICA DE LOGIN ---
SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def verificar_senha():
    if "pwd_input" in st.session_state:
        senha = st.session_state.pwd_input.strip()
        if senha == SENHA_DIRETOR: 
            st.session_state.perfil = "Diretor"
        elif senha == SENHA_PROFESSOR: 
            st.session_state.perfil = "Professor"
        else: 
            st.error("Senha inválida")

# --- 3. DEFINIÇÃO DA NAVEGAÇÃO ---
# Criamos as páginas
pg_cadastro = st.Page("pages/Cadastro.py", title="Entrada de Livros", icon="🚚")
pg_acervo = st.Page("pages/Acervo.py", title="Gestão de Acervo", icon="📊")
pg_emprestimos = st.Page("pages/Emprestimos.py", title="Controle de Empréstimos", icon="📑")

# Página de boas vindas interna
def welcome():
    st.title("🏠 Sistema Integrado Sala de Leitura")
    st.write(f"Perfil atual: **{st.session_state.perfil}**")
    st.divider()
    if st.session_state.perfil == "Aluno":
        st.info("Utilize o menu lateral para acessar a 'Entrada de Livros'.")
    else:
        st.success(f"Nível {st.session_state.perfil} ativo. Todos os módulos liberados.")
        if st.button("🚪 Sair / Logout"):
            st.session_state.perfil = "Aluno"
            st.rerun()

pg_home = st.Page(welcome, title="Painel de Acesso", icon="🏠", default=True)

# Monta o menu dinâmico
if st.session_state.perfil == "Aluno":
    nav = st.navigation([pg_home, pg_cadastro])
else:
    nav = st.navigation({
        "Geral": [pg_home, pg_cadastro],
        "Administração": [pg_acervo, pg_emprestimos]
    })

# --- 4. BARRA LATERAL (LOGIN) ---
st.sidebar.title("Configurações")
if st.session_state.perfil == "Aluno":
    with st.sidebar.expander("👤 Acesso Gestor / Professor"):
        st.text_input("Senha:", type="password", key="pwd_input", on_change=verificar_senha)

# Executa a navegação
nav.run()