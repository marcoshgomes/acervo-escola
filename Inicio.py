import streamlit as st
import pandas as pd
import requests
import time
import json
import numpy as np
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
        st.error(f"⚠️ Erro de conexão com o banco de dados: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. GERENCIAMENTO DE PERFIS E LOGIN
# =================================================================
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = "Aluno"

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def login_sistema():
    st.sidebar.title("🔐 Acesso Restrito")
    if st.session_state.perfil_logado == "Aluno":
        with st.sidebar.expander("👤 Entrar como Gestor/Professor"):
            senha = st.text_input("Senha:", type="password", key="login_pwd")
            if st.button("Validar"):
                if senha == SENHA_DIRETOR:
                    st.session_state.perfil_logado = "Diretor"
                    st.rerun()
                elif senha == SENHA_PROFESSOR:
                    st.session_state.perfil_logado = "Professor"
                    st.rerun()
                else:
                    st.error("Senha inválida")
    else:
        st.sidebar.info(f"Logado como: **{st.session_state.perfil_logado}**")
        if st.sidebar.button("🚪 Sair"):
            st.session_state.perfil_logado = "Aluno"
            st.rerun()

# =================================================================
# 4. MÓDULO: CADASTRO MANUAL (TODOS)
# =================================================================
def modulo_entrada_livros():
    st.header("🚚 Registro de Volumes")
    st.write("Insira os dados do livro manualmente.")
    
    with st.form("form_cadastro_manual", clear_on_submit=True):
        c1, c2 = st.columns(2)
        f_isbn = c1.text_input("ISBN (Opcional)")
        f_titulo = c2.text_input("Título do Livro (Obrigatório)*")
        f_autor = c1.text_input("Autor(es)", value="Pendente")
        f_gen = c2.text_input("Gênero", value="Geral")
        f_sin = st.text_area("Sinopse / Sumário", value="Pendente")
        f_qtd = st.number_input("Quantidade", min_value=1, value=1)
        
        if st.form_submit_button("🚀 Salvar no Sistema"):
            if not f_titulo:
                st.error("O título é obrigatório!")
            else:
                isbn_limpo = f_isbn.strip()
                existe = False
                if isbn_limpo:
                    res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
                    if res.data:
                        existe = True
                        nova_q = res.data[0]['quantidade'] + f_qtd
                        supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                        st.success("Estoque atualizado!")
                
                if not existe:
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": f_titulo, "autor": f_autor,
                        "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success("Livro cadastrado!")

# =================================================================
# 5. MÓDULO: GESTÃO DO ACERVO (PROF/DIR)
# =================================================================
def modulo_gestao():
    st.header("📊 Gestão e Curadoria")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        tabs = ["📋 Lista e Edição"]
        if st.session_state.perfil_logado == "Diretor":
            tabs += ["🪄 Curadoria IA", "📥 Importar Excel"]
        
        guias = st.tabs(tabs)
        
        with guias[0]:
            termo = st.text_input("🔍 Localizar livro:")
            df_f = df[df['titulo'].str.contains(termo, case=False)] if termo else df
            st.dataframe(df_f[['titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
            
            with st.expander("📝 Editar Registro"):
                opcoes = df_f.apply(lambda x: f"{x['titulo']} (ID:{x['id']})", axis=1).tolist()
                sel = st.selectbox("Selecione:", ["..."] + opcoes)
                if sel != "...":
                    id_s = int(sel.split("(ID:")[1].replace(")", ""))
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_manual"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("Salvar"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("Alterado!"); st.rerun()

        if st.session_state.perfil_logado == "Diretor":
            with guias[1]:
                api_k = st.text_input("Gemini API Key:", type="password")
                if api_k:
                    res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
                    df_p = pd.DataFrame(res_p.data)
                    if not df_p.empty:
                        if st.button("✨ Iniciar IA"):
                            prog = st.progress(0)
                            for i, row in df_p.iterrows():
                                prompt = f"Livro: {row['titulo']}. Retorne: Autor; Sinopse(3 linhas); Gênero. Use ';' como separador."
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
# 6. MÓDULO: CONTROLE DE EMPRÉSTIMOS (PROF/DIR)
# =================================================================
def modulo_emprestimos():
    st.header("📑 Controle de Empréstimos")
    tab_out, tab_in, tab_peo = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])
    
    # --- ABA: PESSOAS ---
    with tab_peo:
        st.subheader("Cadastro de Usuários")
        res_u = supabase.table("usuarios").select("nome, turma").execute()
        df_u = pd.DataFrame(res_u.data)
        edit_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_usuarios_lote")
        if st.button("💾 Salvar Pessoas"):
            supabase.table("usuarios").delete().neq("id", 0).execute()
            novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in edit_u.iterrows() if str(r['nome']) != "None"]
            if novos: supabase.table("usuarios").insert(novos).execute()
            st.success("Sincronizado com a nuvem!"); st.rerun()

    # --- ABA: EMPRESTAR ---
    with tab_out:
        # Busca livros com estoque e pessoas cadastradas
        res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        res_us = supabase.table("usuarios").select("id, nome, turma").execute()
        
        if not res_l.data or not res_us.data:
            st.warning("Certifique-se de que há livros no acervo e pessoas cadastradas na aba 'Pessoas'.")
        else:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_us.data}
            l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
            
            with st.form("form_venda"):
                u_id = st.selectbox("Selecione a Pessoa:", options=list(u_map.keys()), format_func=lambda x: u_map[x])
                l_id = st.selectbox("Selecione o Livro:", options=list(l_map.keys()), format_func=lambda x: l_map[x])
                if st.form_submit_button("🚀 Confirmar Empréstimo"):
                    # 1. Registra o empréstimo
                    supabase.table("emprestimos").insert({
                        "id_livro": l_id, "id_usuario": u_id, 
                        "data_saida": datetime.now().strftime('%d/%m/%Y'), "status": "Ativo"
                    }).execute()
                    # 2. Atualiza estoque
                    q_atual = next(i['quantidade'] for i in res_l.data if i['id'] == l_id)
                    supabase.table("livros_acervo").update({"quantidade": q_atual - 1}).eq("id", l_id).execute()
                    st.success("Empréstimo registrado!"); time.sleep(1); st.rerun()

    # --- ABA: DEVOLVER ---
    with tab_in:
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        if not res_e.data:
            st.info("Nenhum empréstimo ativo no momento.")
        else:
            df_e = pd.DataFrame(res_e.data)
            # Busca nomes para o merge
            df_livros_nomes = pd.DataFrame(supabase.table("livros_acervo").select("id, titulo").execute().data)
            df_users_nomes = pd.DataFrame(supabase.table("usuarios").select("id, nome").execute().data)
            
            # Cruzamento de dados seguro
            df_m = df_e.merge(df_livros_nomes, left_on='id_livro', right_on='id')
            df_m = df_m.merge(df_users_nomes, left_on='id_usuario', right_on='id')
            
            df_m["Selecionar"] = False
            edit_dev = st.data_editor(df_m[["Selecionar", "titulo", "nome", "data_saida"]], hide_index=True, use_container_width=True, key="devolve_grid")
            
            if st.button("Confirmar Devolução dos Selecionados"):
                for i in edit_dev[edit_dev["Selecionar"]].index:
                    item_id = df_m.loc[i, 'id_x'] # ID do empréstimo
                    livro_id = df_m.loc[i, 'id_livro']
                    
                    # 1. Finaliza empréstimo
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", item_id).execute()
                    # 2. Devolve estoque
                    res_estoque = supabase.table("livros_acervo").select("quantidade").eq("id", livro_id).execute()
                    nova_q = res_estoque.data[0]['quantidade'] + 1
                    supabase.table("livros_acervo").update({"quantidade": nova_q}).eq("id", livro_id).execute()
                
                st.success("Estoque atualizado!"); time.sleep(1); st.rerun()

# =================================================================
# 7. MAESTRO (CONTROLE DE NAVEGAÇÃO)
# =================================================================
login_sistema()

menu_opcoes = ["🏠 Boas-vindas", "🚚 Registro de Livros"]
if st.session_state.perfil_logado in ["Professor", "Diretor"]:
    menu_opcoes += ["📊 Gestão do Acervo", "📑 Controle de Empréstimos"]

escolha = st.sidebar.radio("Navegação", menu_opcoes)

if escolha == "🏠 Boas-vindas":
    st.title("🏠 Portal Sala de Leitura")
    st.write(f"Bem-vindo, **{st.session_state.perfil_logado}**!")
    st.info("Utilize o menu lateral para navegar.")

elif escolha == "🚚 Registro de Livros":
    modulo_entrada_livros()

elif escolha == "📊 Gestão do Acervo":
    modulo_gestao()

elif escolha == "📑 Controle de Empréstimos":
    modulo_emprestimos()