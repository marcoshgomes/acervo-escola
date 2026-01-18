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
import google.generativeai as genai

# =================================================================
# 1. CONFIGURAÇÃO E PROTEÇÃO ANTI-TRADUTOR
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
# 5. ABA: ENTRADA DE LIVROS
# =================================================================
if menu == "Entrada de Livros":
    st.header("🚚 Entrada de Volumes")
    foto_upload = st.file_uploader("📷 Foto do código de barras", type=['png', 'jpg', 'jpeg'], key=f"up_{st.session_state.reset_count}")
    
    if foto_upload:
        with st.spinner("Lendo imagem..."):
            img_pil = Image.open(foto_upload)
            img_pil.thumbnail((800, 800))
            img_cv = np.array(img_pil.convert('RGB'))
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            detector = cv2.barcode.BarcodeDetector()
            resultado = detector.detectAndDecode(gray)
            codigo_lido = ""
            if resultado and len(resultado) > 0:
                for item in resultado:
                    if isinstance(item, (list, tuple, np.ndarray)) and len(item) > 0:
                        if isinstance(item[0], str) and len(item[0]) > 5:
                            codigo_lido = item[0]; break
            if codigo_lido:
                st.success(f"✅ Código detectado: {codigo_lido}")
                if st.button("Confirmar e Carregar Dados"):
                    st.session_state.isbn_detectado = codigo_lido; st.session_state.reset_count += 1; st.rerun()

    isbn_input = st.text_input("ISBN Confirmado:", value=st.session_state.isbn_detectado, key=f"field_{st.session_state.reset_count}")

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
                    st.success("Estoque atualizado!"); time.sleep(1); st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()
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
                    g_novo = st.text_input("Se novo gênero:")
                    s_f = st.text_area("Sinopse", dados['sinopse'], height=100)
                    q_f = st.number_input("Quantidade", 1)
                    if st.form_submit_button("🚀 Salvar"):
                        gen_final = g_novo.strip().capitalize() if g_sel == "➕ CADASTRAR NOVO GÊNERO" else g_sel
                        supabase.table("livros_acervo").insert({"isbn": isbn_limpo, "titulo": t_f, "autor": a_f, "sinopse": s_f, "genero": gen_final, "quantidade": q_f, "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')}).execute()
                        st.success("Livro salvo!"); time.sleep(1); st.session_state.isbn_detectado = ""; st.session_state.reset_count += 1; st.rerun()

# =================================================================
# 6. ABA: GESTÃO (ADAPTADA PARA PLANILHA DO DIRETOR)
# =================================================================
elif menu == "Gestão do Acervo":
    st.header("📊 Painel de Gestão")
    tab_view, tab_import = st.tabs(["📋 Visualizar e Editar", "📥 Importar Planilha do Diretor"])

    with tab_view:
        res = supabase.table("livros_acervo").select("*").execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            termo = st.text_input("🔍 Pesquisar por Título ou Autor:")
            df_display = df[df['titulo'].str.contains(termo, case=False) | df['autor'].str.contains(termo, case=False)] if termo else df
            st.dataframe(df_display[['titulo', 'autor', 'genero', 'quantidade', 'isbn']], use_container_width=True)
            
            with st.expander("📝 Editar Registro Completo"):
                opcoes = df_display.apply(lambda x: f"{x['titulo']} | ID:{x['id']}", axis=1).tolist()
                livro_sel = st.selectbox("Selecione para editar:", ["..."] + opcoes)
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
                            st.success("Dados atualizados!"); time.sleep(1); st.rerun()

    with tab_import:
        if st.session_state.perfil != "Diretor":
            st.warning("Apenas o Diretor pode importar planilhas externas.")
        else:
            st.subheader("Upload de 'Livros Escaneados'")
            st.info("O sistema lerá a aba 'livros escaneados' da planilha do Diretor.")
            file_diretor = st.file_uploader("Selecione o arquivo Excel", type=['xlsx'])
            
            if file_diretor:
                try:
                    # Lê especificamente a aba informada
                    df_up = pd.read_excel(file_diretor, sheet_name='livros escaneados')
                    
                    # Buscar o banco atual para comparar duplicidade
                    res_db = supabase.table("livros_acervo").select("isbn, titulo, autor").execute()
                    df_banco = pd.DataFrame(res_db.data)
                    
                    novos_livros = []
                    conflitos = []

                    for _, row in df_up.iterrows():
                        # Mapeamento exato das colunas da imagem
                        isbn_up = str(row.get('ISBN', '')).strip().replace(".0", "")
                        titulo_up = str(row.get('Título', '')).strip()
                        autor_up = str(row.get('Autor(es)', 'Pendente')).strip()
                        genero_up = str(row.get('Categorias', 'Geral')).strip()
                        sinopse_up = str(row.get('Sinopse', 'Pendente')).strip()
                        
                        # Limpeza de termos "vazios" do Excel
                        if isbn_up in ["nan", "N/A", ""]: isbn_up = ""
                        if autor_up in ["nan", "N/A", "Não disponível", ""]: autor_up = "Pendente"
                        if genero_up in ["nan", "N/A", ""]: genero_up = "Geral"
                        if sinopse_up in ["nan", "N/A", "Não disponível", ""]: sinopse_up = "Pendente"

                        # --- LÓGICA DE DUPLICIDADE ---
                        match_isbn = False
                        match_titulo_autor = False

                        if not df_banco.empty:
                            if isbn_up != "" and isbn_up in df_banco['isbn'].values:
                                match_isbn = True
                            
                            # Checa Título + Autor ignorando maiúsculas
                            filt = df_banco[(df_banco['titulo'].str.lower() == titulo_up.lower()) & 
                                            (df_banco['autor'].str.lower() == autor_up.lower())]
                            if not filt.empty:
                                match_titulo_autor = True

                        dados_prontos = {
                            "isbn": isbn_up, "titulo": titulo_up, "autor": autor_up,
                            "sinopse": sinopse_up, "genero": genero_up, "quantidade": 1,
                            "data_cadastro": datetime.now().strftime('%d/%m/%Y %H:%M')
                        }

                        if match_isbn or match_titulo_autor:
                            conflitos.append(dados_prontos)
                        else:
                            novos_livros.append(dados_prontos)

                    # Interface de decisão
                    if novos_livros:
                        st.success(f"✨ Encontrados {len(novos_livros)} livros novos para importar.")
                        if st.button("🚀 Confirmar Importação dos Novos"):
                            supabase.table("livros_acervo").insert(novos_livros).execute()
                            st.success("Novos livros cadastrados!"); time.sleep(1); st.rerun()

                    if conflitos:
                        st.warning(f"⚠️ Existem {len(conflitos)} livros que já possuem registro semelhante no banco.")
                        df_conf = pd.DataFrame(conflitos)
                        st.dataframe(df_conf[['titulo', 'autor', 'isbn']], use_container_width=True)
                        
                        if st.button("➕ Forçar Importação destes Duplicados"):
                            supabase.table("livros_acervo").insert(conflitos).execute()
                            st.success("Registros forçados com sucesso!"); time.sleep(1); st.rerun()

                except Exception as e:
                    st.error(f"Erro ao ler a planilha: {e}. Verifique se o nome da aba é 'livros escaneados'.")

# =================================================================
# 7. ABA: CURADORIA INTELIGENTE (IA)
# =================================================================
elif menu == "Curadoria Inteligente (IA)":
    st.header("🪄 Curadoria em Cascata")
    api_key_gemini = st.text_input("Insira sua Gemini API Key:", type="password")
    
    if api_key_gemini:
        res = supabase.table("livros_acervo").select("*").or_("autor.eq.Pendente,sinopse.eq.Pendente").execute()
        df_pend = pd.DataFrame(res.data)
        
        if not df_pend.empty:
            st.warning(f"Encontrados {len(df_pend)} registros para processar.")
            if st.button("✨ Iniciar Processamento Inteligente"):
                progresso = st.progress(0)
                status_txt = st.empty()
                api_key_google = st.secrets["google"]["books_api_key"]

                for i, row in df_pend.iterrows():
                    status_txt.text(f"Processando: {row['titulo']}...")
                    f_autor, f_sinopse, f_genero = row['autor'], row['sinopse'], row['genero']

                    # 1. Google Books (Oficial)
                    try:
                        url_g = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{row['titulo']}&key={api_key_google}"
                        rg = requests.get(url_g, headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                        if "items" in rg:
                            info = rg["items"][0]["volumeInfo"]
                            if f_autor == "Pendente": f_autor = ", ".join(info.get("authors", ["Pendente"]))
                            if f_sinopse == "Pendente": f_sinopse = info.get("description", "Pendente")
                            f_genero = traduzir_genero(info.get("categories", [f_genero])[0])
                    except: pass

                    # 2. Gemini (Inteligência Artificial)
                    if f_autor == "Pendente" or f_sinopse == "Pendente" or len(f_sinopse) < 30:
                        prompt = f"Livro: {row['titulo']}. Autor Atual: {f_autor}. Retorne apenas: Autor; Sinopse(3 linhas); Gênero. Use ';' como separador."
                        url_gemini = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key_gemini}"
                        try:
                            resp = requests.post(url_gemini, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}), timeout=10)
                            if resp.status_code == 200:
                                partes = resp.json()['candidates'][0]['content']['parts'][0]['text'].split(";")
                                if len(partes) >= 3:
                                    if f_autor == "Pendente": f_autor = partes[0].strip()
                                    f_sinopse = partes[1].strip()
                                    f_genero = partes[2].strip().capitalize()
                        except: pass

                    supabase.table("livros_acervo").update({"autor": f_autor, "sinopse": f_sinopse, "genero": f_genero}).eq("id", row['id']).execute()
                    progresso.progress((i + 1) / len(df_pend))
                st.success("Curadoria concluída!"); time.sleep(1); st.rerun()
        else: st.success("Banco de dados completo!")