import streamlit as st
import pandas as pd
import requests
import time
import json
from io import BytesIO
from datetime import datetime
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

opcoes_menu = ["Entrada de Livros"]
if st.session_state.perfil in ["Professor", "Diretor"]:
    opcoes_menu.append("Gestão do Acervo")
if st.session_state.perfil == "Diretor":
    opcoes_menu.append("Curadoria Inteligente (IA)")

menu = st.sidebar.selectbox("Navegação:", opcoes_menu)

# =================================================================
# 5. ABA: ENTRADA DE LIVROS
# =================================================================
if menu == "Entrada de Livros":
    st.header("🚚 Registro de Novos Volumes")
    tab_isbn, tab_manual = st.tabs(["🔍 Por Código ISBN", "✍️ Cadastro Manual"])

    with tab_isbn:
        st.info("Insira o ISBN para busca automática.")
        isbn_input = st.text_input("Digite o Código ISBN:", placeholder="Ex: 9788532511010", key=f"isb_in_{st.session_state.reset_count}")
        if isbn_input:
            isbn_limpo = str(isbn_input).strip()
            res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
            if res_check.data:
                item = res_check.data[0]
                st.success(f"📖 Livro: **{item['titulo']}**")
                with st.form("form_inc"):
                    qtd_add = st.number_input("Volumes novos:", min_value=1, value=1)
                    if st.form_submit_button("Atualizar Estoque"):
                        supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + qtd_add}).eq("isbn", isbn_limpo).execute()
                        st.success("Estoque atualizado!"); time.sleep(1.5); st.session_state.reset_count += 1; st.rerun()
            else:
                with st.spinner("Buscando dados..."):
                    try:
                        api_key_google = st.secrets["google"]["books_api_key"]
                        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key_google}"
                        res = requests.get(url).json()
                        dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                        if "items" in res:
                            info = res["items"][0]["volumeInfo"]
                            dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                    except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                    with st.form("form_n"):
                        t_f = st.text_input("Título", dados['titulo'])
                        a_f = st.text_input("Autor", dados['autor'])
                        g_sel = st.selectbox("Gênero", options=get_generos_dinamicos())
                        g_novo = st.text_input("Novo Gênero?")
                        s_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                        q_f = st.number_input("Quantidade inicial", min_value=1, value=1)
                        if st.form_submit_button("🚀 Salvar"):
                            gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                            supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                            st.success("Cadastrado!"); time.sleep(1.5); st.session_state.reset_count += 1; st.rerun()

    with tab_manual:
        with st.form("form_man"):
            m_t = st.text_input("Título do Livro *")
            m_a = st.text_input("Autor *")
            m_i = st.text_input("ISBN (Opcional)")
            m_g_sel = st.selectbox("Gênero", options=get_generos_dinamicos())
            m_g_novo = st.text_input("Novo Gênero?")
            m_s = st.text_area("Sinopse")
            m_q = st.number_input("Quantidade", min_value=1, value=1)
            if st.form_submit_button("💾 Salvar Manual"):
                if m_t:
                    gen_f = m_g_novo.strip().capitalize() if m_g_sel == "➕ CADASTRAR NOVO GÊNERO" else m_g_sel
                    supabase.table("livros_acervo").insert({"isbn": m_i if m_i else f"MANUAL-{int(time.time())}", "titulo": m_t, "autor": m_a if m_a else "Pendente", "sinopse": m_s if m_s else "Pendente", "genero": gen_f, "quantidade": m_q, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                    st.success("Salvo!"); time.sleep(1.5); st.session_state.reset_count += 1; st.rerun()
                else: st.error("Título obrigatório.")

# =================================================================
# 6. ABA: GESTÃO (PESQUISA, EDIÇÃO E EXCLUSÃO)
# =================================================================
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Controle")
    tab_list, tab_import = st.tabs(["📋 Lista e Busca", "📥 Importação Diretor"])
    
    with tab_list:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            st.write("### 🔍 Pesquisar no Acervo")
            termo = st.text_input("Digite o Título, Autor ou ISBN:", placeholder="Ex: Harry Potter...", key="busca_gestao")
            
            if termo:
                mask = (df['titulo'].str.contains(termo, case=False, na=False) | 
                        df['autor'].str.contains(termo, case=False, na=False) | 
                        df['isbn'].str.contains(termo, case=False, na=False))
                df_display = df[mask]
                st.write(f"Foram encontrados {len(df_display)} livros.")
            else:
                st.info("💡 Digite o nome do livro acima para localizar qualquer registro.")
                df_display = df.tail(10)

            st.dataframe(df_display[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            if not df_display.empty:
                with st.expander("📝 Editar ou Excluir Registro Selecionado"):
                    opcoes = df_display.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                    livro_sel = st.selectbox("Selecione o livro para modificar:", ["..."] + opcoes)
                    
                    if livro_sel != "...":
                        id_sel = int(livro_sel.split("| ID:")[1])
                        item = df[df['id'] == id_sel].iloc[0]
                        
                        with st.form("ed_completa_form"):
                            st.write(f"### Editando: {item['titulo']}")
                            nt = st.text_input("Título", item['titulo'])
                            na = st.text_input("Autor", item['autor'])
                            ni = st.text_input("ISBN", item['isbn'])
                            ng = st.text_input("Gênero", item['genero'])
                            ns = st.text_area("Sinopse", item['sinopse'], height=100)
                            nq = st.number_input("Estoque", value=int(item['quantidade']))
                            
                            st.divider()
                            st.warning("⚠️ **Zona de Exclusão:** Para apagar este livro, marque a caixa abaixo antes de clicar em Excluir.")
                            confirmar_exclusao = st.checkbox("Confirmo que desejo EXCLUIR permanentemente este livro do acervo.")
                            
                            # Botões Lado a Lado
                            col_salvar, col_excluir = st.columns(2)
                            
                            if col_salvar.form_submit_button("💾 Salvar Alterações", use_container_width=True):
                                supabase.table("livros_acervo").update({
                                    "titulo": nt, "autor": na, "isbn": ni, 
                                    "genero": ng, "sinopse": ns, "quantidade": nq
                                }).eq("id", id_sel).execute()
                                st.success("✅ Alterações salvas com sucesso!"); time.sleep(1.5); st.rerun()
                            
                            if col_excluir.form_submit_button("🗑️ Excluir Registro", use_container_width=True):
                                if confirmar_exclusao:
                                    supabase.table("livros_acervo").delete().eq("id", id_sel).execute()
                                    st.success("🔥 Registro removido permanentemente!"); time.sleep(1.5); st.rerun()
                                else:
                                    st.error("❌ Erro: Você precisa marcar a caixa de confirmação para excluir.")

            if st.button("📥 Baixar Excel Completo"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as wr:
                    for g in df['genero'].unique():
                        aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                        df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=aba)
                st.download_button("Clique para Baixar", output.getvalue(), "Acervo_Total.xlsx")

    with tab_import:
        if st.session_state.perfil != "Diretor": st.warning("Acesso Restrito ao Diretor.")
        else:
            f_diretor = st.file_uploader("Upload do arquivo Excel", type=['xlsx'])
            if f_diretor:
                try:
                    df_up = pd.read_excel(f_diretor, sheet_name='livros escaneados')
                    res_db = supabase.table("livros_acervo").select("isbn, titulo").execute()
                    df_banco = pd.DataFrame(res_db.data)
                    novos, conflitos = [], []
                    for _, row in df_up.iterrows():
                        isbn_up = str(row.get('ISBN', '')).strip().replace(".0", "")
                        titulo_up = str(row.get('Título', '')).strip()
                        match = False
                        if not df_banco.empty:
                            if (isbn_up != "" and isbn_up in df_banco['isbn'].values) or (titulo_up.lower() in df_banco['titulo'].str.lower().values):
                                match = True
                        dados = {"isbn": isbn_up if isbn_up != "nan" else "", "titulo": titulo_up, "autor": str(row.get('Autor(es)', 'Pendente')), "sinopse": str(row.get('Sinopse', 'Pendente')), "genero": str(row.get('Categorias', 'Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')}
                        if match: conflitos.append(dados)
                        else: novos.append(dados)
                    if novos:
                        st.success(f"{len(novos)} novos títulos detectados.")
                        if st.button("Confirmar Novos"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                    if conflitos:
                        st.warning(f"{len(conflitos)} duplicatas ignoradas.")
                except Exception as e: st.error(f"Erro: {e}")

# =================================================================
# 7. ABA: CURADORIA INTELIGENTE (IA)
# =================================================================
elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Inteligência Artificial")
    api_k = st.text_input("Insira sua Gemini API Key:", type="password")
    if api_k:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_p = pd.DataFrame(res.data)
        if not df_p.empty:
            st.warning(f"{len(df_p)} registros pendentes.")
            if st.button("✨ Iniciar Correção"):
                prog, stxt = st.progress(0), st.empty()
                api_g = st.secrets["google"]["books_api_key"]
                for i, row in df_p.iterrows():
                    stxt.text(f"Processando: {row['titulo']}")
                    f_a, f_s, f_g = row['autor'], row['sinopse'], row['genero']
                    try:
                        url_g = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_g}"
                        rg = requests.get(url_g, timeout=5).json()
                        if "items" in rg:
                            info = rg["items"][0]["volumeInfo"]
                            if f_a == "Pendente": f_a = ", ".join(info.get("authors", ["Pendente"]))
                            if f_s == "Pendente": f_s = info.get("description", "Pendente")
                    except: pass
                    if f_a == "Pendente" or f_s == "Pendente" or len(f_s) < 30:
                        prompt = f"Livro: {row['titulo']}. Autor; Sinopse Curta; Gênero. Separe por ';'."
                        url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_k}"
                        try:
                            resp = requests.post(url_gem, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                            if resp.status_code == 200:
                                p = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                if len(p) >= 3:
                                    if f_a == "Pendente": f_a = p[0].strip()
                                    f_s, f_g = p[1].strip(), p[2].strip().capitalize()
                        except: pass
                    supabase.table("livros_acervo").update({"autor": f_a, "sinopse": f_s, "genero": f_g}).eq("id", row['id']).execute()
                    prog.progress((i + 1) / len(df_p))
                st.success("Concluído!"); st.rerun()
        else: st.success("Banco 100% Completo!")