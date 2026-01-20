import streamlit as st
import pandas as pd
import requests
import time
import json
from io import BytesIO
from datetime import datetime
from supabase import create_client, Client

# --- SEGURANÇA: Bloqueia acesso se não estiver logado ---
if "perfil" not in st.session_state or st.session_state.perfil == "Aluno":
    st.warning("⚠️ Acesso restrito a Professores e Diretores. Por favor, faça login na página inicial.")
    st.stop()

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def conectar_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

supabase = conectar_supabase()

st.title("📊 Gestão de Acervo e IA")

# Criação de Abas (Diretor vê a Curadoria IA, Professor não)
abas_opcoes = ["🔍 Pesquisa e Edição", "📥 Importar Planilha"]
if st.session_state.perfil == "Diretor":
    abas_opcoes.append("🪄 Curadoria com IA")

abas = st.tabs(abas_opcoes)

# --- ABA 1: PESQUISA E EDIÇÃO ---
with abas[0]:
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        termo = st.text_input("Localizar livro (Título ou ISBN):")
        df_filt = df[df['titulo'].str.contains(termo, case=False) | df['isbn'].str.contains(termo)] if termo else df
        st.dataframe(df_filt[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
        
        with st.expander("📝 Editar/Corrigir Registro"):
            opcoes = df_filt.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
            sel = st.selectbox("Escolha o livro:", ["..."] + opcoes)
            if sel != "...":
                id_sel = int(sel.split("| ID:")[1])
                item = df[df['id'] == id_sel].iloc[0]
                with st.form("ed_form"):
                    nt = st.text_input("Título", item['titulo'])
                    na = st.text_input("Autor", item['autor'])
                    ng = st.text_input("Gênero", item['genero'])
                    ns = st.text_area("Sinopse", item['sinopse'], height=150)
                    nq = st.number_input("Estoque", value=int(item['quantidade']))
                    if st.form_submit_button("💾 Salvar Alterações"):
                        supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_sel).execute()
                        st.success("Atualizado!"); st.rerun()

        if st.button("📥 Gerar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as wr:
                for g in sorted(df['genero'].unique()):
                    aba_nome = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    df[df['genero'] == g][['titulo', 'sinopse', 'autor', 'quantidade']].to_excel(wr, index=False, sheet_name=aba_nome)
            st.download_button("Baixar Excel", output.getvalue(), "Acervo.xlsx")

# --- ABA 2: IMPORTAR PLANILHA DO DIRETOR ---
with abas[1]:
    if st.session_state.perfil != "Diretor":
        st.info("Apenas o Diretor pode realizar importação de planilhas externas.")
    else:
        f = st.file_uploader("Suba a planilha 'livros escaneados'", type=['xlsx'])
        if f:
            try:
                df_up = pd.read_excel(f, sheet_name='livros escaneados')
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
                    if st.button("🚀 Importar"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                if conf:
                    st.warning(f"{len(conf)} duplicados."); st.dataframe(pd.DataFrame(conf)[['titulo', 'isbn']])
                    if st.button("➕ Forçar Importação"): supabase.table("livros_acervo").insert(conf).execute(); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

# --- ABA 3: CURADORIA IA (Google + Gemini) ---
if st.session_state.perfil == "Diretor":
    with abas[2]:
        api_k = st.text_input("Insira sua Gemini API Key:", type="password")
        if api_k:
            res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
            df_p = pd.DataFrame(res_p.data)
            if not df_p.empty:
                st.warning(f"{len(df_p)} registros incompletos.")
                if st.button("✨ Iniciar Curadoria Inteligente"):
                    prog, stxt = st.progress(0), st.empty()
                    api_g = st.secrets["google"]["books_api_key"]
                    for i, row in df_p.iterrows():
                        stxt.text(f"Processando: {row['titulo']}...")
                        f_a, f_s, f_g = row['autor'], row['sinopse'], row['genero']
                        try:
                            url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_g}"
                            rg = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                            if "items" in rg:
                                info = rg["items"][0]["volumeInfo"]
                                if f_a == "Pendente": f_a = ", ".join(info.get("authors", ["Pendente"]))
                                if f_s == "Pendente": f_s = info.get("description", "Pendente")
                        except: pass
                        if f_a == "Pendente" or f_s == "Pendente" or len(f_s) < 30:
                            prompt = f"Livro: {row['titulo']}. Responda apenas: Autor; Sinopse(3 linhas); Gênero. Use ';' como separador."
                            url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_k}"
                            try:
                                resp = requests.post(url_gem, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                                if resp.status_code == 200:
                                    partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                    if len(partes) >= 3:
                                        if f_a == "Pendente": f_a = partes[0].strip()
                                        f_s, f_g = partes[1].strip(), partes[2].strip().capitalize()
                            except: pass
                        supabase.table("livros_acervo").update({"autor": f_a, "sinopse": f_s, "genero": f_g}).eq("id", row['id']).execute()
                        prog.progress((i + 1) / len(df_p))
                    st.success("Concluído!"); st.rerun()
