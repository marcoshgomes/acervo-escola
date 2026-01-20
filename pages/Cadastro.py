import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
supabase: Client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

def traduzir_genero(genero_ingles):
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História"}
    return mapa.get(genero_ingles, "Geral")

st.title("🚚 Registro de Novos Volumes")
st.info("Utilize o campo abaixo para cadastrar livros ou atualizar o estoque.")

if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

isbn_input = st.text_input("Digite o Código ISBN:", key=f"field_{st.session_state.reset_count}")

if isbn_input:
    isbn_limpo = str(isbn_input).strip()
    res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
    
    if res.data:
        item = res.data[0]
        st.success(f"📖 Livro Localizado: {item['titulo']}")
        with st.form("f_inc"):
            add = st.number_input("Volumes novos:", 1)
            if st.form_submit_button("Atualizar Estoque"):
                supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + add}).eq("isbn", isbn_limpo).execute()
                st.success("Estoque atualizado!")
                st.session_state.reset_count += 1
                time.sleep(1); st.rerun()
    else:
        with st.spinner("Buscando no Google Books..."):
            try:
                api_key = st.secrets["google"]["books_api_key"]
                url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key}"
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
                info = resp["items"][0]["volumeInfo"]
                dados = {"t": info.get("title", ""), "a": ", ".join(info.get("authors", ["Pendente"])), "s": info.get("description", "Pendente")}
            except: dados = {"t": "", "a": "Pendente", "s": "Pendente"}
            
            with st.form("f_novo"):
                t_f = st.text_input("Título", dados['t'])
                a_f = st.text_input("Autor", dados['a'])
                s_f = st.text_area("Sinopse", dados['s'])
                q_f = st.number_input("Quantidade inicial", 1)
                if st.form_submit_button("🚀 Salvar no Banco"):
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                        "sinopse": s_f, "genero": "Geral", "quantidade": q_f, 
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success("Salvo com sucesso!"); st.session_state.reset_count += 1; time.sleep(1); st.rerun()