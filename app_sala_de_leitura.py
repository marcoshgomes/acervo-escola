import streamlit as st

# =================================================================
# 1. CAPTURA DE ISBN VIA URL (LOGO NO INÍCIO DO SCRIPT)
# =================================================================
# Verificamos se o ISBN veio pela URL (truque para comunicação JS -> Python)
query_params = st.query_params
if "isbn" in query_params:
    st.session_state.isbn_detectado = query_params["isbn"]
    # Limpa a URL para o navegador não ficar tentando recarregar o mesmo livro
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
# 5. COMPONENTE SCANNER (TELA EXCLUSIVA)
# =================================================================
def show_scanner_ui():
    """Mostra apenas a câmera e o botão de confirmação"""
    st.subheader("📷 Aponte para o Código de Barras")
    
    scanner_html = """
    <div id="reader-container" style="width:100%; font-family: sans-serif; text-align:center;">
        <div id="reader" style="width:100%; border-radius:10px; border: 3px solid #d97706; overflow:hidden;"></div>
        
        <div id="scanned-result" style="display:none; padding:20px; border:2px solid #22c55e; border-radius:10px; margin-top:10px; background:#f0fdf4;">
            <p style="margin:0; color:#166534; font-weight:bold;">CÓDIGO DETECTADO!</p>
            <h2 id="isbn-val" style="margin:15px 0; color:#15803d;">---</h2>
            <button id="confirm-btn" style="background:#22c55e; color:white; border:none; padding:15px 25px; border-radius:8px; font-weight:bold; cursor:pointer; width:100%; font-size:1.2em;">✅ CARREGAR DADOS DO LIVRO</button>
        </div>
    </div>
    
    <script src="https://unpkg.com/html5-qrcode"></script>
    <script>
        const html5QrCode = new Html5Qrcode("reader");
        let lastIsbn = "";

        function onScanSuccess(decodedText) {
            lastIsbn = decodedText;
            html5QrCode.stop().then(() => {
                document.getElementById('reader').style.display = 'none';
                document.getElementById('scanned-result').style.display = 'block';
                document.getElementById('isbn-val').innerText = decodedText;
                if (navigator.vibrate) navigator.vibrate(200);
            });
        }

        document.getElementById('confirm-btn').onclick = function() {
            // Recarrega a página passando o ISBN por URL (método mais seguro)
            const url = new URL(window.top.location.href.split('?')[0]);
            url.searchParams.set("isbn", lastIsbn);
            window.top.location.href = url.href;
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
if "isbn_detectado" not in st.session_state: st.session_state.isbn_detectado = ""
if "reset_count" not in st.session_state: st.session_state.reset_count = 0
if "mostrar_login" not in st.session_state: st.session_state.mostrar_login = False

SENHA_PROFESSOR = "1359307"
SENHA_DIRETOR = "7534833"

def verificar_senha():
    s = st.session_state.pwd_input.strip()
    if s == SENHA_DIRETOR: st.session_state.perfil = "Diretor"; st.session_state.mostrar_login = False
    elif s == SENHA_PROFESSOR: st.session_state.perfil = "Professor"; st.session_state.mostrar_login = False
    else: st.sidebar.error("Senha inválida")

st.sidebar.title("📚 Acervo Cloud")
st.sidebar.write(f"Usuário: **{st.session_state.perfil}**")

if st.session_state.perfil == "Aluno":
    if st.sidebar.button("👤 Acesso Gestor"):
        st.session_state.mostrar_login = not st.session_state.mostrar_login
    if st.session_state.mostrar_login:
        st.sidebar.text_input("Senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    if st.sidebar.button("🚪 Sair"): st.session_state.perfil = "Aluno"; st.rerun()

menu = st.sidebar.selectbox("Navegação:", ["Entrada de Livros", "Gestão do Acervo", "Curadoria Inteligente (IA)"] if st.session_state.perfil == "Diretor" else ["Entrada de Livros", "Gestão do Acervo"] if st.session_state.perfil == "Professor" else ["Entrada de Livros"])

# =================================================================
# 7. ABA: ENTRADA DE LIVROS (LÓGICA DE DUAS ETAPAS)
# =================================================================
if menu == "Entrada de Livros":
    st.header("🚚 Registro de Volumes")

    # --- ETAPA 1: SCANNER (Só aparece se o ISBN estiver vazio) ---
    if not st.session_state.isbn_detectado:
        show_scanner_ui()
        st.info("Aponte para o código de barras. Ou digite abaixo:")
        manual_isbn = st.text_input("Digitar ISBN Manualmente:")
        if manual_isbn:
            st.session_state.isbn_detectado = manual_isbn
            st.rerun()
    
    # --- ETAPA 2: CADASTRO (Só aparece se o ISBN já foi capturado) ---
    else:
        isbn_limpo = str(st.session_state.isbn_detectado).strip()
        st.success(f"📌 ISBN em processamento: {isbn_limpo}")
        
        if st.button("⬅️ Cancelar / Escanear outro"):
            st.session_state.isbn_detectado = ""
            st.rerun()

        res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res_check.data:
            # LIVRO EXISTE
            item = res_check.data[0]
            st.info(f"📖 {item['titulo']} (Já cadastrado)")
            with st.form("form_inc"):
                qtd_add = st.number_input("Volumes adicionais:", 1)
                if st.form_submit_button("Atualizar na Nuvem"):
                    supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + qtd_add}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!")
                    st.session_state.isbn_detectado = ""
                    time.sleep(1); st.rerun()
        else:
            # LIVRO NOVO
            with st.spinner("Buscando detalhes no Google..."):
                headers = {"User-Agent": "Mozilla/5.0"}
                try:
                    api_key_google = st.secrets["google"]["books_api_key"]
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={api_key_google}"
                    res = requests.get(url, headers=headers).json()
                    info = res["items"][0]["volumeInfo"]
                    dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                
                with st.form("form_novo"):
                    st.subheader("✨ Novo Cadastro")
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    g_sel = st.selectbox("Gênero", options=GENEROS_BASE + ["➕ NOVO GÊNERO"])
                    g_novo = st.text_input("Digite se escolheu NOVO:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=150)
                    q_f = st.number_input("Quantidade inicial", 1)
                    if st.form_submit_button("🚀 Salvar no Banco"):
                        gen_final = g_novo.strip().capitalize() if g_sel == "➕ NOVO GÊNERO" else g_sel
                        supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                        st.success("Cadastrado!"); st.session_state.isbn_detectado = ""
                        time.sleep(1); st.rerun()

# --- ABAS DE GESTÃO E IA MANTIDAS IGUAIS (FUNCIONANDO) ---
elif menu == "Gestão do Acervo":
    st.header("📊 Gestão")
    tab_v, tab_i = st.tabs(["📋 Lista", "📥 Importar Planilha do Diretor"])
    with tab_v:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("🔍 Pesquisar:")
            df_d = df[df['titulo'].str.contains(termo, case=False)] if termo else df
            st.dataframe(df_d[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            with st.expander("📝 Editar Registro"):
                opcoes = df_d.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Escolha:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_s = int(livro_sel.split("| ID:")[1]); item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_form"):
                        nt = st.text_input("Título", item['titulo']); na = st.text_input("Autor", item['autor'])
                        ni = st.text_input("ISBN", item['isbn']); ng = st.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=100); nq = st.number_input("Qtd", value=int(item['quantidade']))
                        if st.form_submit_button("💾 Salvar"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("OK!"); st.rerun()
        if st.button("📥 Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as wr:
                for g in df['genero'].unique():
                    df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=str(g)[:30])
            st.download_button("Baixar Excel", output.getvalue(), "Acervo.xlsx")
    with tab_i:
        if st.session_state.perfil == "Diretor":
            f = st.file_uploader("Excel do Diretor", type=['xlsx'])
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
                        st.success(f"{len(novos)} novos."); 
                        if st.button("🚀 Importar"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                    if conf:
                        st.warning(f"{len(conf)} duplicados."); 
                        if st.button("➕ Forçar Importação"): supabase.table("livros_acervo").insert(conf).execute(); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Curadoria em Cascata")
    api_k = st.text_input("Gemini API Key:", type="password")
    if api_k:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_p = pd.DataFrame(res.data)
        if not df_p.empty:
            st.warning(f"{len(df_p)} pendentes.")
            if st.button("✨ Iniciar IA"):
                prog, stxt = st.progress(0), st.empty()
                api_g = st.secrets["google"]["books_api_key"]
                for i, row in df_p.iterrows():
                    stxt.text(f"Limpando: {row['titulo']}...")
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
                        prompt = f"Livro: {row['titulo']}. Responda apenas: Autor; Sinopse Curta; Gênero. Use ';' como separador."
                        url_gem = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_k}"
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