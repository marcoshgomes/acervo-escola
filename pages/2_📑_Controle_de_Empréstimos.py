import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
from supabase import create_client, Client

# Configuração e Segurança
st.set_page_config(page_title="Empréstimos", layout="centered", page_icon="📑")
supabase: Client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

# Se for aluno, não deixa entrar nesta página (Redireciona para o Início)
if st.session_state.get("perfil") == "Aluno":
    st.warning("Acesso restrito a Professores e Gestores.")
    if st.button("Voltar ao Início"): st.switch_page("🏠_Início.py")
    st.stop()

st.title("📑 Circulação de Livros")
aba1, aba2, aba3 = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])

# --- ABA 3: PESSOAS (Cadastro Simplificado) ---
with aba3:
    st.header("👤 Cadastro de Pessoas")
    res = supabase.table("usuarios").select("nome, turma").execute()
    df_u = pd.DataFrame(res.data)
    
    users_edit = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True)
    
    if st.button("💾 Salvar Alterações de Pessoas"):
        supabase.table("usuarios").delete().neq("id", 0).execute() # Limpa para sincronizar
        novos_dados = [{"nome": r['nome'], "turma": r['turma']} for _, r in users_edit.iterrows() if str(r['nome']).strip() != "None"]
        supabase.table("usuarios").insert(novos_dados).execute()
        st.success("Cadastro atualizado na Nuvem!"); st.rerun()

# --- ABA 1: EMPRESTAR (Com baixa no estoque) ---
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
            
            # 1. Registra Empréstimo
            supabase.table("emprestimos").insert({"id_livro": l_id, "id_usuario": u_id, "data_saida": dt_hoje, "data_retorno_prevista": dt_ret, "status": "Ativo"}).execute()
            # 2. Baixa Estoque
            qtd_atual = next(item['quantidade'] for item in res_l.data if item['id'] == l_id)
            supabase.table("livros_acervo").update({"quantidade": qtd_atual - 1}).eq("id", l_id).execute()
            
            st.success("Registrado na Nuvem com sucesso!"); time.sleep(1); st.rerun()

# --- ABA 2: DEVOLVER (Com retorno ao estoque) ---
with aba2:
    st.header("📥 Registrar Devolução")
    res_e = supabase.table("emprestimos").select("*, livros_acervo(titulo), usuarios(nome)").eq("status", "Ativo").execute()
    
    if res_e.data:
        df_e = pd.json_normalize(res_e.data)
        df_e["Selecionar"] = False
        # Ajuste nomes para exibição
        df_show = df_e[["Selecionar", "livros_acervo.titulo", "usuarios.nome", "data_retorno_prevista"]]
        edit_dev = st.data_editor(df_show, hide_index=True, use_container_width=True)
        
        sel = edit_dev[edit_dev["Selecionar"] == True]
        if not sel.empty:
            if st.button("Confirmar Retorno"):
                for i in sel.index:
                    emp = df_e.loc[i]
                    # 1. Finaliza Empréstimo
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", emp['id']).execute()
                    # 2. Devolve Estoque
                    res_estoque = supabase.table("livros_acervo").select("quantidade").eq("id", emp['id_livro']).execute()
                    nova_qtd = res_estoque.data[0]['quantidade'] + 1
                    supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("id", emp['id_livro']).execute()
                st.success("Estoque atualizado!"); time.sleep(1); st.rerun()
    else: st.info("Sem pendências.")