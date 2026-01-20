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
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História", "Computers": "Informática"}
    return mapa.get(genero_ingles, "Geral")

# --- 2. FUNÇÃO DE BUSCA UNIFICADA (GOOGLE + OPENLIB) ---
def buscar_dados_completos(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    dados_finais = {
        "titulo": "",
        "autor": "Pendente",
        "sinopse": "Pendente",
        "genero": "Geral",
        "fontes": []
    }

    # --- TENTATIVA 1: GOOGLE BOOKS ---
    try:
        api_key = st.secrets["google"]["books_api_key"]
        url_g = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key}"
        res_g = requests.get(url_g, headers=headers, timeout=8).json()
        
        if "items" in res_g:
            info = res_g["items"][0]["volumeInfo"]
            dados_finais["titulo"] = info.get("title", "")
            dados_finais["autor"] = ", ".join(info.get("authors", ["Pendente"]))
            desc = info.get("description", "Pendente")
            if desc != "Pendente":
                dados_finais["sinopse"] = desc
            dados_finais["genero"] = traduzir_genero(info.get("categories", ["General"])[0])
            dados_finais["fontes"].append("Google")
    except:
        pass

    # --- TENTATIVA 2: OPEN LIBRARY (Para completar o que falta) ---
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res_ol = requests.get(url_ol, headers=headers, timeout=8).json()
        key = f"ISBN:{isbn_limpo}"
        
        if key in res_ol:
            info_ol = res_ol[key]
            # Se o título ainda estiver vazio, usa o da OpenLib
            if not dados_finais["titulo"]:
                dados_finais["titulo"] = info_ol.get("title", "")
            
            # Se o autor estiver pendente, usa o da OpenLib
            if dados_finais["autor"] == "Pendente":
                autores = info_ol.get("authors", [])
                dados_finais["autor"] = ", ".join([a['name'] for a in autores]) if autores else "Pendente"
            
            # SEGREDO: Se a sinopse do Google for curta ou vazia e a OpenLib tiver algo, substitui
            sinopse_ol = info_ol.get("notes", "Pendente")
            if dados_finais["sinopse"] == "Pendente" and sinopse_ol != "Pendente":
                dados_finais["sinopse"] = sinopse_ol
            
            dados_finais["fontes"].append("OpenLibrary")
    except:
        pass

    return dados_finais if dados_finais["titulo"] else None

# --- 3. INTERFACE ---
st.title("🚚 Entrada de Novos Volumes")
st.write("O sistema busca dados no Google e OpenLibrary para gerar o cadastro mais completo possível.")

if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

isbn_input = st.text_input("Digite o ISBN:", placeholder="Ex: 9788532511010", key=f"in_{st.session_state.reset_count}")

if isbn_input:
    isbn_limpo = str(isbn_input).strip()
    
    # Verifica se já existe
    res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
    
    if res_db.data:
        item = res_db.data[0]
        st.success(f"📖 Livro já está no acervo: **{item['titulo']}**")
        with st.form("f_inc"):
            add = st.number_input("Quantidade nova:", 1)
            if st.form_submit_button("Atualizar Estoque"):
                supabase.table("livros_acervo").update({"quantidade": item['quantidade'] + add}).eq("isbn", isbn_limpo).execute()
                st.success("Estoque atualizado!")
                st.session_state.reset_count += 1
                time.sleep(1); st.rerun()
    else:
        with st.spinner("Fundindo dados das bibliotecas online..."):
            dados = buscar_dados_completos(isbn_limpo)
            
            if dados:
                st.info(f"Fontes utilizadas: {', '.join(dados['fontes'])}")
                with st.form("f_novo"):
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    s_f = st.text_area("Sinopse (Preenchida automaticamente)", dados['sinopse'], height=200)
                    g_f = st.text_input("Gênero", dados['genero'])
                    q_f = st.number_input("Quantidade inicial", 1)
                    
                    if st.form_submit_button("🚀 Confirmar Cadastro"):
                        supabase.table("livros_acervo").insert({
                            "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                            "sinopse": s_f, "genero": g_f, "quantidade": q_f,
                            "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                        }).execute()
                        st.success("Cadastrado com sucesso!")
                        st.session_state.reset_count += 1
                        time.sleep(1); st.rerun()
            else:
                st.warning("Não encontramos dados automáticos. Por favor, preencha manualmente.")
                # ... formulário manual se desejar ...