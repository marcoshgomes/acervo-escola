import streamlit as st
import pandas as pd
import requests
import time
import json
import numpy as np
import cv2
from io import BytesIO
from datetime import datetime
from PIL import Image
from supabase import create_client, Client
import streamlit.components.v1 as components

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
# 4. COMPONENTE SCANNER REAL-TIME (CÂMERA TRASEIRA)
# =================================================================
def real_time_barcode_scanner():
    """Scanner em JS que força a câmera traseira e lê em tempo real"""
    st.subheader("📷 Leitor de Código de Barras")
    st.info("Aponte a câmera traseira para o código de barras do livro.")
    
    scanner_html = """
    <div id="reader" style="width:100%; border-radius:12px; border: 2px solid #d97706; overflow:hidden;"></div>
    <div id="result" style="margin-top:10px; font-weight:bold; color:green; font-size:1.2em; text-align:center;"></div>
    
    <script src="https://unpkg.com/html5-qrcode"></script>
    <script>
        function onScanSuccess(decodedText, decodedResult) {
            document.getElementById('result').innerText = "CÓDIGO CAPTURADO: " + decodedText;
            // Efeito sonoro básico (beep) se possível
            window.parent.postMessage({type: 'barcode_result', value: decodedText}, '*');
        }

        const html5QrCode = new Html5Qrcode("reader");
        const config = { fps: 15, qrbox: {width: 300, height: 150} };

        // Tenta iniciar especificamente com a câmera traseira (environment)
        html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess)
        .catch(err => {
            // Se falhar a traseira (ex: PC), tenta a padrão
            html5QrCode.start({ facingMode: "user" }, config, onScanSuccess);
        });
    </script>
    """
    components.html(scanner_html, height=450)

# =================================================================
# 5. SEGURANÇA E CONTROLE DE PERFIS
# =================================================================
if "perfil" not in st.session_state: st.session_state.perfil = "Aluno"
if "reset_count" not in st.session_state: st.session_state.reset_count = 0
if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
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
    else: st.sidebar.error("Senha inválida")

st.sidebar.title("📚 Acervo Digital")
st.sidebar.write(f"Usuário: **{st.session_state.perfil}**")

