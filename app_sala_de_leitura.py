import streamlit as st

# =================================================================
# 1. CAPTURA DE ISBN (DEVE SER A PRIMEIRA COISA PARA NÃO PERDER O DADO)
# =================================================================
if "isbn" in st.query_params:
    # Captura o número vindo do scanner e salva na sessão
    st.session_state.isbn_detectado = st.query_params["isbn"]
    # Limpa a URL para o navegador não ficar recarregando o mesmo livro
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

def traduzir_genero(genero_ingles):
    mapa = {"Fiction": "Ficção", "Education": "Didático", "History": "História"}
    return mapa.get(genero_ingles, "Geral")

# =================================================================
# 5. COMPONENTE SCANNER COM "LINK DE FUGA" (ESTILO LOVABLE)
# =================================================================
def show_barcode_scanner():
    """Scanner que interrompe o iframe e envia o dado para a página principal"""
    st.subheader("📷 Leitor Digital")
    
    scanner_html = """
    <div id="scanner-container" style="text-align:center; font-family:sans-serif;">
        <div id="interactive" style="width:100%; border-radius:10px; border:3px solid #d97706; overflow:hidden;"></div>
        
        <div id="result-panel" style="display:none; padding:20px; border:3px solid #22c55e; border-radius:10px; margin-top:10px; background:#f0fdf4;">
            <p style="margin:0; color:#166534; font-weight:bold;">LIVRO IDENTIFICADO!</p>
            <h1 id="isbn-code" style="margin:15px 0; color:#15803d; letter-spacing:2px;">---</h1>
            
            <!-- O BOTÃO VERDE AGORA É UM LINK DE FUGA -->
            <a id="btn-confirmar" target="_top" style="display:block; background:#22c55e; color:white; text-decoration:none; padding:18px; border-radius:10px; font-weight:bold; font-size:1.3em; box-shadow:0 4px 10px rgba(0,0,0,0.2);">
                ✅ CONFIRMAR E CARREGAR
            </a>
            
            <p onclick="location.reload()" style="margin-top:15px; color:#666; text-decoration:underline; cursor:pointer;">Tentar novamente</p>
        </div>
    </div>
    
    <script src="https://unpkg.com/html5-qrcode"></script>
    <script>
        const html5QrCode = new Html5Qrcode("interactive");
        
        function onScanSuccess(decodedText) {
            // Vibra o celular e para a câmera
            if (navigator.vibrate) navigator.vibrate(200);
            
            html5QrCode.stop().then(() => {
                document.getElementById('interactive').style.display = 'none';
                document.getElementById('result-panel').style.display = 'block';
                document.getElementById('isbn-code').innerText = decodedText;
                
                // Configura o link de fuga com o ISBN detectado
                const baseUrl = window.parent.location.href.split('?')[0];
                document.getElementById('btn-confirmar').href = baseUrl + "?isbn=" + decodedText;
            });
        }

        const config = { fps: 25, qrbox: {width: 250, height: 150} };
        html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess)
        .catch(err => {
            html5QrCode.start({ facingMode: "user" }, config, onScanSuccess);
        });
    </script>
    """
    import streamlit.components.v1 as components
    components.html(scanner_html, height=550)

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
    if st.sidebar.button("👤 Acesso Gestor do Sistema"):
        st.session_state.mostrar_login = not st.session_state.mostrar_login
    if st.session_state.mostrar_login:
        st.sidebar.text_input("Senha:", type="password", key="pwd_input", on_change=verificar_senha)
else:
    if st.sidebar.button("🚪 Sair"): st.session_state.perfil = "Aluno"; st.rerun()

menu = st.sidebar.selectbox("Navegação:", ["Entrada de Livros", "Gestão do Acervo", "Curadoria Inteligente (IA)"] if st.session_state.perfil == "Diretor" else ["Entrada de Livros", "Gestão do Acervo"] if st.session_state.perfil == "Professor" else ["Entrada de Livros"])

