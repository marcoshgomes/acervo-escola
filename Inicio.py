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
# 2. CONEXÃO COM O BANCO DE DADOS (SUPABASE)
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
# 4. GERENCIAMENTO DE PERFIS E LOGIN
# =================================================================
if "perfil_logado" not in st.session_state:
    st.session_state.perfil_logado = "Aluno"

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def login_sistema():
    st.sidebar.title("🔐 Acesso Restrito")
    if st.session_state.perfil_logado == "Aluno":
        with st.sidebar.expander("👤 Login Gestor/Professor"):
            senha = st.text_input("Senha:", type="password", key="login_pwd_input")
            if st.button("Validar Acesso"):
                if senha == SENHA_DIRETOR:
                    st.session_state.perfil_logado = "Diretor"
                    st.rerun()
                elif senha == SENHA_PROFESSOR:
                    st.session_state.perfil_logado = "Professor"
                    st.rerun()
                else:
                    st.error("Senha incorreta")
    else:
        st.sidebar.write(f"Conectado como: **{st.session_state.perfil_logado}**")
        if st.sidebar.button("🚪 Sair / Logout"):
            st.session_state.perfil_logado = "Aluno"
            st.rerun()

# =================================================================
# 5. MÓDULO: CADASTRO MANUAL (ALUNOS E TODOS)
# =================================================================
def modulo_entrada_livros():
    st.header("🚚 Registro de Volumes")
    st.info("Insira os dados do livro manualmente.")
    
    with st.form("form_cadastro_manual", clear_on_submit=True):
        col1, col2 = st.columns(2)
        f_isbn = col1.text_input("ISBN (Opcional)")
        f_titulo = col2.text_input("Título do Livro (Obrigatório)*")
        f_autor = col1.text_input("Autor(es)", value="Pendente")
        f_gen = col2.text_input("Gênero", value="Geral")
        f_sin = st.text_area("Sinopse / Sumário", value="Pendente")
        f_qtd = st.number_input("Quantidade de Exemplares", min_value=1, value=1)
        
        if st.form_submit_button("🚀 Salvar no Sistema"):
            if not f_titulo:
                st.error("O título é obrigatório!")
            else:
                isbn_limpo = f_isbn.strip()
                existe = False
                if isbn_limpo:
                    res = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
                    if res.data:
                        existe = True
                        nova_q = res.data[0]['quantidade'] + f_qtd
                        supabase.table("livros_acervo").update({"quantidade": nova_q}).eq("isbn", isbn_limpo).execute()
                        st.success(f"Estoque de '{f_titulo}' atualizado!")
                
                if not existe:
                    supabase.table("livros_acervo").insert({
                        "isbn": isbn_limpo, "titulo": f_titulo, "autor": f_autor,
                        "sinopse": f_sin, "genero": f_gen, "quantidade": f_qtd,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success(f"Livro '{f_titulo}' cadastrado com sucesso!")

# =================================================================
# 6. MÓDULO: GESTÃO DO ACERVO (PROF/DIR)
# =================================================================
def modulo_gestao():
    st.header("📊 Painel de Gestão")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        # Define quais abas aparecem para cada nível
        tabs_labels = ["📋 Lista e Edição"]
        if st.session_state.perfil_logado == "Diretor":
            tabs_labels += ["🪄 Curadoria IA", "📥 Importar Planilha"]
        
        guias = st.tabs(tabs_labels)
        
        # --- ABA: LISTA E EDIÇÃO ---
        with guias[0]:
            termo = st.text_input("🔍 Pesquisar por Título ou Autor:")
            df_filt = df[df['titulo'].str.contains(termo, case=False) | df['autor'].str.contains(termo, case=False)] if termo else df
            st.dataframe(df_filt[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Editar Registro"):
                opcoes = df_filt.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                sel = st.selectbox("Escolha o livro para corrigir:", ["..."] + opcoes)
                if sel != "...":
                    id_s = int(sel.split("| ID:")[1])
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_f"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn'])
                        ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=150)
                        nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("💾 Salvar Alterações"):
                            supabase.table("livros_acervo").update({
                                "titulo": nt, "autor": na, "isbn": ni, 
                                "genero": ng, "sinopse": ns, "quantidade": nq
                            }).eq("id", id_s).execute()
                            st.success("Dados atualizados!"); st.rerun()

            if st.button("📥 Gerar Excel do Acervo"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as wr:
                    for g in df['genero'].unique():
                        df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=str(g)[:30])
                st.download_button("Baixar Excel", output.getvalue(), "Acervo.xlsx")

        # --- ABAS EXCLUSIVAS DO DIRETOR ---
        if st.session_state.perfil_logado == "Diretor":
            with guias[1]:
                st.subheader("Curadoria em Cascata (Google + Gemini)")
                api_k = st.text_input("Gemini API Key:", type="password")
                if api_k:
                    res_p = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
                    df_p = pd.DataFrame(res_p.data)
                    if not df_p.empty:
                        st.warning(f"{len(df_p)} registros incompletos.")
                        if st.button("✨ Iniciar IA"):
                            prog, stxt = st.progress(0), st.empty()
                            api_g = st.secrets["google"]["books_api_key"]
                            for i, row in df_p.iterrows():
                                stxt.text(f"Limpando: {row['titulo']}...")
                                f_a, f_s, f_g = row['autor'], row['sinopse'], row['genero']
                                try:
                                    url_g = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_g}"
                                    rg = requests.get(url_g, headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                                    if "items" in rg:
                                        info = rg["items"][0]["volumeInfo"]
                                        if f_a == "Pendente": f_a = ", ".join(info.get("authors", ["Pendente"]))
                                        if f_s == "Pendente": f_s = info.get("description", "Pendente")
                                except: pass
                                if f_a == "Pendente" or f_s == "Pendente" or len(f_s) < 30:
                                    prompt = f"Livro: {row['titulo']}. Responda apenas: Autor; Sinopse Curta; Gênero. Use ';' como separador."
                                    url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_k}"
                                    try:
                                        resp = requests.post(url_gem, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
                                        if resp.status_code == 200:
                                            partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                            if len(partes) >= 3:
                                                f_a = partes[0].strip() if f_a == "Pendente" else f_a
                                                f_s, f_g = partes[1].strip(), partes[2].strip().capitalize()
                                    except: pass
                                supabase.table("livros_acervo").update({"autor": f_a, "sinopse": f_s, "genero": f_g}).eq("id", row['id']).execute()
                                prog.progress((i + 1) / len(df_p))
                            st.success("Concluído!"); st.rerun()
            
            with guias[2]:
                f_dir = st.file_uploader("Upload Planilha Diretor", type=['xlsx'])
                if f_dir:
                    try:
                        df_up = pd.read_excel(f_dir, sheet_name='livros escaneados')
                        if st.button("🚀 Importar Novos"):
                            dados_n = []
                            for _, r in df_up.iterrows():
                                dados_n.append({
                                    "isbn": str(r.get('ISBN','')), "titulo": str(r.get('Título','')), 
                                    "autor": str(r.get('Autor(es)','Pendente')), "sinopse": str(r.get('Sinopse','Pendente')), 
                                    "genero": str(r.get('Categorias','Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')
                                })
                            supabase.table("livros_acervo").insert(dados_n).execute()
                            st.success("Importado!"); st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")

# =================================================================
# 7. MÓDULO: EMPRÉSTIMOS (PROF/DIR)
# =================================================================
def modulo_emprestimos():
    st.header("📑 Controle de Empréstimos")
    t1, t2, t3 = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])
    
    with t3:
        st.subheader("Cadastro de Usuários")
        res_u = supabase.table("usuarios").select("nome, turma").execute()
        df_u = pd.DataFrame(res_u.data)
        edit_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_u_lote")
        if st.button("💾 Salvar Alterações de Pessoas"):
            supabase.table("usuarios").delete().neq("id", 0).execute()
            novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in edit_u.iterrows() if str(r['nome']) != "None"]
            if novos: supabase.table("usuarios").insert(novos).execute()
            st.success("Salvo!"); st.rerun()

    with t1:
        res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        res_us = supabase.table("usuarios").select("id, nome, turma").execute()
        if res_l.data and res_us.data:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_us.data}
            l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
            u_id = st.selectbox("Aluno:", options=list(u_map.keys()), format_func=lambda x: u_map[x])
            l_id = st.selectbox("Livro:", options=list(l_map.keys()), format_func=lambda x: l_map[x])
            if st.button("🚀 Confirmar Empréstimo"):
                supabase.table("emprestimos").insert({
                    "id_livro": l_id, "id_usuario": u_id, 
                    "data_saida": datetime.now().strftime('%d/%m/%Y'), "status": "Ativo"
                }).execute()
                q_atual = next(i['quantidade'] for i in res_l.data if i['id'] == l_id)
                supabase.table("livros_acervo").update({"quantidade": q_atual - 1}).eq("id", l_id).execute()
                st.success("Emprestado!"); time.sleep(1); st.rerun()

    with t2:
        # Busca empréstimos ativos cruzando com livros e usuários no Python
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        if res_e.data:
            df_e = pd.DataFrame(res_e.data)
            df_l = pd.DataFrame(supabase.table("livros_acervo").select("id, titulo").execute().data)
            df_u = pd.DataFrame(supabase.table("usuarios").select("id, nome").execute().data)
            
            df_m = df_e.merge(df_l, left_on='id_livro', right_on='id').merge(df_u, left_on='id_usuario', right_on='id')
            df_m["Selecionar"] = False
            edit_dev = st.data_editor(df_m[["Selecionar", "titulo", "nome"]], hide_index=True, use_container_width=True, key="edit_dev_lote")
            
            if st.button("Confirmar Retorno dos Selecionados"):
                for i in edit_dev[edit_dev["Selecionar"]].index:
                    linha = df_m.loc[i]
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", linha['id_x']).execute()
                    res_q = supabase.table("livros_acervo").select("quantidade").eq("id", linha['id_livro']).execute()
                    supabase.table("livros_acervo").update({"quantidade": res_q.data[0]['quantidade'] + 1}).eq("id", linha['id_livro']).execute()
                st.success("Devolvido com sucesso!"); st.rerun()
        else: st.info("Sem pendências.")

# =================================================================
# 8. MAESTRO (CONTROLE DE EXIBIÇÃO)
# =================================================================
login_sistema()

menu_opcoes = ["🏠 Início", "🚚 Registro de Livros"]
if st.session_state.perfil_logado in ["Professor", "Diretor"]:
    menu_opcoes += ["📊 Gestão do Acervo", "📑 Empréstimos"]

escolha = st.sidebar.radio("Navegação", menu_opcoes)

if escolha == "🏠 Início":
    st.title("🏠 Portal Mara Cristina")
    st.write(f"Bem-vindo, **{st.session_state.perfil_logado}**!")
    st.info("Utilize o menu lateral para navegar entre as funções.")

elif escolha == "🚚 Registro de Livros":
    modulo_entrada_livros()

elif escolha == "📊 Gestão do Acervo":
    modulo_gestao()

elif escolha == "📑 Empréstimos":
    modulo_emprestimos()