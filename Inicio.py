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
        st.error(f"Erro de conexão: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. GERENCIAMENTO DE PERFIS E SEGURANÇA
# =================================================================
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = "Aluno"

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def login_sessao():
    st.sidebar.title("🔐 Acesso Restrito")
    if st.session_state.perfil_logado == "Aluno":
        with st.sidebar.expander("👤 Login Gestor/Professor"):
            senha = st.text_input("Senha:", type="password", key="pwd_input")
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
        st.sidebar.write(f"Logado como: **{st.session_state.perfil_logado}**")
        if st.sidebar.button("🚪 Sair"):
            st.session_state.perfil_logado = "Aluno"
            st.rerun()

# =================================================================
# 4. MÓDULOS DO SISTEMA (FUNÇÕES)
# =================================================================

def modulo_entrada_manual():
    st.header("🚚 Registro de Volumes")
    st.info("Cadastro Manual: Preencha os campos abaixo para inserir o livro no acervo.")
    
    with st.form("form_cad_manual", clear_on_submit=True):
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
                # Verifica se o ISBN já existe para somar estoque
                res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute() if isbn_limpo else None
                
                if res and res.data:
                    nova_q = res.data[0]['quantidade'] + f_qtd
                    supabase.table("livros_acervo").update({"quantidade": nova_q}).eq("isbn", isbn_limpo).execute()
                    st.success(f"Estoque de '{f_titulo}' atualizado!")
                else:
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": f_titulo, "autor": f_autor,
                        "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success("Livro cadastrado com sucesso!")

def modulo_gestao_acervo():
    st.header("📊 Gestão e Curadoria")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        tabs_labels = ["📋 Lista e Edição"]
        if st.session_state.perfil_logado == "Diretor":
            tabs_labels += ["🪄 Curadoria IA (Gemini)", "📥 Importar Planilha"]
        
        guias = st.tabs(tabs_labels)
        
        with guias[0]:
            busca = st.text_input("🔍 Localizar por Título:")
            df_f = df[df['titulo'].str.contains(busca, case=False)] if busca else df
            st.dataframe(df_f[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Editar Registro"):
                opcoes = df_f.apply(lambda x: f"{x['titulo']} (ID:{x['id']})", axis=1).tolist()
                livro_sel = st.selectbox("Escolha o livro:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_s = int(livro_sel.split("(ID:")[1].replace(")", ""))
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("edit_manual"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=100)
                        nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("Salvar Alterações"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("Dados atualizados!"); st.rerun()

        if st.session_state.perfil_logado == "Diretor":
            with guias[1]:
                st.subheader("Curadoria Gemini 2.0 Flash")
                api_k = st.text_input("Gemini API Key:", type="password")
                if api_k:
                    res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
                    df_p = pd.DataFrame(res_p.data)
                    if not df_p.empty:
                        st.warning(f"Existem {len(df_p)} livros para consertar.")
                        if st.button("✨ Iniciar Processamento"):
                            prog = st.progress(0)
                            for i, row in df_p.iterrows():
                                prompt = f"Sobre o livro '{row['titulo']}', retorne: Autor; Sinopse Curta; Gênero. Use ';' como separador e nada mais."
                                url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_k}"
                                try:
                                    resp = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
                                    if resp.status_code == 200:
                                        partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                        if len(partes) >= 3:
                                            supabase.table("livros_acervo").update({"autor": partes[0].strip(), "sinopse": partes[1].strip(), "genero": partes[2].strip().capitalize()}).eq("id", row['id']).execute()
                                except: pass
                                prog.progress((i + 1) / len(df_p))
                            st.success("Concluído!"); st.rerun()
            
            with guias[2]:
                f_up = st.file_uploader("Upload Planilha 'livros escaneados'", type=['xlsx'])
                if f_up:
                    try:
                        df_excel = pd.read_excel(f_up, sheet_name='livros escaneados')
                        if st.button("🚀 Importar Planilha"):
                            novos = []
                            for _, r in df_excel.iterrows():
                                novos.append({"isbn": str(r.get('ISBN','')), "titulo": str(r.get('Título','')), "autor": str(r.get('Autor(es)','Pendente')), "sinopse": str(r.get('Sinopse','Pendente')), "genero": str(r.get('Categorias','Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')})
                            supabase.table("livros_acervo").insert(novos).execute()
                            st.success("Importação concluída!"); st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")

def modulo_emprestimos():
    st.header("📑 Circulação (Empréstimos)")
    t_out, t_in, t_peo = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])
    
    with t_peo:
        res_u = supabase.table("usuarios").select("nome, turma").execute()
        df_u = pd.DataFrame(res_u.data)
        edit_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Salvar Cadastro de Pessoas"):
            supabase.table("usuarios").delete().neq("id", 0).execute()
            novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in edit_u.iterrows() if str(r['nome']) != "None"]
            if novos: supabase.table("usuarios").insert(novos).execute()
            st.success("Atualizado!"); st.rerun()

    with t_out:
        res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        res_us = supabase.table("usuarios").select("id, nome, turma").execute()
        if res_l.data and res_us.data:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_us.data}
            l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
            u_id = st.selectbox("Aluno/Prof:", options=list(u_map.keys()), format_func=lambda x: u_map[x])
            l_id = st.selectbox("Livro:", options=list(l_map.keys()), format_func=lambda x: l_map[x])
            if st.button("🚀 Confirmar Saída"):
                supabase.table("emprestimos").insert({"id_livro": l_id, "id_usuario": u_id, "data_saida": datetime.now().strftime('%d/%m/%Y'), "status": "Ativo"}).execute()
                q_nova = next(i['quantidade'] for i in res_l.data if i['id'] == l_id) - 1
                supabase.table("livros_acervo").update({"quantidade": q_nova}).eq("id", l_id).execute()
                st.success("Emprestado!"); st.rerun()

    with t_in:
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        if res_e.data:
            df_e = pd.DataFrame(res_e.data)
            df_l = pd.DataFrame(supabase.table("livros_acervo").select("id, titulo").execute().data)
            df_u = pd.DataFrame(supabase.table("usuarios").select("id, nome").execute().data)
            df_m = df_e.merge(df_l, left_on='id_livro', right_on='id').merge(df_u, left_on='id_usuario', right_on='id')
            df_m["Selecionar"] = False
            edit_dev = st.data_editor(df_m[["Selecionar", "titulo", "nome"]], hide_index=True, use_container_width=True)
            if st.button("Confirmar Devolução"):
                for i in edit_dev[edit_dev["Selecionar"]].index:
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", df_m.loc[i, 'id_x']).execute()
                    res_q = supabase.table("livros_acervo").select("quantidade").eq("id", df_m.loc[i, 'id_livro']).execute()
                    supabase.table("livros_acervo").update({"quantidade": res_q.data[0]['quantidade'] + 1}).eq("id", df_m.loc[i, 'id_livro']).execute()
                st.success("Estoque Atualizado!"); st.rerun()
        else: st.info("Sem pendências.")

# =================================================================
# 5. MAESTRO (CONTROLE DE NAVEGAÇÃO)
# =================================================================
login_sessao()

# Menu principal
opcoes = ["🏠 Boas-vindas", "🚚 Cadastro de Livros"]
if st.session_state.perfil_logado in ["Professor", "Diretor"]:
    opcoes += ["📊 Gestão do Acervo", "📑 Empréstimos"]

escolha = st.sidebar.radio("Navegação", opcoes)

if escolha == "🏠 Boas-vindas":
    st.title("🏠 Portal Sala de Leitura")
    st.write(f"Bem-vindo, **{st.session_state.perfil_logado}**!")
    st.info("Utilize o menu lateral para acessar as funções.")

elif escolha == "🚚 Cadastro de Livros":
    modulo_entrada_manual()

elif escolha == "📊 Gestão do Acervo":
    modulo_gestao_acervo()

elif escolha == "📑 Empréstimos":
    modulo_emprestimos()