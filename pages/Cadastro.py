import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONEXÃO ---
supabase: Client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

st.title("🚚 Registro de Novos Volumes")
st.write("Preencha todos os campos para cadastrar o livro no acervo.")

# Formulário único com todos os campos abertos
with st.form("cadastro_manual", clear_on_submit=True):
    col1, col2 = st.columns(2)
    f_isbn = col1.text_input("ISBN (Opcional se for livro antigo)")
    f_titulo = col2.text_input("Título do Livro (Obrigatório)*")
    
    f_autor = col1.text_input("Autor", value="Pendente")
    f_genero = col2.text_input("Gênero / Categoria", value="Geral")
    
    f_sinopse = st.text_area("Sinopse / Sumário", value="Pendente", height=100)
    f_qtd = st.number_input("Quantidade de exemplares", min_value=1, value=1)
    
    enviar = st.form_submit_button("🚀 Cadastrar Livro no Sistema")

if enviar:
    if not f_titulo:
        st.error("O Título do livro é obrigatório para o cadastro!")
    else:
        # Verifica se o ISBN já existe para evitar duplicidade
        isbn_limpo = f_isbn.strip()
        existe = False
        if isbn_limpo:
            res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
            if res.data:
                existe = True
                item = res.data[0]
                # Se existe, apenas soma a quantidade
                nova_qtd = item['quantidade'] + f_qtd
                supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                st.success(f"Estoque de '{f_titulo}' atualizado!")
        
        if not existe:
            # Se não existe, cria novo registro
            supabase.table("livros_acervo").insert({
                "isbn": isbn_limpo, "titulo": f_titulo, "autor": f_autor, 
                "sinopse": f_sinopse, "genero": f_genero, "quantidade": f_qtd,
                "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
            }).execute()
            st.success(f"Livro '{f_titulo}' cadastrado com sucesso!")