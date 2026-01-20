import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONEXÃO COM O BANCO ---
@st.cache_resource
def conectar_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

supabase = conectar_supabase()

def traduzir_genero(genero_ingles):
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História"}
    return mapa.get(genero_ingles, "Geral")

# --- 2. INTERFACE ---
st.title("🚚 Registro de Novos Volumes")
st.info("Insira o ISBN para cadastrar ou atualizar o estoque.")

if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

isbn_input = st.text_input("Digite o Código ISBN:", placeholder="Ex: 9788532511010", key=f"field_{st.session_state.reset_count}")

if isbn_input:
    isbn_limpo = str(isbn_input).strip()
    # Verifica no Supabase
    res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
    
    if res_check.data:
        # CASO 1: LIVRO JÁ EXISTE
        item = res_check.data[0]
        st.success(f"📖 Livro Localizado: **{item['titulo']}**")
        with st.form("form_inc"):
            qtd_add = st.number_input("Adicionar exemplares?", 1)
            if st.form_submit_button("Atualizar Estoque"):
                nova_qtd = int(item['quantidade']) + qtd_add
                supabase.table("livros_acervo").update({"quantidade": nova_qtd}).eq("isbn", isbn_limpo).execute()
                st.success("Estoque atualizado!")
                st.session_state.reset_count += 1
                time.sleep(1); st.rerun()
    else:
        # CASO 2: BUSCA NO GOOGLE BOOKS (A lógica que você gosta)
        with st.spinner("Buscando informações bibliográficas..."):
            headers = {"User-Agent": "Mozilla/5.0"}
            try:
                api_key_google = st.secrets["google"]["books_api_key"]
                url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key_google}"
                res = requests.get(url, headers=headers).json()
                
                if "items" in res:
                    info = res["items"][0]["volumeInfo"]
                    dados = {
                        "titulo": info.get("title", ""), 
                        "autor": ", ".join(info.get("authors", ["Pendente"])), 
                        "sinopse": info.get("description", "Pendente"), 
                        "genero": traduzir_genero(info.get("categories", ["General"])[0])
                    }
                else:
                    dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
            except:
                dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
            
            with st.form("form_novo"):
                st.write("### ✨ Novo Título Detectado")
                t_f = st.text_input("Título", dados['titulo'])
                a_f = st.text_input("Autor", dados['autor'])
                s_f = st.text_area("Sinopse", dados['sinopse'], height=200)
                q_f = st.number_input("Quantidade inicial", 1)
                
                if st.form_submit_button("🚀 Salvar no Banco de Dados"):
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                        "sinopse": s_f, "genero": dados['genero'], "quantidade": q_f,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success("Livro salvo com sucesso!")
                    st.session_state.reset_count += 1
                    time.sleep(1); st.rerun()