# =================================================================
# 7. ABA: ENTRADA DE LIVROS (LOGICA DE TRANSFERÊNCIA GARANTIDA)
# =================================================================
if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    
    # Se não há ISBN, mostra o Scanner
    if not st.session_state.isbn_detectado:
        show_barcode_scanner()
        st.write("---")
        manual = st.text_input("Ou digite o ISBN manualmente:")
        if manual: 
            st.session_state.isbn_detectado = manual
            st.rerun()
    
    # Se o ISBN foi capturado, mostra o formulário
    else:
        isbn_limpo = str(st.session_state.isbn_detectado).strip()
        st.success(f"📖 ISBN Capturado: {isbn_limpo}")
        
        if st.button("🔄 Cancelar e Escanear de novo"):
            st.session_state.isbn_detectado = ""
            st.rerun()

        res_check = supabase.table("livros_acervo").select("*").eq("isbn", isbn_limpo).execute()
        
        if res_check.data:
            item = res_check.data[0]
            st.info(f"O livro '{item['titulo']}' já está no acervo.")
            with st.form("f_estoque"):
                add = st.number_input("Adicionar unidades:", 1)
                if st.form_submit_button("Atualizar Estoque"):
                    supabase.table("livros_acervo").update({"quantidade": int(item['quantidade']) + add}).eq("isbn", isbn_limpo).execute()
                    st.success("Estoque atualizado!"); st.session_state.isbn_detectado = ""; time.sleep(1); st.rerun()
        else:
            with st.spinner("Buscando no Google..."):
                headers = {"User-Agent": "Mozilla/5.0"}
                try:
                    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_limpo}&key={st.secrets['google']['books_api_key']}"
                    res = requests.get(url, headers=headers).json()
                    info = res["items"][0]["volumeInfo"]
                    dados = {"titulo": info.get("title", ""), "autor": ", ".join(info.get("authors", ["Pendente"])), "sinopse": info.get("description", "Pendente"), "genero": traduzir_genero(info.get("categories", ["General"])[0])}
                except: dados = {"titulo": "", "autor": "Pendente", "sinopse": "Pendente", "genero": "Geral"}
                
                with st.form("f_novo"):
                    st.subheader("✨ Novo Cadastro")
                    t_f = st.text_input("Título", dados['titulo'])
                    a_f = st.text_input("Autor", dados['autor'])
                    g_sel = st.selectbox("Gênero", options=GENEROS_BASE + ["➕ CADASTRAR NOVO"])
                    g_novo = st.text_input("Se novo:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=100)
                    q_f = st.number_input("Quantidade", 1)
                    if st.form_submit_button("🚀 Salvar no Banco"):
                        gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO" else g_sel
                        supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                        st.success("Salvo!"); st.session_state.isbn_detectado = ""; time.sleep(1); st.rerun()

# =================================================================
# 8. GESTÃO DO ACERVO (EDIÇÃO TOTAL LIBERADA)
# =================================================================
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Gestão")
    tab_list, tab_import = st.tabs(["📋 Lista e Edição Completa", "📥 Importar Planilha do Diretor"])
    
    with tab_list:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("🔍 Localizar por Título ou ISBN:")
            df_d = df[df['titulo'].str.contains(termo, case=False) | df['isbn'].str.contains(termo)] if termo else df
            st.dataframe(df_d[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 CORREÇÃO MANUAL DE CAMPOS"):
                opcoes = df_d.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Selecione o livro:", ["..."] + opcoes)
                if livro_sel != "...":
                    id_s = int(livro_sel.split("| ID:")[1])
                    item = df[df['id'] == id_s].iloc[0]
                    with st.form("ed_completa"):
                        # AQUI: TODOS OS CAMPOS LIBERADOS PARA EDIÇÃO
                        c1, c2 = st.columns(2)
                        nt = c1.text_input("Título do Livro", item['titulo'])
                        na = c2.text_input("Autor(es)", item['autor'])
                        ni = c1.text_input("ISBN", item['isbn'])
                        ng = c2.text_input("Gênero", item['genero'])
                        ns = st.text_area("Sinopse", item['sinopse'], height=150)
                        nq = st.number_input("Quantidade em Estoque", value=int(item['quantidade']))
                        
                        if st.form_submit_button("💾 SALVAR ALTERAÇÕES NO BANCO"):
                            supabase.table("livros_acervo").update({"titulo": nt, "autor": na, "isbn": ni, "genero": ng, "sinopse": ns, "quantidade": nq}).eq("id", id_s).execute()
                            st.success("As informações foram corrigidas!"); time.sleep(1); st.rerun()

        if st.button("📥 Baixar Excel"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as wr:
                for g in df['genero'].unique():
                    aba = "".join(c for c in str(g) if c.isalnum() or c==' ')[:30]
                    df[df['genero']==g][['titulo','sinopse','autor','quantidade']].to_excel(wr, index=False, sheet_name=aba)
            st.download_button("Clique aqui para Baixar", output.getvalue(), "Acervo_Escolar.xlsx")

    with tab_import:
        if st.session_state.perfil == "Diretor":
            f_diretor = st.file_uploader("Upload da Planilha Diretor", type=['xlsx'])
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
                        st.success(f"{len(novos)} novos livros."); 
                        if st.button("🚀 Importar"): supabase.table("livros_acervo").insert(novos).execute(); st.rerun()
                    if conf:
                        st.warning(f"{len(conf)} duplicados."); st.dataframe(pd.DataFrame(conf)[['titulo', 'isbn']])
                        if st.button("➕ Forçar Importação"): supabase.table("livros_acervo").insert(conf).execute(); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

# =================================================================
# 9. CURADORIA IA (Google + Gemini 2.0 Flash)
# =================================================================
elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Curadoria em Cascata")
    api_k = st.text_input("Gemini API Key:", type="password")
    if api_k:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_p = pd.DataFrame(res.data)
        if not df_p.empty:
            st.warning(f"Existem {len(df_p)} registros pendentes.")
            if st.button("✨ Iniciar IA"):
                prog, stxt = st.progress(0), st.empty(); api_g = st.secrets["google"]["books_api_key"]
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
                st.success("Curadoria concluída!"); st.rerun()