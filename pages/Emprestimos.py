import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- SEGURANÇA ---
if "perfil" not in st.session_state or st.session_state.perfil == "Aluno":
    st.warning("⚠️ Acesso restrito. Por favor, faça login na página inicial.")
    st.stop()

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def conectar_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

supabase = conectar_supabase()

st.title("📑 Controle de Empréstimos")
aba1, aba2, aba3 = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])

# --- ABA 3: PESSOAS ---
with aba3:
    st.subheader("Cadastro de Usuários")
    res_u = supabase.table("usuarios").select("nome, turma").execute()
    df_u = pd.DataFrame(res_u.data)
    edit_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True)
    if st.button("💾 Salvar Cadastro de Pessoas"):
        supabase.table("usuarios").delete().neq("id", 0).execute()
        novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in edit_u.iterrows() if str(r['nome']) != "None"]
        if novos: supabase.table("usuarios").insert(novos).execute()
        st.success("Atualizado!"); st.rerun()

# --- ABA 1: EMPRESTAR ---
with aba1:
    res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
    res_users = supabase.table("usuarios").select("id, nome, turma").execute()
    
    if res_l.data and res_users.data:
        u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_users.data}
        l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
        
        u_id = st.selectbox("Quem está pegando?", options=list(u_map.keys()), format_func=lambda x: u_map[x])
        l_id = st.selectbox("Qual o livro?", options=list(l_map.keys()), format_func=lambda x: l_map[x])
        prazo = st.select_slider("Prazo (dias):", [7, 15, 30], 15)
        
        if st.button("🚀 Confirmar Empréstimo"):
            dt_hoje = datetime.now().strftime('%d/%m/%Y')
            dt_ret = (datetime.now() + timedelta(days=prazo)).strftime('%d/%m/%Y')
            supabase.table("emprestimos").insert({"id_livro": l_id, "id_usuario": u_id, "data_saida": dt_hoje, "data_retorno_prevista": dt_ret, "status": "Ativo"}).execute()
            # Baixa estoque
            q_atual = next(i['quantidade'] for i in res_l.data if i['id'] == l_id)
            supabase.table("livros_acervo").update({"quantidade": q_atual - 1}).eq("id", l_id).execute()
            st.success("Registrado!"); time.sleep(1); st.rerun()

# --- ABA 2: DEVOLVER ---
with aba2:
    res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
    if res_e.data:
        df_e = pd.DataFrame(res_e.data)
        res_livros = supabase.table("livros_acervo").select("id, titulo").execute()
        res_users = supabase.table("usuarios").select("id, nome").execute()
        df_merge = df_e.merge(pd.DataFrame(res_livros.data), left_on='id_livro', right_on='id', suffixes=('','_l'))
        df_merge = df_merge.merge(pd.DataFrame(res_users.data), left_on='id_usuario', right_on='id', suffixes=('','_u'))
        df_merge["Selecionar"] = False
        edit_dev = st.data_editor(df_merge[["Selecionar", "titulo", "nome", "data_retorno_prevista"]], hide_index=True, use_container_width=True)
        if st.button("Confirmar Retorno"):
            for i in edit_dev[edit_dev["Selecionar"]].index:
                linha = df_merge.loc[i]
                supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", linha['id']).execute()
                res_q = supabase.table("livros_acervo").select("quantidade").eq("id", linha['id_livro']).execute()
                supabase.table("livros_acervo").update({"quantidade": res_q.data[0]['quantidade'] + 1}).eq("id", linha['id_livro']).execute()
            st.success("Estoque atualizado!"); time.sleep(1); st.rerun()
    else: st.info("Sem pendências.")
