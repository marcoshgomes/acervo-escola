import streamlit as st

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Portal Sala de Leitura", layout="centered", page_icon="📚")

# Proteção contra tradutor
st.markdown("""<head><meta name="google" content="notranslate"></head>
    <script>document.documentElement.lang = 'pt-br'; document.documentElement.classList.add('notranslate');</script>""", unsafe_allow_html=True)

# Inicializa o estado se não existir
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = None

# --- 2. LÓGICA DE NAVEGAÇÃO DINÂMICA ---
# Definimos as páginas como objetos
pg_welcome = st.Page(lambda: None, title="Portal de Acesso", icon="🏠") # Placeholder
pg_cadastro = st.Page("pages/Cadastro.py", title="Entrada de Livros", icon="🚚")
pg_acervo = st.Page("pages/Acervo.py", title="Gestão de Acervo", icon="📊")
pg_emprestimos = st.Page("pages/Emprestimos.py", title="Controle de Empréstimos", icon="📑")

# Montagem do Menu baseado na escolha feita na Home
if st.session_state.perfil_logado == "Aluno":
    nav = st.navigation({"Público": [pg_cadastro]})
elif st.session_state.perfil_logado in ["Professor", "Diretor"]:
    nav = st.navigation({
        "Operacional": [pg_cadastro, pg_emprestimos],
        "Gestão": [pg_acervo]
    })
else:
    # Se ninguém logou, o menu lateral fica vazio ou apenas com a Home
    nav = st.navigation([st.Page(lambda: st.write(""), title="Aguardando Login...", icon="🔒")])

# --- 3. CONTEÚDO DA TELA DE INÍCIO (O CHECK-IN) ---
if st.session_state.perfil_logado is None:
    st.title("📚 Sistema Integrado Mara Cristina")
    st.subheader("Para começar, selecione quem você é:")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("👨‍🎓 Sou Aluno", use_container_width=True):
            st.session_state.perfil_logado = "Aluno"
            st.rerun()
            
    with col2:
        if st.button("👩‍🏫 Sou Professor", use_container_width=True):
            st.session_state.temp_perfil = "Professor"
            
    with col3:
        if st.button("🔑 Sou Diretor", use_container_width=True):
            st.session_state.temp_perfil = "Diretor"

    # Campo de senha aparece se escolheu Prof ou Diretor
    if "temp_perfil" in st.session_state:
        st.write("---")
        senha = st.text_input(f"Digite a senha de {st.session_state.temp_perfil}:", type="password")
        if st.button("Confirmar Senha"):
            if st.session_state.temp_perfil == "Professor" and senha == "1359307":
                st.session_state.perfil_logado = "Professor"
                del st.session_state.temp_perfil
                st.rerun()
            elif st.session_state.temp_perfil == "Diretor" and senha == "7534833":
                st.session_logado = "Diretor"
                st.session_state.perfil_logado = "Diretor"
                del st.session_state.temp_perfil
                st.rerun()
            else:
                st.error("Senha incorreta!")
else:
    # Se já estiver logado, mostra opção de sair na sidebar
    st.sidebar.title("Configurações")
    st.sidebar.write(f"Conectado como: **{st.session_state.perfil_logado}**")
    if st.sidebar.button("🚪 Sair / Trocar Perfil"):
        st.session_state.perfil_logado = None
        st.rerun()
    
    st.title(f"Bem-vindo, {st.session_state.perfil_logado}!")
    st.info("Utilize o menu lateral para acessar as funcionalidades.")

# Executa o sistema de navegação
nav.run()