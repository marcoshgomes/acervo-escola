import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONEXÃO ---
supabase: Client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

st.title("🚚 Registro de Novos Volumes")
st.write("Preencha os campos abaixo. Se não souber algum dado, deixe como 'Pendente'.")

if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

isbn_input = st.text_input("1. Digite o ISBN:", placeholder="Ex: 978...", key=f"field_{st.session_state.reset_count}")

if isbn_input:
    isbn_limpo = isbn_input.strip()
    res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
    
    if res_db.data:
        item = res_db.data[0]
        st.success(f"📖 Livro já existe: **{item['titulo']}**")
        with st.form("f_inc"):
            add = st.number_input("Adicionar unidades:", 1)
            if st.form_submit_button("Atualizar Estoque"):
                supabase.table("livros_acervo").update({"quantidade": item['quantidade'] + add}).eq("isbn", isbn_limpo).execute()
                st.success("Estoque atualizado!")
                st.session_state.reset_count += 1
                st.rerun()
    else:
        st.warning("✨ Livro novo! Preencha os dados abaixo:")
        with st.form("f_novo_manual"):
            t_f = st.text_input("Título Completo (Obrigatório)*")
            a_f = st.text_input("Autor", value="Pendente")
            g_f = st.text_input("Gênero / Categoria", value="Geral")
            s_f = st.text_area("Sinopse / Sumário", value="Pendente")
            q_f = st.number_input("Quantidade", 1)
            
            if st.form_submit_button("🚀 Salvar no Sistema"):
                if not t_f:
                    st.error("O título é obrigatório!")
                else:
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                        "sinopse": s_f, "genero": g_f, "quantidade": q_f,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success("Salvo com sucesso!")
                    st.session_state.reset_count += 1
                    st.rerun()