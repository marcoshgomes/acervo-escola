import streamlit as st
import pandas as pd
import requests
import time
import json
from io import BytesIO
from datetime import datetime, timedelta
from supabase import create_client, Client

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR
# =================================================================
st.set_page_config(page_title="Acervo Inteligente Mara Cristina", layout="centered", page_icon="📚")

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
        st.error(f"⚠️ Erro de conexão na nuvem: {e}")
        return None

supabase = conectar_supabase()

# =================================================================
# 3. DICIONÁRIO E FUNÇÕES DE APOIO
# =================================================================
GENEROS_BASE = ["Ficção", "Infantil", "Juvenil", "Didático", "Poesia", "História", "Ciências", "Artes", "Gibis/HQ", "Religião", "Filosofia"]
TRADUCAO_GENEROS = {"Fiction": "Ficção", "Education": "Didático", "History": "História", "General": "Geral"}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS.get(genero_ingles, genero_ingles)

def get_generos_dinamicos():
    try:
        res = supabase.table("livros_acervo").select("genero").execute()
        generos_na_nuvem = [d['genero'] for d in res.data] if res.data else []
        lista_final = list(set(GENEROS_BASE + generos_na_nuvem))
        lista_final = [g for g in lista_final if g]; lista_final.sort(); lista_final.append("➕ CADASTRAR NOVO GÊNERO")
        return lista_final
    except: return GENEROS_BASE + ["➕ CADASTRAR NOVO GÊNERO"]

# =================================================================
# 4. SEGURANÇA E CONTROLE DE PERFIS
# =================================================================
if "perfil" not in st.session_state: st.session_state.perfil = "Aluno"
if "reset_count" not in st.session_state: st.session_state.reset_count = 0
if "mostrar_login" not in st.session_state: st.session_state.mostrar_login = False

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def verificar_senha():
    senha = st.session_state.pwd_input.strip()
    if senha == SENHA_DIRETOR:
        st.session_state.perfil = "Diretor"
        st.session_state.mostrar_login = False
    elif senha == SENHA_PROFESSOR:
        st.session_state.perfil = "Professor"
        st.session_state.mostrar_login = False
    else:
        st.sidebar.error("Senha inválida")

st.sidebar.title("📚 Acervo Digital")
st.sidebar.write(f"Perfil Atual: **{st.session_state.perfil}**")

