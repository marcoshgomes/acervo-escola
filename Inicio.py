import streamlit as st
import pandas as pd
import requests
import time
import json
import numpy as np
from io import BytesIO
from datetime import datetime, timedelta
from supabase import create_client, Client

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR
# =================================================================
st.set_page_config(page_title="Sistema Integrado Sala de Leitura", layout="centered", page_icon="📚")

st.markdown("""
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
""", unsafe_allow_html=True)

# =================================================================
# 2. CONEXÃO SUPABASE
# =================================================================
@st.cache_resource
def conectar_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. DICIONÁRIO E APOIO
# =================================================================
GENEROS_BASE = ["Ficção", "Infantil", "Juvenil", "Didático", "Poesia", "História", "Ciências", "Artes", "Gibis/HQ", "Religião", "Filosofia"]

def traduzir_genero(genero_ingles):
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História"}
    return mapa.get(genero_ingles, "Geral")

# =================================================================
# 4. GERENCIAMENTO DE PERFIS (LOGIN)
# =================================================================
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = "Aluno"

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def login_sidebar():
    st.sidebar.title("🔐 Acesso Restrito")
    if st.session_state.perfil_logado == "Aluno":
        with st.sidebar.expander("👤 Entrar como Gestor"):
            senha = st.text_input("Senha:", type="password", key="login_pwd")
            if st.button("Validar Senha"):
                if senha == SENHA_DIRETOR:
                    st.session_state.perfil_logado = "Diretor"
                    st.rerun()
                elif senha == SENHA_PROFESSOR:
                    st.session_state.perfil_logado = "Professor"
                    st.rerun()
                else:
                    st.error("Senha incorreta")
    else:
        st.sidebar.write(f"Logado como: **{st.session_state.perfil_logado}**")
        if st.sidebar.button("🚪 Sair do Sistema"):
            st.session_state.perfil_logado = "Aluno"
            st.rerun()

