import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONEXÃO ---
supabase: Client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

def traduzir_genero(genero_ingles):
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História"}
    return mapa.get(genero_ingles, "Geral")

# --- 2. FUNÇÃO DE BUSCA REFORÇADA ---
def buscar_livro_multi_fontes(isbn):
    isbn_limpo = "".join(filter(str.isdigit, str(isbn)))
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # --- TENTATIVA 1: GOOGLE BOOKS ---
    try:
        api_key = st.secrets["google"]["books_api_key"]
        url_g = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key}"
        res_g = requests.get(url_g, headers=headers, timeout=10)
        
        if res_g.status_code == 200:
            dados = res_g.json()
            if "items" in dados:
                info = dados["items"][0]["volumeInfo"]
                return {
                    "titulo": info.get("title", ""),
                    "autor": ", ".join(info.get("authors", ["Pendente"])),
                    "sinopse": info.get("description", "Pendente"),
                    "genero": traduzir_genero(info.get("categories", ["General"])[0]),
                    "fonte": "Google Books"
                }
    except Exception as e:
        st.sidebar.warning(f"Google Offline: {e}")

    # --- TENTATIVA 2: OPEN LIBRARY (BACKUP) ---
    try:
        url_ol = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_limpo}&format=json&jscmd=data"
        res_ol = requests.get(url_ol, headers=headers, timeout=10)
        if res_ol.status_code == 200:
            dados_ol = res_ol.json()
            key = f"ISBN:{isbn_limpo}"
            if key in dados_ol:
                info = dados_ol[key]
                return {
                    "titulo": info.get("title", ""),
                    "autor": ", ".join([a['name'] for a in info.get("authors", [{"name": "Pendente"}])]),
                    "sinopse": "Sinopse não disponível na base de backup.",
                    "genero": "Geral",
                    "fonte": "Open Library"
                }
    except:
        pass

    return None

# --- 3. INTERFACE ---
st.title("🚚 Registro de Livros")

if "reset_count" not in st.session_state:
    st.session_state.reset_count = 0

isbn_input = st.text_input("Digite o ISBN (Harry Potter: 9788532511010):", key=f"field_{st.session_state.reset_count}")

if isbn_input:
    isbn_limpo = str(isbn_input).strip()
    
    # Primeiro checa se já existe no banco para não gastar API
    res_db = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
    
    if res_db.data:
        item = res_db.data[0]
        st.success(f"📖 Livro já cadastrado: {item['titulo']}")
        with st.form("f_inc"):
            add = st.number_input("Adicionar exemplares:", 1)
            if st.form_submit_button("Confirmar Atualização"):
                supabase.table("livros_acervo").update({"quantidade": item['quantidade'] + add}).eq("isbn", isbn_limpo).execute()
                st.success("Estoque atualizado!")
                st.session_state.reset_count += 1
                st.rerun()
    else:
        # Se não existe, busca na internet
        with st.spinner("Buscando dados bibliográficos..."):
            dados = buscar_livro_multi_fontes(isbn_limpo)
            
            if dados:
                st.success(f"✨ Dados encontrados via {dados['fonte']}")
                with st.form("f_novo"):
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                    q_f = st.number_input("Quantidade Inicial", 1)
                    if st.form_submit_button("🚀 Salvar no Sistema"):
                        supabase.table("livros_acervo").insert({
                            "isbn": isbn_limpo, "titulo": t_f, "autor": a_f, 
                            "sinopse": s_f, "genero": dados['genero'], "quantidade": q_f,
                            "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                        }).execute()
                        st.success("Livro cadastrado!")
                        st.session_state.reset_count += 1
                        st.rerun()
            else:
                st.error("❌ Não encontramos dados automáticos. Por favor, preencha manualmente:")
                with st.form("f_manual"):
                    t_m = st.text_input("Título")
                    a_m = st.text_input("Autor")
                    s_m = st.text_area("Sinopse")
                    q_m = st.number_input("Quantidade", 1)
                    if st.form_submit_button("Salvar Manualmente"):
                        supabase.table("livros_acervo").insert({
                            "isbn": isbn_limpo, "titulo": t_m, "autor": a_m, 
                            "sinopse": s_m, "genero": "Geral", "quantidade": q_m,
                            "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                        }).execute()
                        st.success("Salvo!")
                        st.session_state.reset_count += 1
                        st.rerun()