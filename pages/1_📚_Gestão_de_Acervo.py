import streamlit as st
import pandas as pd
import requests
import time
import json
import numpy as np
from io import BytesIO
from datetime import datetime
from supabase import create_client, Client

# =================================================================
# 1. CONFIGURAÇÃO E SEGURANÇA DE PERFIL
# =================================================================
st.set_page_config(page_title="Gestão de Acervo", layout="centered", page_icon="📚")

# Proteção contra tradutor
st.markdown("""<head><meta name="google" content="notranslate"></head>
    <script>document.documentElement.lang = 'pt-br'; document.documentElement.classList.add('notranslate');</script>""", unsafe_allow_html=True)

# Verifica se o usuário passou pela tela de início
if "perfil" not in st.session_state:
    st.session_state.perfil = "Aluno"

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def conectar_supabase():
    try:
        return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    except:
        st.error("Erro de conexão com a nuvem.")
        return None

supabase = conectar_supabase()

# =================================================================
# 2. FUNÇÕES DE APOIO
# =================================================================
GENEROS_BASE = ["Ficção", "Infantil", "Juvenil", "Didático", "Poesia", "História", "Ciências", "Artes", "Gibis/HQ", "Religião", "Filosofia"]

def traduzir_genero(genero_ingles):
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História"}
    return mapa.get(genero_ingles, "Geral")

def get_generos_dinamicos():
    try:
        res = supabase.table("livros_acervo").select("genero").execute()
        generos_na_nuvem = [d['genero'] for d in res.data] if res.data else []
        lista = list(set(GENEROS_BASE + generos_na_nuvem))
        lista = [g for g in lista if g]; lista.sort()
        lista.append("➕ CADASTRAR NOVO GÊNERO")
        return lista
    except: return GENEROS_BASE + ["➕ CADASTRAR NOVO GÊNERO"]

# =================================================================
# 3. DEFINIÇÃO DE ABAS POR PERFIL
# =================================================================
st.title("📚 Gestão de Acervo")
st.write(f"Nível de acesso: **{st.session_state.perfil}**")

# Define quais abas aparecem para cada um
abas_disponiveis = ["🚚 Entrada de Livros"]
if st.session_state.perfil in ["Professor", "Diretor"]:
    abas_disponiveis.append("📋 Lista e Edição")
if st.session_state.perfil == "Diretor":
    abas_disponiveis.append("📥 Importar Excel")
    abas_disponiveis.append("🪄 Curadoria IA")

abas = st.tabs(abas_disponiveis)

