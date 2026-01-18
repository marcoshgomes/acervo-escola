import streamlit as st

# =================================================================
# 1. CAPTURA DE ISBN (DEVE SER A PRIMEIRA COISA NO CÓDIGO)
# =================================================================
# Verificamos se existe um ISBN na URL antes de carregar o resto
if "isbn" in st.query_params:
    st.session_state.isbn_detectado = st.query_params["isbn"]
    # Limpa o parâmetro da URL para o navegador não ficar em loop
    st.query_params.clear()

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
# 2. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR
# =================================================================
st.set_page_config(page_title="Acervo Inteligente Cloud", layout="centered", page_icon="📚")

st.markdown("""
    <head><meta name="google" content="notranslate"></head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
""", unsafe_allow_html=True)

# =================================================================
# 3. CONEXÃO COM O BANCO DE DADOS (SUPABASE)
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
# 4. DICIONÁRIO E FUNÇÕES DE APOIO
# =================================================================
GENEROS_BASE = ["Ficção", "Infantil", "Juvenil", "Didático", "Poesia", "História", "Ciências", "Artes", "Gibis/HQ", "Religião", "Filosofia"]
TRADUCAO_GENEROS = {"Fiction": "Ficção", "Education": "Didático", "History": "História", "General": "Geral"}

def traduzir_genero(genero_ingles):
    if not genero_ingles: return "Geral"
    return TRADUCAO_GENEROS.get(genero_ingles, genero_ingles)

# =================================================================
# 5. COMPONENTE SCANNER (VERSÃO REDIRECIONAMENTO FORÇADO)
# =================================================================
def camera_barcode_scanner():
    """Scanner que força a câmera traseira e recarrega a página com o ISBN"""
    st.subheader("📷 Leitor Digital")
    
    scanner_html = """
    <div id="reader-container" style="width:100%; font-family: sans-serif; text-align:center;">
        <div id="reader" style="width:100%; border-radius:10px; border: 2px solid #d97706; overflow:hidden;"></div>
        <div id="result-box" style="display:none; padding:20px; border:2px solid #22c55e; border-radius:10px; margin-top:10px; background:#f0fdf4;">
            <p style="margin:0; color:#166534; font-weight:bold;">LIVRO LIDO!</p>
            <h2 id="isbn-txt" style="margin:15px 0; color:#15803d; letter-spacing: 2px;">---</h2>
            <button id="confirm-link" style="background:#22c55e; color:white; border:none; padding:15px 25px; border-radius:8px; font-weight:bold; cursor:pointer; width:100%; font-size:1.2em;">✅ CONFIRMAR E CARREGAR</button>
        </div>
    </div>
    
    <script src="https://unpkg.com/html5-qrcode"></script>
    <script>
        const html5QrCode = new Html5Qrcode("reader");
        let lastCode = "";

        function onScanSuccess(decodedText) {
            lastCode = decodedText;
            html5QrCode.stop().then(() => {
                document.getElementById('reader').style.display = 'none';
                document.getElementById('result-box').style.display = 'block';
                document.getElementById('isbn-txt').innerText = decodedText;
                if (navigator.vibrate) navigator.vibrate(200);
            });
        }

        // Função do Botão: Faz a página principal navegar para ela mesma com o ISBN na URL
        document.getElementById('confirm-link').onclick = function() {
            const currentUrl = new URL(window.top.location.href.split('?')[0]);
            currentUrl.searchParams.set("isbn", lastCode);
            window.top.location.href = currentUrl.href;
        };

        const config = { fps: 20, qrbox: {width: 250, height: 150} };
        html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess)
        .catch(err => {
            html5QrCode.start({ facingMode: "user" }, config, onScanSuccess);
        });
    </script>
    """
    components.html(scanner_html, height=500)

# =================================================================
# 6. SEGURANÇA E PERFIS
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
    else:
        st.sidebar.error("Senha inválida")

st.sidebar.title("📚 Acervo Cloud")
st.sidebar.write(f"Usuário: **{st.session_state.perfil}**")