if st.session_state.perfil == "Aluno":
    if st.sidebar.button("👤 Acesso Gestor do Sistema"):
        st.session_state.mostrar_login = not st.session_state.mostrar_login
    if st.session_state.mostrar_login:
        st.sidebar.text_input("Digite sua senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    if st.sidebar.button("🚪 Sair (Logoff)"):
        st.session_state.perfil = "Aluno"; st.rerun()

# --- DEFINIÇÃO DO MENU POR PERFIL ---
opcoes_menu = ["Consulta do Acervo", "Entrada de Livros"] # Ambos podem cadastrar
if st.session_state.perfil in ["Professor", "Diretor"]:
    opcoes_menu.extend(["Circulação (Empréstimos)", "Gestão do Acervo"])
if st.session_state.perfil == "Diretor":
    opcoes_menu.append("Curadoria Inteligente (IA)")

menu = st.sidebar.selectbox("Navegação:", opcoes_menu)

# =================================================================
# 5. ABA: CONSULTA DO ACERVO
# =================================================================
if menu == "Consulta do Acervo":
    st.header("🔍 Pesquisa de Títulos")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        termo = st.text_input("Busque por Título, Autor ou Gênero:")
        if termo:
            mask = (df['titulo'].str.contains(termo, case=False, na=False) | 
                    df['autor'].str.contains(termo, case=False, na=False) |
                    df['genero'].str.contains(termo, case=False, na=False))
            df_res = df[mask]
        else:
            df_res = df.tail(10)
        st.dataframe(df_res[['titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
    else:
        st.info("O acervo está vazio no momento.")

# =================================================================
# 6. ABA: ENTRADA DE LIVROS (ACESSÍVEL A TODOS)
# =================================================================
elif menu == "Entrada de Livros":
    st.header("🚚 Registro de Novos Volumes")
    tab_isbn, tab_manual = st.tabs(["🔍 Por Código ISBN", "✍️ Cadastro Manual"])

    with tab_isbn:
        st.info("Insira o ISBN para busca automática e entrada rápida.")
        isbn_input = st.text_input("Digite o ISBN:", placeholder="Ex: 9788532511010", key=f"isb_in_{st.session_state.reset_count}")
        if isbn_input:
            isbn_limpo = str(isbn_input).strip()
            res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
            
            if res_check.data:
                item = res_check.data[0]
                st.success(f"📖 Livro Localizado: **{item['titulo']}**")
                with st.form("form_inc"):
                    qtd_add = st.number_input("Adicionar quantos exemplares?", min_value=1, value=1)
                    if st.form_submit_button("Atualizar Estoque"):
                        supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + qtd_add}).eq("isbn", isbn_limpo).execute()
                        st.success("Estoque atualizado com sucesso!"); time.sleep(1.5); st.session_state.reset_count += 1; st.rerun()
            else:
                with st.spinner("Buscando dados bibliográficos..."):
                    try:
                        api_key_google = st.secrets["google"]["books_api_key"]
                        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key_google}"
                        res = requests.get(url).json()
                        info = res["items"][0]["volumeInfo"]
                        dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                    except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                    
                    with st.form("form_isbn_new"):
                        st.write("### ✨ Novo Título Detectado")
                        t_f = st.text_input("Título", dados['titulo'])
                        a_f = st.text_input("Autor", dados['autor'])
                        g_sel = st.selectbox("Gênero", options=get_generos_dinamicos())
                        g_novo = st.text_input("Novo Gênero?")
                        s_f = st.text_area("Sinopse", dados['sinopse'], height=100)
                        q_f = st.number_input("Quantidade inicial", min_value=1, value=1)
                        if st.form_submit_button("🚀 Cadastrar no Sistema"):
                            gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                            supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                            st.success("Cadastrado com sucesso!"); time.sleep(1.5); st.session_state.reset_count += 1; st.rerun()

    with tab_manual:
        st.write("### ✍️ Cadastro Manual Completo")
        with st.form("form_manual_puro"):
            m_t = st.text_input("Título do Livro *")
            m_a = st.text_input("Autor *", value="Pendente")
            m_i = st.text_input("ISBN (Opcional)")
            m_g_sel = st.selectbox("Gênero", options=get_generos_dinamicos(), key="g_man")
            m_g_novo = st.text_input("Novo Gênero?", key="gn_man")
            m_s = st.text_area("Sinopse", value="Pendente")
            m_q = st.number_input("Quantidade", min_value=1, value=1)
            if st.form_submit_button("💾 Salvar Registro Manual"):
                if m_t:
                    gen_f = m_g_novo.strip().capitalize() if m_g_sel == "➕ CADASTRAR NOVO GÊNERO" else m_g_sel
                    supabase.table("livros_acervo").insert({
                        "isbn": m_i if m_i else f"M-{int(time.time())}", "titulo": m_t, "autor": m_a,
                        "sinopse": m_s, "genero": gen_f, "quantidade": m_q,
                        "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                    }).execute()
                    st.success("Salvo com sucesso!"); time.sleep(1.5); st.session_state.reset_count += 1; st.rerun()
                else: st.error("O título é obrigatório.")

# =================================================================
# 7. ABA: CIRCULAÇÃO (EMPRÉSTIMOS E PESSOAS)
# =================================================================
elif menu == "Circulação (Empréstimos)":
    st.header("📑 Circulação de Livros")
    aba_emp, aba_dev, aba_pes = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])

    with aba_pes:
        st.subheader("👤 Cadastro de Usuários")
        res_u = supabase.table("usuarios").select("*").execute()
        df_u = pd.DataFrame(res_u.data)
        users_edit = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True, key="ed_pess")
        if st.button("💾 Salvar Alterações de Usuários"):
            supabase.table("usuarios").delete().neq("id", 0).execute()
            novos = [{"nome": r['nome'], "turma": r['turma']} for _, r in users_edit.iterrows() if r['nome']]
            if novos: supabase.table("usuarios").insert(novos).execute()
            st.success("Usuários atualizados!"); time.sleep(1); st.rerun()

    with aba_emp:
        st.subheader("Novo Empréstimo")
        res_l = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        res_u = supabase.table("usuarios").select("id, nome, turma").execute()
        if res_u.data and res_l.data:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in res_u.data}
            l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in res_l.data}
            u_id = st.selectbox("Quem está pegando?", options=list(u_map.keys()), format_func=lambda x: u_map[x])
            l_id = st.selectbox("Qual o livro?", options=list(l_map.keys()), format_func=lambda x: l_map[x])
            prazo = st.select_slider("Prazo (dias):", [7, 15, 30], 15)
            if st.button("🚀 Confirmar Empréstimo"):
                dt_hoje = datetime.now().strftime('%d/%m/%Y')
                dt_ret = (datetime.now() + timedelta(days=prazo)).strftime('%d/%m/%Y')
                supabase.table("emprestimos").insert({"id_livro": l_id, "id_usuario": u_id, "data_saida": dt_hoje, "data_retorno_prevista": dt_ret, "status": "Ativo"}).execute()
                qtd_atual = next(item['quantidade'] for item in res_l.data if item['id'] == l_id)
                supabase.table("livros_acervo").update({"quantidade": qtd_atual - 1}).eq("id", l_id).execute()
                st.success("Empréstimo registrado!"); time.sleep(1); st.rerun()
        else: st.info("Certifique-se de que há pessoas cadastradas e livros com estoque disponível.")

    with aba_dev:
        st.subheader("📥 Registro de Devolução")
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        res_livros = supabase.table("livros_acervo").select("id, titulo").execute()
        res_users = supabase.table("usuarios").select("id, nome").execute()
        if res_e.data:
            df_e, df_l, df_u = pd.DataFrame(res_e.data), pd.DataFrame(res_livros.data), pd.DataFrame(res_users.data)
            df_m = df_e.merge(df_l, left_on='id_livro', right_on='id').merge(df_u, left_on='id_usuario', right_on='id')
            df_m["Selecionar"] = False
            df_show = df_m[["Selecionar", "titulo", "nome", "data_retorno_prevista"]]
            df_show.columns = ["Selecionar", "Livro", "Pessoa", "Data Prevista"]
            edit_dev = st.data_editor(df_show, hide_index=True, use_container_width=True)
            sel = edit_dev[edit_dev["Selecionar"] == True]
            if not sel.empty and st.button(f"Confirmar Devolução de {len(sel)} item(ns)"):
                for i in sel.index:
                    linha = df_m.loc[i]
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", linha['id_x']).execute()
                    res_q = supabase.table("livros_acervo").select("quantidade").eq("id", linha['id_livro']).execute()
                    supabase.table("livros_acervo").update({"quantidade": res_q.data[0]['quantidade'] + 1}).eq("id", linha['id_livro']).execute()
                st.success("Estoque e status atualizados!"); time.sleep(1); st.rerun()
        else: st.info("Não existem empréstimos pendentes.")

