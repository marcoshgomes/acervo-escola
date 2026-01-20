import streamlit as st

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal Sala de Leitura", layout="centered", page_icon="📚")

# Proteção contra tradutor
st.markdown("""<head><meta name="google" content="notranslate"></head>
    <script>document.documentElement.lang = 'pt-br'; document.documentElement.classList.add('notranslate');</script>""", unsafe_allow_html=True)

# Inicializa o perfil se não existir
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = None

# --- 2. LÓGICA DE LOGIN ---
SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def realizar_login(perfil_alvo, senha_digitada):
    if perfil_alvo == "Professor" and senha_digitada == SENHA_PROFESSOR:
        st.session_state.perfil_logado = "Professor"
        st.success("Login realizado!")
        st.rerun()
    elif perfil_alvo == "Diretor" and senha_digitada == SENHA_DIRETOR:
        st.session_state.perfil_logado = "Diretor"
        st.success("Login realizado!")
        st.rerun()
    else:
        st.error("Senha incorreta!")

# --- 3. DEFINIÇÃO DA NAVEGAÇÃO DINÂMICA ---
pg_cadastro = st.Page("pages/Cadastro.py", title="Entrada de Livros", icon="🚚")
pg_acervo = st.Page("pages/Acervo.py", title="Gestão de Acervo", icon="📊")
pg_emprestimos = st.Page("pages/Emprestimos.py", title="Controle de Empréstimos", icon="📑")

# Monta o menu baseado no login
if st.session_state.perfil_logado == "Aluno":
    nav = st.navigation({"Público": [pg_cadastro]})
elif st.session_state.perfil_logado in ["Professor", "Diretor"]:
    nav = st.navigation({
        "Operacional": [pg_cadastro, pg_emprestimos],
        "Gestão": [pg_acervo]
    })
else:
    # Se ninguém logou, o menu lateral fica vazio
    nav = st.navigation([st.Page(lambda: None, title="Portal de Acesso", icon="🔒")])

# --- 4. TELA DE CHECK-IN (HOME) ---
if st.session_state.perfil_logado is None:
    st.title("📚 Sistema Integrado Mara Cristina")
    st.subheader("Escolha seu perfil para acessar o sistema:")
    
    col1, col2, col3 = st.columns(3)
    
    if col1.button("👨‍🎓 Sou Aluno", use_container_width=True):
        st.session_state.perfil_logado = "Aluno"
        st.rerun()
            
    if col2.button("👩‍🏫 Sou Professor", use_container_width=True):
        st.session_state.tentando_perfil = "Professor"
            
    if col3.button("🔑 Sou Diretor", use_container_width=True):
        st.session_state.tentando_perfil = "Diretor"

    if "tentando_perfil" in st.session_state:
        st.write("---")
        senha = st.text_input(f"Digite a senha de {st.session_state.tentando_perfil}:", type="password")
        if st.button("Entrar"):
            realizar_login(st.session_state.tentando_perfil, senha)
else:
    # Sidebar informativa
    st.sidebar.title("Configurações")
    st.sidebar.write(f"Conectado: **{st.session_state.perfil_logado}**")
    if st.sidebar.button("🚪 Sair / Trocar Perfil"):
        st.session_state.perfil_logado = None
        st.rerun()
    
    st.title(f"Bem-vindo, {st.session_state.perfil_logado}!")
    st.info("Acesse as ferramentas através do menu lateral à esquerda.")

# Rodar navegação
nav.run()