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
# 3. FUNÇÕES DE APOIO
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
        st.session_state.perfil = "Diretor"; st.session_state.mostrar_login = False
    elif senha == SENHA_PROFESSOR:
        st.session_state.perfil = "Professor"; st.session_state.mostrar_login = False
    else: st.sidebar.error("Senha inválida")

st.sidebar.title("📚 Acervo Digital")
st.sidebar.write(f"Perfil Atual: **{st.session_state.perfil}**")

if st.session_state.perfil == "Aluno":
    if st.sidebar.button("👤 Acesso Gestor"):
        st.session_state.mostrar_login = not st.session_state.mostrar_login
    if st.session_state.mostrar_login:
        st.sidebar.text_input("Senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    if st.sidebar.button("🚪 Sair (Logoff)"):
        st.session_state.perfil = "Aluno"; st.rerun()

# Definição de Menu: Alunos e Gestores podem cadastrar livros
opcoes_menu = ["Consulta do Acervo", "Entrada de Livros"]
if st.session_state.perfil in ["Professor", "Diretor"]:
    opcoes_menu.extend(["Circulação (Empréstimos)", "Gestão do Acervo"])
if st.session_state.perfil == "Diretor":
    opcoes_menu.append("Curadoria Inteligente (IA)")

menu = st.sidebar.selectbox("Navegação:", opcoes_menu)

# =================================================================
# 5. ABA: CONSULTA
# =================================================================
if menu == "Consulta do Acervo":
    st.header("🔍 Pesquisa de Títulos")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        termo = st.text_input("Busque por Título, Autor ou Gênero:")
        if termo:
            df_res = df[df['titulo'].str.contains(termo, case=False, na=False) | 
                        df['autor'].str.contains(termo, case=False, na=False) |
                        df['genero'].str.contains(termo, case=False, na=False)]
        else:
            df_res = df.tail(15)
        st.dataframe(df_res[['titulo', 'autor', 'genero', 'quantidade']], use_container_width=True)
    else: st.info("O acervo está vazio.")

# =================================================================
# 6. ABA: ENTRADA DE LIVROS (REMOVIDO CÂMERA)
# =================================================================
elif menu == "Entrada de Livros":
    st.header("🚚 Registro de Novos Volumes")
    t_isbn, t_man = st.tabs(["🔍 Por ISBN (Rápido)", "✍️ Cadastro Manual"])
    
    with t_isbn:
        isbn_in = st.text_input("Digite o ISBN:", key=f"isb_{st.session_state.reset_count}")
        if isbn_in:
            isbn_limpo = isbn_in.strip()
            res_c = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
            if res_c.data:
                item = res_c.data[0]
                st.success(f"📖 Livro Localizado: {item['titulo']}")
                with st.form("f_inc"):
                    q = st.number_input("Volumes novos:", min_value=1, value=1)
                    if st.form_submit_button("Atualizar Estoque"):
                        supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + q}).eq("isbn", isbn_limpo).execute()
                        st.success("Estoque atualizado!"); time.sleep(1); st.session_state.reset_count += 1; st.rerun()
            else:
                with st.spinner("Buscando na Web..."):
                    try:
                        api_k = st.secrets["google"]["books_api_key"]
                        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_k}").json()
                        info = res["items"][0]["volumeInfo"]
                        dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                    except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                    with st.form("f_new_isbn"):
                        tf = st.text_input("Título", dados['titulo'])
                        af = st.text_input("Autor", dados['autor'])
                        gs = st.selectbox("Gênero", get_generos_dinamicos(), key="gs_isbn")
                        gn = st.text_input("Novo Gênero?", key="gn_isbn")
                        sf = st.text_area("Sinopse", dados['sinopse'])
                        qf = st.number_input("Quantidade inicial", min_value=1, value=1)
                        if st.form_submit_button("🚀 Cadastrar Livro"):
                            gf = gn.strip().capitalize() if gs == "➕ CADASTRAR NOVO GÊNERO" else gs
                            supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": tf, "autor": af, "sinopse": sf, "genero": gf, "quantidade": qf, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                            st.success("Cadastrado!"); time.sleep(1); st.session_state.reset_count += 1; st.rerun()

    with t_man:
        with st.form("f_man"):
            mt = st.text_input("Título do Livro *")
            ma = st.text_input("Autor *", "Pendente")
            mi = st.text_input("ISBN (Opcional)")
            mg = st.selectbox("Gênero", get_generos_dinamicos(), key="gm")
            mgn = st.text_input("Novo Gênero?", key="gnm")
            ms = st.text_area("Sinopse", "Pendente")
            mq = st.number_input("Quantidade", min_value=1, value=1)
            if st.form_submit_button("💾 Salvar Registro Manual"):
                if mt:
                    gf = mgn.strip().capitalize() if mg == "➕ CADASTRAR NOVO GÊNERO" else mg
                    supabase.table("livros_acervo").insert({"isbn": mi if mi else f"M-{int(time.time())}", "titulo": mt, "autor": ma, "sinopse": ms, "genero": gf, "quantidade": mq, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                    st.success("Salvo com sucesso!"); time.sleep(1); st.session_state.reset_count += 1; st.rerun()
                else: st.error("Título é obrigatório.")

# =================================================================
# 7. ABA: CIRCULAÇÃO (CONECTADA ÀS SUAS NOVAS TABELAS)
# =================================================================
elif menu == "Circulação (Empréstimos)":
    st.header("📑 Circulação de Livros")
    aba_emp, aba_dev, aba_pes = st.tabs(["📤 Emprestar", "📥 Devolver", "👤 Pessoas"])

    with aba_pes:
        st.subheader("👤 Gestão de Usuários")
        with st.form("cad_u", clear_on_submit=True):
            nu = st.text_input("Nome Completo *")
            tu = st.text_input("Turma (Ex: 6ºA, Professor, Funcionário)")
            if st.form_submit_button("🚀 Cadastrar Usuário"):
                if nu:
                    supabase.table("usuarios").insert({"nome": nu, "turma": tu}).execute()
                    st.success(f"{nu} cadastrado!"); time.sleep(1.5); st.rerun()
        
        st.divider()
        res_u = supabase.table("usuarios").select("*").execute()
        if res_u.data:
            df_u = pd.DataFrame(res_u.data)
            st.write("### Lista de Usuários")
            ed_u = st.data_editor(df_u, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("💾 Sincronizar Lista de Usuários"):
                supabase.table("usuarios").delete().neq("id", 0).execute()
                novos_u = [{"nome": r['nome'], "turma": r['turma']} for _, r in ed_u.iterrows() if r['nome']]
                if novos_u: supabase.table("usuarios").insert(novos_u).execute()
                st.success("Lista sincronizada!"); time.sleep(1); st.rerun()

    with aba_emp:
        st.subheader("Novo Empréstimo")
        # Só livros com estoque > 0
        l_res = supabase.table("livros_acervo").select("id, titulo, quantidade").gt("quantidade", 0).execute()
        u_res = supabase.table("usuarios").select("id, nome, turma").execute()
        if l_res.data and u_res.data:
            u_map = {d['id']: f"{d['nome']} ({d['turma']})" for d in u_res.data}
            l_map = {d['id']: f"{d['titulo']} (Disp: {d['quantidade']})" for d in l_res.data}
            sel_u = st.selectbox("Quem está pegando?", options=list(u_map.keys()), format_func=lambda x: u_map[x])
            sel_l = st.selectbox("Qual o livro?", options=list(l_map.keys()), format_func=lambda x: l_map[x])
            dias = st.select_slider("Prazo de devolução (dias):", [7, 15, 30], 15)
            if st.button("🚀 Confirmar Saída"):
                dt_s = datetime.now().strftime('%d/%m/%Y')
                dt_p = (datetime.now() + timedelta(days=dias)).strftime('%d/%m/%Y')
                # Registra empréstimo
                supabase.table("emprestimos").insert({"id_livro": sel_l, "id_usuario": sel_u, "data_saida": dt_s, "data_retorno_prevista": dt_p, "status": "Ativo"}).execute()
                # Baixa estoque
                q_atual = next(i['quantidade'] for i in l_res.data if i['id'] == sel_l)
                supabase.table("livros_acervo").update({"quantidade": q_atual - 1}).eq("id", sel_l).execute()
                st.success("Empréstimo realizado!"); time.sleep(1.5); st.rerun()
        else: st.info("Cadastre pessoas e livros com estoque disponível.")

    with aba_dev:
        st.subheader("📥 Registro de Devolução")
        res_e = supabase.table("emprestimos").select("*").eq("status", "Ativo").execute()
        if res_e.data:
            df_e = pd.DataFrame(res_e.data)
            # Buscamos nomes para exibir
            l_res = supabase.table("livros_acervo").select("id, titulo").execute()
            u_res = supabase.table("usuarios").select("id, nome").execute()
            df_l, df_u = pd.DataFrame(l_res.data), pd.DataFrame(u_res.data)
            
            # Merge para visualização
            df_m = df_e.merge(df_l, left_on='id_livro', right_on='id', suffixes=('', '_liv'))
            df_m = df_m.merge(df_u, left_on='id_usuario', right_on='id', suffixes=('', '_usr'))
            df_m["Selecionar"] = False
            
            st.write("Selecione os livros que estão sendo devolvidos:")
            grid = st.data_editor(df_m[["Selecionar", "titulo", "nome", "data_retorno_prevista"]], hide_index=True, use_container_width=True)
            
            sel = grid[grid["Selecionar"] == True]
            if not sel.empty and st.button(f"Confirmar Devolução de {len(sel)} item(ns)"):
                for idx in sel.index:
                    loan = df_m.loc[idx]
                    # Finaliza empréstimo (usando o ID da tabela emprestimos que é loan['id'])
                    supabase.table("emprestimos").update({"status": "Devolvido"}).eq("id", loan['id']).execute()
                    # Devolve estoque
                    q_res = supabase.table("livros_acervo").select("quantidade").eq("id", loan['id_livro']).execute()
                    supabase.table("livros_acervo").update({"quantidade": q_res.data[0]['quantidade'] + 1}).eq("id", loan['id_livro']).execute()
                st.success("Devolução concluída!"); time.sleep(1.5); st.rerun()
        else: st.info("Nenhum empréstimo ativo no momento.")

# =================================================================
# 8. ABA: GESTÃO (PESQUISA, EDIÇÃO E EXCLUSÃO)
# =================================================================
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Controle")
    res = supabase.table("livros_acervo").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        termo = st.text_input("Busca Geral (Título, Autor ou ISBN):", key="bg_gestao")
        if termo:
            df_d = df[df['titulo'].str.contains(termo, False, False) | 
                      df['autor'].str.contains(termo, False, False) | 
                      df['isbn'].str.contains(termo, False, False)]
        else: df_d = df.tail(15)
        
        st.dataframe(df_d[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
        
        with st.expander("📝 Editar ou Excluir Registro Selecionado"):
            op = df_d.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
            sel = st.selectbox("Escolha o livro:", ["..."] + op)
            if sel != "...":
                idx = int(sel.split("| ID:")[1])
                item = df[df['id'] == idx].iloc[0]
                with st.form("ed_final"):
                    c1, c2 = st.columns(2)
                    nt = c1.text_input("Título", item['titulo'])
                    na = c2.text_input("Autor", item['autor'])
                    ni = c1.text_input("ISBN", item['isbn'])
                    ng = c2.text_input("Gênero", item['genero'])
                    ns = st.text_area("Sinopse", item['sinopse'], height=100)
                    nq = st.number_input("Estoque Total", value=int(item['quantidade']))
                    st.divider()
                    exc = st.checkbox("⚠️ Confirmo que desejo EXCLUIR este livro permanentemente.")
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("💾 Salvar Alterações", use_container_width=True):
                        supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", idx).execute()
                        st.success("Atualizado!"); time.sleep(1); st.rerun()
                    if b2.form_submit_button("🗑️ Excluir Registro", use_container_width=True):
                        if exc:
                            supabase.table("livros_acervo").delete().eq("id", idx).execute()
                            st.success("Excluído!"); time.sleep(1); st.rerun()
                        else: st.error("Marque a confirmação para excluir.")

# =================================================================
# 9. ABA: CURADORIA INTELIGENTE (IA - MANTIDA)
# =================================================================
elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Inteligência Artificial")
    api_k = st.text_input("Insira sua Gemini API Key:", type="password")
    if api_k:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_p = pd.DataFrame(res.data)
        if not df_p.empty:
            st.warning(f"Existem {len(df_p)} registros com dados pendentes.")
            if st.button("✨ Iniciar Correção via IA"):
                prog, stxt = st.progress(0), st.empty()
                api_g = st.secrets["google"]["books_api_key"]
                for i, row in df_p.iterrows():
                    stxt.text(f"Corrigindo: {row['titulo']}...")
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
                            prompt = f"Livro: {row['titulo']}. Forneça: Autor; Sinopse Curta; Gênero. Separe por ';' e nada mais."
                            resp = requests.post(f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_k}", headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                            p = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                            if len(p) >= 3:
                                if f_a == "Pendente": f_a = p[0].strip()
                                f_s, f_g = p[1].strip(), p[2].strip().capitalize()
                        except: pass
                    supabase.table("livros_acervo").update({"autor": f_a, "sinopse": f_s, "genero": f_g}).eq("id", row['id']).execute()
                    prog.progress((i + 1) / len(df_p))
                st.success("Curadoria concluída!"); st.rerun()
        else: st.success("Banco de dados 100% completo!")