import streamlit as st
import pandas as pd
import requests
import time
import json
from io import BytesIO
from datetime import datetime, timedelta
from supabase import create_client, Client

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR
# =================================================================
st.set_page_config(page_title="Sistema Integrado Mara Cristina", layout="centered", page_icon="📚")

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
        st.error(f"⚠️ Erro de conexão na nuvem: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. SEGURANÇA E PERFIS (SENHAS FIXAS)
# =================================================================
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = "Aluno"
if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def login_gestor():
    st.sidebar.title("🔐 Acesso Restrito")
    if st.session_state.perfil_logado == "Aluno":
        with st.sidebar.expander("👤 Login Gestor/Professor"):
            senha = st.text_input("Senha:", type="password", key="login_pwd")
            if st.button("Validar Acesso"):
                if senha == SENHA_DIRETOR:
                    st.session_state.perfil_logado = "Diretor"
                    st.rerun()
                elif senha == SENHA_PROFESSOR:
                    st.session_state.perfil_logado = "Professor"
                    st.rerun()
                else:
                    st.error("Senha inválida")
    else:
        st.sidebar.write(f"Conectado como: **{st.session_state.perfil_logado}**")
        if st.sidebar.button("🚪 Sair do Sistema"):
            st.session_state.perfil_logado = "Aluno"
            st.rerun()

# =================================================================
# 4. MÓDULO: CADASTRO MANUAL (ALUNOS E TODOS)
# =================================================================
def modulo_entrada_livros():
    st.header("🚚 Registro de Volumes")
    st.info("Insira os dados do livro. Deixe 'Pendente' se não souber o autor ou sinopse.")
    
    with st.form("form_cadastro_manual", clear_on_submit=True):
        col1, col2 = st.columns(2)
        f_isbn = col1.text_input("ISBN (Opcional)")
        f_titulo = col2.text_input("Título do Livro (Obrigatório)*")
        f_autor = col1.text_input("Autor(es)", value="Pendente")
        f_gen = col2.text_input("Gênero", value="Geral")
        f_sin = st.text_area("Sinopse / Sumário", value="Pendente")
        f_qtd = st.number_input("Quantidade de Exemplares", min_value=1, value=1)
        
        if st.form_submit_button("🚀 Cadastrar no Sistema"):
            if not f_titulo:
                st.error("O título é obrigatório!")
            else:
                # Checa duplicidade pelo ISBN
                isbn_limpo = f_isbn.strip()
                existe = False
                if isbn_limpo:
                    res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
                    if res.data:
                        existe = True
                        nova_q = res.data[0]['quantidade'] + f_qtd
                        supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                        st.success(f"Estoque de '{f_titulo}' atualizado!")
                
                if not existe:
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": f_titulo, "autor": f_autor,
                        "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success(f"Livro '{f_titulo}' cadastrado com sucesso!")

# =================================================================
# 5. MÓDULO: GESTÃO DO ACERVO (PROF/DIR)
# =================================================================
def modulo_gestao():
    st.header("📊 Gestão do Acervo")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        tabs = ["📋 Lista e Edição"]
        if st.session_state.perfil_logado == "Diretor":
            tabs += ["🪄 Curadoria IA", "📥 Importar Planilha"]
        
        guias = st.tabs(tabs)
        
        with guias[0]:
            termo = st.text_input("🔍 Localizar por Título ou Autor:")
            df_filt = df[df['titulo'].str.contains(termo, case=False) | df['autor'].str.contains(termo, case=False)] if termo else df
            st.dataframe(df_filt[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Corrigir Registro Selecionado"):
                opcoes = df_filt.apply(lambda x: f"{x['titulo']} (ID:{x['id']})", axis=1).tolist()
                sel = st.selectbox("Escolha:", ["..."] + opcoes)
                if sel != "...":
                    id_s = int(sel.split("(ID:")[1].replace(")", ""))
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_f"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=150)
                        nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("💾 Salvar"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "sinopse": ns, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("Dados atualizados!"); st.rerun()

        if st.session_state.perfil_logado == "Diretor":
            with guias[1]:
                st.subheader("IA: Preenchimento Automático")
                api_k = st.text_input("Gemini API Key:", type="password")
                if api_k:
                    res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
                    df_p = pd.DataFrame(res_p.data)
                    if not df_p.empty:
                        st.warning(f"{len(df_p)} registros pendentes.")
                        if st.button("✨ Iniciar IA Gemini"):
                            prog, stxt = st.progress(0), st.empty()
                            for i, row in df_p.iterrows():
                                stxt.text(f"Processando: {row['titulo']}...")
                                prompt = f"Livro: {row['titulo']}. Retorne APENAS: Autor; Sinopse(3 linhas); Gênero. Use ';' como separador."
                                url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_k}"
                                try:
                                    resp = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
                                    if resp.status_code == 200:
                                        partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                        if len(partes) >= 3:
                                            supabase.table("livros_acervo").update({"autor": partes[0].strip(), "sinopse": partes[1].strip(), "genero": partes[2].strip().capitalize()}).eq("id", row['id']).execute()
                                except: pass
                                prog.progress((i + 1) / len(df_p))
                            st.success("Concluído!"); st.rerun()

# =================================================================
# 6. MÓDULO: EMPRÉSTIMOS (CIRCULAÇÃO)
# =================================================================
def modulo_emprestimos():
    st.header("📑 Controle de Empréstimos")
    t1, t2, t3 = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])
    
    with t3:
        st.subheader("Cadastro de Usuários")
        res_u = supabase.table("usuarios").select("nome, turma").execute()
        df_u = pd.DataFrame(res_u.data)
        edit_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Salvar Alterações de Pessoas"):
            supabase.table("usuarios").delete().neq("id", 0).execute()
            novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in edit_u.iterrows() if str(r['nome']) != "None"]
            if novos: supabase.table("usuarios").insert(novos).execute()
            st.success("Lista de pessoas atualizada!"); st.rerun()

    with t1:
        res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        res_us = supabase.table("usuarios").select("id, nome, turma").execute()
        if res_l.data and res_us.data:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_us.data}
            l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
            u_id = st.selectbox("Selecione o Aluno:", options=list(u_map.keys()), format_func=lambda x: u_map[x])
            l_id = st.selectbox("Selecione o Livro:", options=list(l_map.keys()), format_func=lambda x: l_map[x])
            if st.button("🚀 Confirmar Saída"):
                supabase.table("emprestimos").insert({"id_livro": l_id, "id_usuario": u_id, "data_saida": datetime.now().strftime('%d/%m/%Y'), "status": "Ativo"}).execute()
                q_atual = next(i['quantidade'] for i in res_l.data if i['id'] == l_id)
                supabase.table("livros_acervo").update({"quantidade": q_atual - 1}).eq("id", l_id).execute()
                st.success("Empréstimo realizado!"); time.sleep(1); st.rerun()

    with t2:
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        if res_e.data:
            df_e = pd.DataFrame(res_e.data)
            res_liv = supabase.table("livros_acervo").select("id, titulo").execute()
            res_pess = supabase.table("usuarios").select("id, nome").execute()
            df_m = df_e.merge(pd.DataFrame(res_liv.data), left_on='id_livro', right_on='id').merge(pd.DataFrame(res_pess.data), left_on='id_usuario', right_on='id')
            df_m["Selecionar"] = False
            edit_dev = st.data_editor(df_m[["Selecionar", "titulo", "nome"]], hide_index=True, use_container_width=True)
            if st.button("Confirmar Retorno"):
                for i in edit_dev[edit_dev["Selecionar"]].index:
                    linha = df_m.loc[i]
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", linha['id_x']).execute()
                    res_q = supabase.table("livros_acervo").select("quantidade").eq("id", linha['id_livro']).execute()
                    supabase.table("livros_acervo").update({"quantidade": res_q.data[0]['quantidade'] + 1}).eq("id", linha['id_livro']).execute()
                st.success("Livros devolvidos ao estoque!"); st.rerun()

# =================================================================
# 7. MAESTRO (CONTROLE DE EXIBIÇÃO)
# =================================================================
login_sidebar()

opcoes_menu = ["🏠 Início", "🚚 Registro de Livros"]
if st.session_state.perfil_logado in ["Professor", "Diretor"]:
    opcoes_menu += ["📊 Gestão do Acervo", "📑 Empréstimos"]

escolha = st.sidebar.radio("Navegação", opcoes_menu)

if escolha == "🏠 Início":
    st.title("🏠 Portal Sala de Leitura")
    st.write(f"Olá! Bem-vindo ao sistema da escola.")
    st.info("Utilize o menu lateral para acessar as funções de acordo com seu perfil.")
    if st.session_state.perfil_logado == "Aluno":
        st.write("Dica para Alunos: Para cadastrar novos livros que chegaram, use a opção **Registro de Livros**.")

elif escolha == "🚚 Registro de Livros":
    modulo_entrada_livros()

elif escolha == "📊 Gestão do Acervo":
    modulo_gestao()

elif escolha == "📑 Empréstimos":
    modulo_emprestimos()