# =================================================================
# 5. MÓDULO: CADASTRO MANUAL (ALUNO/PROF/DIR)
# =================================================================
def modulo_cadastro():
    st.header("🚚 Registro de Novos Volumes")
    st.write("Preencha os campos abaixo para cadastrar o livro.")
    
    with st.form("form_cadastro", clear_on_submit=True):
        col1, col2 = st.columns(2)
        f_isbn = col1.text_input("ISBN (Opcional)")
        f_titulo = col2.text_input("Título do Livro (Obrigatório)*")
        f_autor = col1.text_input("Autor", value="Pendente")
        f_gen = col2.text_input("Gênero", value="Geral")
        f_sin = st.text_area("Sinopse / Sumário", value="Pendente")
        f_qtd = st.number_input("Quantidade", min_value=1, value=1)
        
        if st.form_submit_button("🚀 Salvar no Sistema"):
            if not f_titulo:
                st.error("O título é obrigatório!")
            else:
                # Verifica duplicidade por ISBN
                existe = False
                if f_isbn.strip():
                    res = supabase.table("livros_acervo").select("*").eq("isbn", f_isbn.strip()).execute()
                    if res.data:
                        existe = True
                        nova_q = res.data[0]['quantidade'] + f_qtd
                        supabase.table("livros_acervo").update({"quantidade": nova_q}).eq("isbn", f_isbn.strip()).execute()
                        st.success("Estoque do livro atualizado!")
                
                if not existe:
                    supabase.table("livros_acervo").insert({
                        "isbn": f_isbn, "titulo": f_titulo, "autor": f_autor,
                        "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success(f"Livro '{f_titulo}' cadastrado com sucesso!")

# =================================================================
# 6. MÓDULO: GESTÃO E CURADORIA (PROF/DIR)
# =================================================================
def modulo_gestao():
    st.header("📊 Painel de Gestão")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        aba_list, aba_ia, aba_import = st.tabs(["📋 Lista e Edição", "🪄 Curadoria IA", "📥 Importar Excel"])
        
        with aba_list:
            busca = st.text_input("Localizar livro por título:")
            df_f = df[df['titulo'].str.contains(busca, case=False)] if busca else df
            st.dataframe(df_f[['titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
            
            with st.expander("📝 Editar Registro"):
                opcoes = df_f.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                sel = st.selectbox("Escolha:", ["..."] + opcoes)
                if sel != "...":
                    id_s = int(sel.split("| ID:")[1])
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_f"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        nq = st.number_input("Qtd", value=int(item['quantidade']))
                        if st.form_submit_button("Salvar"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("OK!"); st.rerun()

            if st.button("📥 Gerar Excel"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as wr:
                    for g in df['genero'].unique():
                        df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=str(g)[:30])
                st.download_button("Baixar Excel", output.getvalue(), "Acervo.xlsx")

        with aba_ia:
            if st.session_state.perfil_logado != "Diretor":
                st.info("Acesso restrito ao Diretor.")
            else:
                api_k = st.text_input("Gemini API Key:", type="password")
                if api_k:
                    res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
                    df_p = pd.DataFrame(res_p.data)
                    if not df_p.empty:
                        st.warning(f"{len(df_p)} registros pendentes.")
                        if st.button("✨ Iniciar IA"):
                            prog = st.progress(0)
                            for i, row in df_p.iterrows():
                                prompt = f"Livro: {row['titulo']}. Forneça: Autor; Sinopse(3 linhas); Gênero. Use ';' como separador."
                                url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_k}"
                                try:
                                    resp = requests.post(url_gem, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
                                    if resp.status_code == 200:
                                        partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                        if len(partes) >= 3:
                                            supabase.table("livros_acervo").update({"autor": partes[0].strip(), "sinopse": partes[1].strip(), "genero": partes[2].strip().capitalize()}).eq("id", row['id']).execute()
                                except: pass
                                prog.progress((i + 1) / len(df_p))
                            st.success("Fim!"); st.rerun()
        
        with aba_import:
            if st.session_state.perfil_logado == "Diretor":
                f_dir = st.file_uploader("Planilha do Diretor", type=['xlsx'])
                if f_dir:
                    try:
                        df_up = pd.read_excel(f_dir, sheet_name='livros escaneados')
                        if st.button("🚀 Importar Todos"):
                            dados_novos = []
                            for _, r in df_up.iterrows():
                                dados_novos.append({"isbn": str(r.get('ISBN','')), "titulo": str(r.get('Título','')), "autor": str(r.get('Autor(es)','Pendente')), "sinopse": str(r.get('Sinopse','Pendente')), "genero": str(r.get('Categorias','Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')})
                            supabase.table("livros_acervo").insert(dados_novos).execute()
                            st.success("Importado!"); st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")

# =================================================================
# 7. MÓDULO: EMPRÉSTIMOS (PROF/DIR)
# =================================================================
def modulo_emprestimos():
    st.header("📑 Controle de Empréstimos")
    t1, t2, t3 = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])
    
    with t3:
        res_u = supabase.table("usuarios").select("nome, turma").execute()
        df_u = pd.DataFrame(res_u.data)
        edit_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Salvar Pessoas"):
            supabase.table("usuarios").delete().neq("id", 0).execute()
            novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in edit_u.iterrows() if str(r['nome']) != "None"]
            if novos: supabase.table("usuarios").insert(novos).execute()
            st.success("Salvo!"); st.rerun()

    with t1:
        res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        res_us = supabase.table("usuarios").select("id, nome, turma").execute()
        if res_l.data and res_us.data:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_us.data}
            l_map = {d['id']: f"{d['titulo']} ({d['quantidade']})" for d in res_l.data}
            u_id = st.selectbox("Aluno:", options=list(u_map.keys()), format_func=lambda x: u_map[x])
            l_id = st.selectbox("Livro:", options=list(l_map.keys()), format_func=lambda x: l_map[x])
            if st.button("🚀 Confirmar Saída"):
                supabase.table("emprestimos").insert({"id_livro": l_id, "id_usuario": u_id, "data_saida": datetime.now().strftime('%d/%m/%Y'), "status": "Ativo"}).execute()
                q_nova = next(i['quantidade'] for i in res_l.data if i['id'] == l_id) - 1
                supabase.table("livros_acervo").update({"quantidade": q_nova}).eq("id", l_id).execute()
                st.success("Emprestado!"); time.sleep(1); st.rerun()

    with t2:
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        if res_e.data:
            df_e = pd.DataFrame(res_e.data)
            res_liv = supabase.table("livros_acervo").select("id, titulo").execute()
            res_pess = supabase.table("usuarios").select("id, nome").execute()
            df_m = df_e.merge(pd.DataFrame(res_liv.data), left_on='id_livro', right_on='id').merge(pd.DataFrame(res_pess.data), left_on='id_usuario', right_on='id')
            df_m["Selecionar"] = False
            edit_dev = st.data_editor(df_m[["Selecionar", "titulo", "nome"]], hide_index=True, use_container_width=True)
            if st.button("Confirmar Retorno"):
                for i in edit_dev[edit_dev["Selecionar"]].index:
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", df_m.loc[i, 'id_x']).execute()
                    res_q = supabase.table("livros_acervo").select("quantidade").eq("id", df_m.loc[i, 'id_livro']).execute()
                    supabase.table("livros_acervo").update({"quantidade": res_q.data[0]['quantidade'] + 1}).eq("id", df_m.loc[i, 'id_livro']).execute()
                st.success("Devolvido!"); st.rerun()

# =================================================================
# 8. MAESTRO (CONTROLE DE EXIBIÇÃO)
# =================================================================
login_sidebar()

# Menu principal na lateral
menu_opcoes = ["Boas-vindas", "Entrada de Livros"]
if st.session_state.perfil_logado in ["Professor", "Diretor"]:
    menu_opcoes.append("Gestão de Acervo")
    menu_opcoes.append("Empréstimos e Devoluções")

escolha = st.sidebar.radio("Navegação", menu_opcoes)

if escolha == "Boas-vindas":
    st.title("🏠 Portal Mara Cristina")
    st.write(f"Olá! Você está no portal da Sala de Leitura.")
    st.info("Utilize o menu lateral para navegar entre as funções disponíveis para o seu perfil.")

elif escolha == "Entrada de Livros":
    modulo_cadastro()

elif escolha == "Gestão de Acervo":
    modulo_gestao()

elif escolha == "Empréstimos e Devoluções":
    modulo_emprestimos()