# =================================================================
# ABA: ENTRADA DE LIVROS (TODOS)
# =================================================================
with abas[0]:
    st.subheader("Registro de Novos Exemplares")
    isbn_input = st.text_input("Digite o ISBN do livro:", placeholder="Ex: 9788532511010")

    if isbn_input:
        isbn_limpo = isbn_input.strip()
        res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res_check.data:
            item = res_check.data[0]
            st.info(f"📖 Livro: {item['titulo']} (Já cadastrado)")
            with st.form("f_inc"):
                add = st.number_input("Adicionar unidades:", 1)
                if st.form_submit_button("Atualizar Estoque"):
                    supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + add}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!"); time.sleep(1); st.rerun()
        else:
            with st.spinner("Buscando no Google..."):
                headers = {"User-Agent": "Mozilla/5.0"}
                try:
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={st.secrets['google']['books_api_key']}"
                    res = requests.get(url, headers=headers).json()
                    info = res["items"][0]["volumeInfo"]
                    dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                
                with st.form("f_novo"):
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    g_sel = st.selectbox("Gênero", get_generos_dinamicos())
                    g_novo = st.text_input("Se novo gênero:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=100)
                    q_f = st.number_input("Quantidade inicial", 1)
                    if st.form_submit_button("🚀 Salvar no Banco"):
                        gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                        supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                        st.success("Salvo com sucesso!"); time.sleep(1); st.rerun()

# =================================================================
# ABA: LISTA E EDIÇÃO (PROFESSOR E DIRETOR)
# =================================================================
if st.session_state.perfil in ["Professor", "Diretor"]:
    with abas[1]:
        st.subheader("Pesquisa e Correção")
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("🔍 Localizar por Título ou ISBN:")
            df_d = df[df['titulo'].str.contains(termo, case=False) | df['isbn'].str.contains(termo)] if termo else df
            st.dataframe(df_d[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Editar Registro"):
                opcoes = df_d.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Selecione:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_s = int(livro_sel.split("| ID:")[1])
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_form"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn'])
                        ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=150)
                        nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("💾 Salvar Alterações"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("Atualizado!"); st.rerun()
            
            if st.button("📥 Exportar para Excel"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as wr:
                    for g in df['genero'].unique():
                        aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                        df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=aba)
                st.download_button("Baixar Arquivo Excel", output.getvalue(), "Acervo.xlsx")

# =================================================================
# ABA: IMPORTAR EXCEL (SÓ DIRETOR)
# =================================================================
if st.session_state.perfil == "Diretor":
    with abas[2]:
        st.subheader("Importar Planilha do Diretor")
        f_diretor = st.file_uploader("Upload da Planilha 'livros escaneados'", type=['xlsx'])
        if f_diretor:
            try:
                df_up = pd.read_excel(f_diretor, sheet_name='livros escaneados')
                res_db = supabase.table("livros_acervo").select("isbn, titulo").execute()
                df_b = pd.DataFrame(res_db.data)
                novos, conf = [], []
                for _, row in df_up.iterrows():
                    i_u = str(row.get('ISBN', '')).strip().replace(".0", "")
                    t_u = str(row.get('Título', '')).strip()
                    match = False
                    if not df_b.empty:
                        if (i_u != "" and i_u in df_b['isbn'].values) or (df_b['titulo'].str.lower().values == t_u.lower()).any(): match = True
                    d = {"isbn": i_u if i_u != "nan" else "", "titulo": t_u, "autor": str(row.get('Autor(es)', 'Pendente')), "sinopse": str(row.get('Sinopse', 'Pendente')), "genero": str(row.get('Categorias', 'Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')}
                    if match: conf.append(d)
                    else: novos.append(d)
                if novos:
                    st.success(f"{len(novos)} novos livros."); 
                    if st.button("🚀 Confirmar Importação"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                if conf:
                    st.warning(f"{len(conf)} duplicados."); st.dataframe(pd.DataFrame(conf)[['titulo', 'isbn']])
                    if st.button("➕ Forçar Importação"): supabase.table("livros_acervo").insert(conf).execute(); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

# =================================================================
# ABA: CURADORIA IA (SÓ DIRETOR)
# =================================================================
if st.session_state.perfil == "Diretor":
    with abas[3]:
        st.subheader("Curadoria com Gemini 1.5 Flash")
        api_k = st.text_input("Gemini API Key:", type="password")
        if api_k:
            res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
            df_p = pd.DataFrame(res.data)
            if not df_p.empty:
                st.warning(f"Existem {len(df_p)} registros pendentes.")
                if st.button("✨ Iniciar Inteligência Artificial"):
                    prog, stxt = st.progress(0), st.empty()
                    for i, row in df_p.iterrows():
                        stxt.text(f"Limpando: {row['titulo']}...")
                        prompt = f"Livro: {row['titulo']}. Responda apenas: Autor; Sinopse Curta; Gênero. Use ';' como separador."
                        url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_k}"
                        try:
                            resp = requests.post(url_gem, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                            if resp.status_code == 200:
                                partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                if len(partes) >= 3:
                                    supabase.table("livros_acervo").update({"autor": partes[0].strip(), "sinopse": partes[1].strip(), "genero": partes[2].strip().capitalize()}).eq("id", row['id']).execute()
                        except: pass
                        prog.progress((i + 1) / len(df_p))
                    st.success("Concluído!"); st.rerun()