import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
from supabase import create_client, Client

if "perfil_logado" not in st.session_state or st.session_state.perfil_logado is None:
    st.warning("Acesso negado. Por favor, identifique-se na página inicial.")
    st.stop()

# Configuração da Página
st.set_page_config(page_title="Empréstimos", layout="centered", page_icon="📑")

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def conectar_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

supabase = conectar_supabase()

# TRAVA DE SEGURANÇA: Se não passou pelo Início, volta para lá
if "perfil" not in st.session_state or st.session_state.perfil == "Aluno":
    st.warning("⚠️ Acesso restrito. Por favor, identifique-se na página de Início.")
    if st.button("Ir para Início"):
        st.switch_page("🏠_Início.py")
    st.stop()

st.title("📑 Circulação de Livros")
aba1, aba2, aba3 = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])

# --- ABA 3: PESSOAS ---
with aba3:
    st.header("👤 Cadastro de Pessoas")
    res = supabase.table("usuarios").select("nome, turma").execute()
    df_u = pd.DataFrame(res.data)
    
    users_edit = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True, key="editor_pess")
    
    if st.button("💾 Salvar Alterações"):
        # Limpa e reinsere para simplificar a sincronização
        supabase.table("usuarios").delete().neq("id", 0).execute()
        novos_dados = [{"nome": r['nome'], "turma": r['turma']} for _, r in users_edit.iterrows() if str(r['nome']).strip() != "None"]
        if novos_dados:
            supabase.table("usuarios").insert(novos_dados).execute()
        st.success("Cadastro atualizado!"); time.sleep(1); st.rerun()

# --- ABA 1: EMPRESTAR ---
with aba1:
    st.header("Novo Empréstimo")
    res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
    res_u = supabase.table("usuarios").select("id, nome, turma").execute()
    
    if res_u.data and res_l.data:
        u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_u.data}
        l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
        
        u_id = st.selectbox("Quem está pegando?", options=list(u_map.keys()), format_func=lambda x: u_map[x])
        l_id = st.selectbox("Qual o livro?", options=list(l_map.keys()), format_func=lambda x: l_map[x])
        prazo = st.select_slider("Prazo (dias):", [7, 15, 30], 15)
        
        if st.button("🚀 Confirmar Empréstimo"):
            dt_hoje = datetime.now().strftime('%d/%m/%Y')
            dt_ret = (datetime.now() + timedelta(days=prazo)).strftime('%d/%m/%Y')
            
            # Registra na tabela de empréstimos
            supabase.table("emprestimos").insert({
                "id_livro": l_id, 
                "id_usuario": u_id, 
                "data_saida": dt_hoje, 
                "data_retorno_prevista": dt_ret, 
                "status": "Ativo"
            }).execute()
            
            # Baixa no estoque
            qtd_atual = next(item['quantidade'] for item in res_l.data if item['id'] == l_id)
            supabase.table("livros_acervo").update({"quantidade": qtd_atual - 1}).eq("id", l_id).execute()
            
            st.success("Empréstimo realizado!"); time.sleep(1); st.rerun()
    else:
        st.info("Cadastre pessoas e certifique-se de que há livros no estoque.")

# --- ABA 2: DEVOLVER (CORREÇÃO DO ERRO API) ---
with aba2:
    st.header("📥 Registrar Devolução")
    # Buscamos os dados das 3 tabelas separadamente para evitar o erro de relação (Join)
    res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
    res_livros = supabase.table("livros_acervo").select("id, titulo").execute()
    res_users = supabase.table("usuarios").select("id, nome").execute()
    
    if res_e.data:
        df_e = pd.DataFrame(res_e.data)
        df_l = pd.DataFrame(res_livros.data)
        df_u = pd.DataFrame(res_users.data)
        
        # Unimos as tabelas no Python (Pandas) em vez de pedir para o banco fazer
        df_merge = df_e.merge(df_l, left_on='id_livro', right_on='id', suffixes=('', '_liv'))
        df_merge = df_merge.merge(df_u, left_on='id_usuario', right_on='id', suffixes=('', '_user'))
        
        df_merge["Selecionar"] = False
        # Prepara visualização
        df_show = df_merge[["Selecionar", "titulo", "nome", "data_retorno_prevista"]]
        df_show.columns = ["Selecionar", "Livro", "Pessoa", "Data Prevista"]
        
        edit_dev = st.data_editor(df_show, hide_index=True, use_container_width=True)
        
        sel = edit_dev[edit_dev["Selecionar"] == True]
        if not sel.empty:
            if st.button(f"Confirmar Retorno de {len(sel)} livro(s)"):
                for i in sel.index:
                    linha = df_merge.loc[i]
                    # 1. Finaliza Empréstimo
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", linha['id']).execute()
                    # 2. Devolve Estoque
                    res_q = supabase.table("livros_acervo").select("quantidade").eq("id", linha['id_livro']).execute()
                    nova_qtd = res_q.data[0]['quantidade'] + 1
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("id", linha['id_livro']).execute()
                st.success("Estoque atualizado!"); time.sleep(1); st.rerun()
    else:
        st.info("Não há livros emprestados no momento.")