if st.session_state.perfil == "Aluno":
    if st.sidebar.button("👤 Acesso Gestor do Sistema"):
        st.session_state.mostrar_login = not st.session_state.mostrar_login
    if st.session_state.mostrar_login:
        st.sidebar.text_input("Digite sua senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    if st.sidebar.button("🚪 Sair (Logoff)"):
        st.session_state.perfil = "Aluno"; st.rerun()

opcoes_menu = ["Entrada de Livros"]
if st.session_state.perfil in ["Professor", "Diretor"]: opcoes_menu.append("Gestão do Acervo")
if st.session_state.perfil == "Diretor": opcoes_menu.append("Curadoria Inteligente (IA)")
menu = st.sidebar.selectbox("Navegação:", opcoes_menu)

# =================================================================
# 6. ABA: ENTRADA DE LIVROS
# =================================================================
if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    # Scanner em Tempo Real (Câmera Traseira)
    real_time_barcode_scanner()

    st.write("---")
    # Campo manual para caso o scanner detecte mas não preencha automaticamente (devido limitações do Streamlit)
    # ou para digitação manual direta.
    isbn_input = st.text_input("Confirme o ISBN lido ou digite aqui:", key=f"field_{st.session_state.reset_count}")

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res_check.data:
            item = res_check.data[0]
            st.info(f"📖 {item['titulo']} (Já cadastrado)")
            with st.form("form_inc"):
                qtd_add = st.number_input("Adicionar exemplares?", 1)
                if st.form_submit_button("Atualizar Estoque"):
                    supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + qtd_add}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!"); time.sleep(1); st.session_state.reset_count += 1; st.rerun()
        else:
            with st.spinner("Buscando dados bibliográficos..."):
                headers = {"User-Agent": "Mozilla/5.0"}
                try:
                    api_key_google = st.secrets["google"]["books_api_key"]
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key_google}"
                    res = requests.get(url, headers=headers).json()
                    dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                    if "items" in res:
                        info = res["items"][0]["volumeInfo"]
                        dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                
                with st.form("form_novo"):
                    st.write("### ✨ Novo Cadastro")
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    g_sel = st.selectbox("Gênero", options=get_generos_dinamicos())
                    g_novo = st.text_input("Se novo gênero, digite aqui:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=100)
                    q_f = st.number_input("Quantidade inicial", 1)
                    if st.form_submit_button("🚀 Salvar no Banco de Dados"):
                        gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                        supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                        st.success("Salvo com sucesso!"); time.sleep(1); st.session_state.reset_count += 1; st.rerun()

# =================================================================
# 7. ABA: GESTÃO DO ACERVO
# =================================================================
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Gestão")
    tab_view, tab_import = st.tabs(["📋 Lista e Edição", "📥 Importar Planilha do Diretor"])

    with tab_view:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("🔍 Localizar Livro:")
            df_disp = df[df['titulo'].str.contains(termo, case=False) | df['isbn'].str.contains(termo)] if termo else df
            st.dataframe(df_disp[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Editar Registro Completo"):
                opcoes = df_disp.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Escolha o livro para editar:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_sel = int(livro_sel.split("| ID:")[1])
                    item = df[df['id'] == id_sel].iloc[0]
                    with st.form("ed_form"):
                        nt = st.text_input("Título", item['titulo'])
                        na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn'])
                        ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=150)
                        nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("💾 Salvar Alterações"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_sel).execute()
                            st.success("Alterado!"); time.sleep(1); st.rerun()

        if st.button("📥 Gerar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as wr:
                for g in df['genero'].unique():
                    aba = str(g)[:30]
                    df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=aba)
            st.download_button("Baixar Arquivo Excel", output.getvalue(), "Acervo.xlsx")

    with tab_import:
        if st.session_state.perfil != "Diretor": st.warning("Acesso restrito ao Diretor.")
        else:
            f_diretor = st.file_uploader("Selecione a planilha 'Livros Escaneados'", type=['xlsx'])
            if f_diretor:
                try:
                    df_up = pd.read_excel(f_diretor, sheet_name='livros escaneados')
                    res_db = supabase.table("livros_acervo").select("isbn, titulo").execute()
                    df_banco = pd.DataFrame(res_db.data)
                    novos, conf = [], []
                    for _, row in df_up.iterrows():
                        i_up = str(row.get('ISBN', '')).strip().replace(".0", "")
                        t_up = str(row.get('Título', '')).strip()
                        if i_up in ["nan", "N/A", ""]: i_up = ""
                        match = False
                        if not df_banco.empty:
                            if (i_up != "" and i_up in df_banco['isbn'].values) or (df_banco['titulo'].str.lower().values == t_up.lower()).any(): match = True
                        dados = {"isbn": i_up, "titulo": t_up, "autor": str(row.get('Autor(es)', 'Pendente')), "sinopse": str(row.get('Sinopse', 'Pendente')), "genero": str(row.get('Categorias', 'Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')}
                        if match: conf.append(dados)
                        else: novos.append(dados)
                    if novos:
                        st.success(f"{len(novos)} novos livros.")
                        if st.button("🚀 Importar Novos"): supabase.table("livros_acervo").insert(novos).execute(); st.success("Importado!"); st.rerun()
                    if conf:
                        st.warning(f"{len(conf)} duplicados.")
                        st.dataframe(pd.DataFrame(conf)[['titulo', 'isbn']])
                        if st.button("➕ Forçar Importação"): supabase.table("livros_acervo").insert(conf).execute(); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

# =================================================================
# 8. CURADORIA INTELIGENTE (IA - CASCATA GOOGLE + GEMINI 2.0)
# =================================================================
elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Curadoria Inteligente")
    api_key_gemini = st.text_input("Insira sua Gemini API Key:", type="password")
    if api_key_gemini:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_pend = pd.DataFrame(res.data)
        if not df_pend.empty:
            st.warning(f"Existem {len(df_pend)} registros incompletos.")
            if st.button("✨ Iniciar IA"):
                prog, status_txt = st.progress(0), st.empty()
                api_key_google = st.secrets["google"]["books_api_key"]
                for i, row in df_pend.iterrows():
                    status_txt.text(f"Limpando: {row['titulo']}...")
                    f_autor, f_sinopse, f_genero = row['autor'], row['sinopse'], row['genero']
                    try:
                        url_g = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_key_google}"
                        rg = requests.get(url_g, headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                        if "items" in rg:
                            info = rg["items"][0]["volumeInfo"]
                            if f_autor == "Pendente": f_autor = ", ".join(info.get("authors", ["Pendente"]))
                            if f_sinopse == "Pendente": f_sinopse = info.get("description", "Pendente")
                    except: pass
                    if f_autor == "Pendente" or f_sinopse == "Pendente" or len(f_sinopse) < 30:
                        prompt = f"Livro: {row['titulo']}. Responda apenas: Autor; Sinopse Curta; Gênero Literário. Separe por ';'."
                        url_gemini = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key_gemini}"
                        try:
                            resp = requests.post(url_gemini, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                            if resp.status_code == 200:
                                partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                if len(partes) >= 3:
                                    if f_autor == "Pendente": f_autor = partes[0].strip()
                                    f_sinopse, f_genero = partes[1].strip(), partes[2].strip().capitalize()
                        except: pass
                    supabase.table("livros_acervo").update({"autor": f_autor, "sinopse": f_sinopse, "genero": f_genero}).eq("id", row['id']).execute()
                    prog.progress((i + 1) / len(df_pend))
                st.success("Concluído!"); st.rerun()
        else: st.success("Tudo em ordem!")