# =================================================================
# 8. ABA: GESTÃO (PESQUISA, EDIÇÃO E EXCLUSÃO)
# =================================================================
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Controle")
    tab_list, tab_import = st.tabs(["📋 Lista e Busca", "📥 Importação Planilha"])
    
    with tab_list:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("Busca por Título, Autor ou ISBN:", key="busca_gestao")
            if termo:
                mask = (df['titulo'].str.contains(termo, case=False, na=False) | 
                        df['autor'].str.contains(termo, case=False, na=False) | 
                        df['isbn'].str.contains(termo, case=False, na=False))
                df_display = df[mask]
            else: df_display = df.tail(15)
            
            st.dataframe(df_display[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Editar ou Excluir Registro Selecionado"):
                opcoes = df_display.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Selecione o livro:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_sel = int(livro_sel.split("| ID:")[1])
                    item = df[df['id'] == id_sel].iloc[0]
                    with st.form("ed_completa"):
                        nt = st.text_input("Título", item['titulo']); na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn']); ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=80); nq = st.number_input("Estoque", value=int(item['quantidade']))
                        st.warning("⚠️ Para excluir, marque abaixo:")
                        conf_exc = st.checkbox("Confirmo que desejo apagar este livro.")
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("💾 Salvar Alterações", use_container_width=True):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_sel).execute()
                            st.success("Alterado!"); time.sleep(1); st.rerun()
                        if c2.form_submit_button("🗑️ Excluir Livro", use_container_width=True):
                            if conf_exc:
                                supabase.table("livros_acervo").delete().eq("id", id_sel).execute()
                                st.success("Excluído!"); time.sleep(1); st.rerun()
                            else: st.error("Marque a confirmação para excluir.")

    with tab_import:
        if st.session_state.perfil == "Diretor":
            st.subheader("Importação em Massa")
            f = st.file_uploader("Upload da Planilha Diretor (xlsx)", type=['xlsx'])
            if f:
                try:
                    df_up = pd.read_excel(f, sheet_name='livros escaneados')
                    res_db = supabase.table("livros_acervo").select("isbn, titulo").execute()
                    df_banco = pd.DataFrame(res_db.data)
                    novos, conflitos = [], []
                    for _, row in df_up.iterrows():
                        isbn_up = str(row.get('ISBN', '')).strip().replace(".0", "")
                        titulo_up = str(row.get('Título', '')).strip()
                        match = (isbn_up != "" and isbn_up in df_banco['isbn'].values) or (titulo_up.lower() in df_banco['titulo'].str.lower().values)
                        dados = {"isbn": isbn_up if isbn_up != "nan" else "", "titulo": titulo_up, "autor": str(row.get('Autor(es)', 'Pendente')), "sinopse": str(row.get('Sinopse', 'Pendente')), "genero": str(row.get('Categorias', 'Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')}
                        if match: conflitos.append(dados)
                        else: novos.append(dados)
                    if novos:
                        st.success(f"{len(novos)} novos livros.")
                        if st.button("🚀 Confirmar Importação"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                    if conflitos: st.warning(f"{len(conflitos)} livros já cadastrados.")
                except Exception as e: st.error(f"Erro na planilha: {e}")
        else: st.warning("Acesso restrito ao Diretor.")

# =================================================================
# 9. ABA: CURADORIA INTELIGENTE (IA COMPLETA)
# =================================================================
elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Inteligência Artificial")
    st.write("Preenchimento automático de livros com dados 'Pendente'.")
    api_k = st.text_input("Gemini API Key:", type="password")
    if api_k:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_p = pd.DataFrame(res.data)
        if not df_p.empty:
            st.warning(f"Existem {len(df_p)} registros pendentes.")
            if st.button("✨ Iniciar Correção via IA"):
                prog, stxt = st.progress(0), st.empty()
                api_g = st.secrets["google"]["books_api_key"]
                for i, row in df_p.iterrows():
                    stxt.text(f"Corrigindo: {row['titulo']}")
                    f_a, f_s, f_g = row['autor'], row['sinopse'], row['genero']
                    try:
                        rg = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_g}", timeout=5).json()
                        if "items" in rg:
                            info = rg["items"][0]["volumeInfo"]
                            if f_a == "Pendente": f_a = ", ".join(info.get("authors", ["Pendente"]))
                            if f_s == "Pendente": f_s = info.get("description", "Pendente")
                    except: pass
                    if f_a == "Pendente" or f_s == "Pendente":
                        try:
                            prompt = f"Livro: {row['titulo']}. Autor; Sinopse Curta; Gênero. Separe por ';'."
                            resp = requests.post(f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_k}", headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
                            p = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                            if len(p) >= 3:
                                if f_a == "Pendente": f_a = p[0].strip()
                                f_s, f_g = p[1].strip(), p[2].strip().capitalize()
                        except: pass
                    supabase.table("livros_acervo").update({"autor": f_a, "sinopse": f_s, "genero": f_g}).eq("id", row['id']).execute()
                    prog.progress((i + 1) / len(df_p))
                st.success("Curadoria concluída!"); st.rerun()
        else: st.success("Banco de dados completo!")