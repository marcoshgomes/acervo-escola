import streamlit as st

# 1. Configuração da Página
st.set_page_config(page_title="Portal Sala de Leitura", layout="centered", page_icon="🏠")

# Proteção contra tradutor
st.markdown("""<head><meta name="google" content="notranslate"></head>
    <script>document.documentElement.lang = 'pt-br'; document.documentElement.classList.add('notranslate');</script>""", unsafe_allow_html=True)

# 2. Gerenciamento de Perfil Global
if "perfil" not in st.session_state:
    st.session_state.perfil = "Aluno"

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def verificar_senha():
    senha = st.session_state.pwd_input.strip()
    if senha == SENHA_DIRETOR: st.session_state.perfil = "Diretor"
    elif senha == SENHA_PROFESSOR: st.session_state.perfil = "Professor"
    else: st.error("Senha inválida")

# 3. Interface de Boas-Vindas
st.title("🏠 Bem-vindo à Sala de Leitura")
st.write(f"Você está acessando como: **{st.session_state.perfil}**")

if st.session_state.perfil == "Aluno":
    st.info("Utilize o menu lateral para registrar a entrada de livros.")
    with st.expander("👤 Acesso Gestor / Professor"):
        st.text_input("Digite sua senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    st.success(f"Acesso liberado para nível: {st.session_state.perfil}")
    if st.button("🚪 Sair do Sistema"):
        st.session_state.perfil = "Aluno"
        st.rerun()

st.divider()
st.write("### O que você deseja fazer hoje?")
c1, c2 = st.columns(2)

with c1:
    if st.button("📚 Ir para Gestão de Acervo", use_container_width=True):
        st.switch_page("pages/1_📚_Gestão_de_Acervo.py")

with c2:
    if st.button("📑 Ir para Empréstimos", use_container_width=True):
        st.switch_page("pages/2_📑_Controle_de_Empréstimos.py")