if st.session_state.perfil == "Aluno":
    if st.sidebar.button("👤 Acesso Gestor"):
        st.session_state.mostrar_login = not st.session_state.mostrar_login
    if st.session_state.mostrar_login:
        st.sidebar.text_input("Senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    if st.sidebar.button("🚪 Sair"):
        st.session_state.perfil = "Aluno"; st.rerun()

menu = st.sidebar.selectbox("Navegação:", ["Entrada de Livros", "Gestão do Acervo", "Curadoria Inteligente (IA)"] if st.session_state.perfil == "Diretor" else ["Entrada de Livros", "Gestão do Acervo"] if st.session_state.perfil == "Professor" else ["Entrada de Livros"])

# =================================================================
# 7. ABA: ENTRADA DE LIVROS (FLUXO CORRIGIDO)
# =================================================================
if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    # Scanner
    camera_barcode_scanner()

    st.divider()
    
    # O valor aqui agora é alimentado pela captura da URL no topo do código
    isbn_input = st.text_input(
        "ISBN Confirmado:", 
        value=st.session_state.isbn_detectado, 
        key=f"field_{st.session_state.reset_count}"
    )

    if isbn_input:
        isbn_limpo = str(isbn_input).strip()
        res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res_check.data:
            item = res_check.data[0]
            st.info(f"📖 {item['titulo']} (Já cadastrado)")
            with st.form("form_inc"):
                qtd_add = st.number_input("Adicionar unidades:", 1)
                if st.form_submit_button("Atualizar Estoque"):
                    supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + qtd_add}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.isbn_detectado = ""
                    st.session_state.reset_count += 1
                    time.sleep(1); st.rerun()
        else:
            with st.spinner("Buscando dados no Google..."):
                headers = {"User-Agent": "Mozilla/5.0"}
                try:
                    api_key_google = st.secrets["google"]["books_api_key"]
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key_google}"
                    res = requests.get(url, headers=headers).json()
                    info = res["items"][0]["volumeInfo"]
                    dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                
                with st.form("form_novo"):
                    st.write("### ✨ Novo Cadastro")
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    g_sel = st.selectbox("Gênero", options=GENEROS_BASE + ["➕ CADASTRAR NOVO GÊNERO"])
                    g_novo = st.text_input("Gênero novo:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=100)
                    q_f = st.number_input("Quantidade inicial", 1)
                    if st.form_submit_button("🚀 Salvar no Banco"):
                        gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                        supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                        st.success("Salvo!")
                        st.session_state.isbn_detectado = ""
                        st.session_state.reset_count += 1
                        time.sleep(1); st.rerun()

# --- Outras abas (Gestão, IA) mantidas conforme versões anteriores ---
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Gestão")
    tab_view, tab_import = st.tabs(["📋 Lista e Edição", "📥 Importar Planilha do Diretor"])
    with tab_view:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("🔍 Localizar:")
            df_disp = df[df['titulo'].str.contains(termo, case=False) | df['isbn'].str.contains(termo)] if termo else df
            st.dataframe(df_disp[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            with st.expander("📝 Editar Registro"):
                opcoes = df_disp.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Escolha:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_sel = int(livro_sel.split("| ID:")[1]); item = df[df['id'] == id_sel].iloc[0]
                    with st.form("ed_form"):
                        nt = st.text_input("Título", item['titulo']); na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn']); ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=150); nq = st.number_input("Estoque", value=int(item['quantidade']))
                        if st.form_submit_button("💾 Salvar"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_sel).execute()
                            st.success("Alterado!"); st.rerun()
        if st.button("📥 Gerar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as wr:
                for g in df['genero'].unique():
                    aba = str(g)[:30]
                    df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=aba)
            st.download_button("Baixar Excel", output.getvalue(), "Acervo.xlsx")
    with tab_import:
        if st.session_state.perfil == "Diretor":
            f_diretor = st.file_uploader("Planilha do Diretor", type=['xlsx'])
            if f_diretor:
                try:
                    df_up = pd.read_excel(f_diretor, sheet_name='livros escaneados')
                    res_db = supabase.table("livros_acervo").select("isbn, titulo").execute()
                    df_b = pd.DataFrame(res_db.data)
                    novos, conf = [], []
                    for _, row in df_up.iterrows():
                        i_up = str(row.get('ISBN', '')).strip().replace(".0", "")
                        t_up = str(row.get('Título', '')).strip()
                        match = False
                        if not df_b.empty:
                            if (i_up != "" and i_up in df_b['isbn'].values) or (df_b['titulo'].str.lower().values == t_up.lower()).any(): match = True
                        d = {"isbn": i_up if i_up != "nan" else "", "titulo": t_up, "autor": str(row.get('Autor(es)', 'Pendente')), "sinopse": str(row.get('Sinopse', 'Pendente')), "genero": str(row.get('Categorias', 'Geral')), "quantidade": 1, "data_cadastro": datetime.now().strftime('%d/%m/%Y')}
                        if match: conf.append(d)
                        else: novos.append(d)
                    if novos:
                        st.success(f"{len(novos)} novos livros.")
                        if st.button("🚀 Importar Novos"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                    if conf:
                        st.warning(f"{len(conf)} duplicados."); st.dataframe(pd.DataFrame(conf)[['titulo', 'isbn']])
                        if st.button("➕ Forçar Importação"): supabase.table("livros_acervo").insert(conf).execute(); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Curadoria em Cascata")
    api_key_gemini = st.text_input("Gemini API Key:", type="password")
    if api_key_gemini:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_pend = pd.DataFrame(res.data)
        if not df_pend.empty:
            st.warning(f"Existem {len(df_pend)} registros pendentes.")
            if st.button("✨ Iniciar IA"):
                prog, status_txt = st.progress(0), st.empty()
                api_key_google = st.secrets["google"]["books_api_key"]
                for i, row in df_pend.iterrows():
                    status_txt.text(f"Limpando: {row['titulo']}...")
                    f_a, f_s, f_g = row['autor'], row['sinopse'], row['genero']
                    try:
                        url_g = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_key_google}"
                        rg = requests.get(url_g, headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                        if "items" in rg:
                            info = rg["items"][0]["volumeInfo"]
                            if f_a == "Pendente": f_a = ", ".join(info.get("authors", ["Pendente"]))
                            if f_s == "Pendente": f_s = info.get("description", "Pendente")
                    except: pass
                    if f_a == "Pendente" or f_s == "Pendente" or len(f_s) < 30:
                        prompt = f"Livro: {row['titulo']}. Responda apenas: Autor; Sinopse Curta; Gênero. Use ';' como separador."
                        url_gemini = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key_gemini}"
                        try:
                            resp = requests.post(url_gemini, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                            if resp.status_code == 200:
                                partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                if len(partes) >= 3:
                                    if f_a == "Pendente": f_a = partes[0].strip()
                                    f_s, f_g = partes[1].strip(), partes[2].strip().capitalize()
                        except: pass
                    supabase.table("livros_acervo").update({"autor": f_a, "sinopse": f_s, "genero": f_g}).eq("id", row['id']).execute()
                    prog.progress((i + 1) / len(df_pend))
                st.success("Curadoria concluída!"); st.rerun()