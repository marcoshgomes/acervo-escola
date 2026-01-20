import streamlit as st
import pandas as pd
import requests
import json
import time
from io import BytesIO
from datetime import datetime
from supabase import create_client, Client

if "perfil_logado" not in st.session_state or st.session_state.perfil_logado is None:
    st.warning("Acesso negado. Por favor, identifique-se na página inicial.")
    st.stop()

# --- CONEXÃO ---
supabase: Client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

if st.session_state.get("perfil") == "Aluno":
    st.warning("Acesso restrito.")
    st.stop()

st.title("📊 Gestão e Curadoria")
tab1, tab2 = st.tabs(["📋 Lista e Edição", "🪄 Curadoria IA"])

with tab1:
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        busca = st.text_input("Localizar livro:")
        df_f = df[df['titulo'].str.contains(busca, case=False)] if busca else df
        st.dataframe(df_f[['titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
        # (Aqui continua seu código de edição manual que já funciona)

with tab2:
    if st.session_state.perfil != "Diretor":
        st.info("Apenas o Diretor pode usar a Inteligência Artificial.")
    else:
        st.subheader("Consertar Registros Incompletos")
        api_k = st.text_input("Gemini API Key:", type="password")
        if api_k:
            # Busca livros onde o autor ou sinopse estão como 'Pendente'
            res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
            df_p = pd.DataFrame(res_p.data)
            if not df_p.empty:
                st.warning(f"Existem {len(df_p)} livros para consertar.")
                if st.button("✨ Iniciar IA"):
                    prog = st.progress(0)
                    for i, row in df_p.iterrows():
                        # Lógica de Cascata: Tenta Google Books por Título e depois Gemini
                        # (O código de cascata que funcionou no seu PC vai aqui)
                        # Vou simplificar para o post do Gemini que você validou:
                        prompt = f"Livro: {row['titulo']}. Forneça: Autor; Sinopse(3 linhas); Gênero. Separe por ';'."
                        url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_k}"
                        try:
                            resp = requests.post(url_gem, headers={'Content-Type': 'application/json'}, 
                                                data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
                            if resp.status_code == 200:
                                partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                if len(partes) >= 3:
                                    supabase.table("livros_acervo").update({
                                        "autor": partes[0].strip(),
                                        "sinopse": partes[1].strip(),
                                        "genero": partes[2].strip().capitalize()
                                    }).eq("id", row['id']).execute()
                        except: pass
                        prog.progress((i + 1) / len(df_p))
                    st.success("Curadoria concluída!"); st.rerun()