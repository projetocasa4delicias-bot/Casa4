import os
import re
import unicodedata
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Carrega as variáveis de ambiente
app.secret_key = os.environ.get('SECRET_KEY', 'uma-chave-secreta-padrao-para-desenvolvimento')
SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY: str = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Defina aqui o e-mail da conta que terá permissão para editar
MASTER_EMAIL = os.environ.get("MASTER_EMAIL", "projetocasa4delicias@gmail.com")

def sanitize_filename(nome):
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = nome.replace(" ", "_")
    nome = re.sub(r'[^a-zA-Z0-9._-]', '', nome)
    return nome

# --- LOGIN, CADASTRO E LOGOUT ---
@app.route('/')
def index():
    return redirect(url_for('pagina_login'))

@app.route('/login', methods=['GET', 'POST'])
def pagina_login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        try:
            resp = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        except Exception:
            flash('Erro na autenticação. Verifique suas credenciais.', 'danger')
            return redirect(url_for('pagina_login'))
        if resp.user:
            session['user'] = resp.user.email
            return redirect(url_for('painel'))
        else:
            flash('Email ou senha incorretos.', 'danger')
    return render_template('TelaLogin.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('pagina_login'))

# --- PAINEL PRINCIPAL ---
@app.route('/painel')
def painel():
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    
    is_master = session.get('user') == MASTER_EMAIL
    try:
        produtos = supabase_admin.table('produtos').select("*").order('nome', desc=False).execute().data
    except Exception:
        produtos = []
        flash("Erro ao carregar produtos.", "danger")
    try:
        receitas = supabase_admin.table('receitas').select("*").order('nome', desc=False).execute().data
        # Processa a string de ingredientes para virar uma lista
        for receita in receitas:
            if receita.get('ingredientes'):
                receita['ingredientes_lista'] = [ing.strip() for ing in receita['ingredientes'].split('\n') if ing.strip()]
    except Exception:
        receitas = []
        flash("Erro ao carregar receitas.", "danger")
    return render_template('painel.html', produtos=produtos, receitas=receitas, is_master=is_master)

# --- ROTAS DE MANIPULAÇÃO DE DADOS ---

@app.route('/adicionar_receita', methods=['POST'])
def adicionar_receita():
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    if session.get('user') != MASTER_EMAIL:
        flash('Você não tem permissão para realizar esta ação.', 'danger')
        return redirect(url_for('painel'))

    nome = request.form.get('nome')
    descricao = request.form.get('descricao')
    ingredientes = request.form.get('ingredientes')
    imagem = request.files.get('imagem')

    try:
        if imagem and imagem.filename != '':
            nome_arquivo = sanitize_filename(nome)
            # Lê o conteúdo do arquivo uma vez
            conteudo_imagem = imagem.read()
            # Usa a opção upsert para substituir se o arquivo já existir
            supabase_admin.storage.from_('imagens').upload(
                file=conteudo_imagem, path=nome_arquivo, file_options={"content-type": imagem.mimetype, "upsert": "true"}
            )
            url_imagem = supabase_admin.storage.from_('imagens').get_public_url(nome_arquivo)
        else:
            url_imagem = None

        supabase_admin.table('receitas').insert({"nome": nome, "descricao": descricao, "ingredientes": ingredientes, "imagem_url": url_imagem}).execute()
        flash('Receita adicionada com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar receita: {str(e)}', 'danger')
    return redirect(url_for('painel'))

@app.route('/editar_receita/<int:receita_id>', methods=['POST'])
def editar_receita(receita_id):
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    if session.get('user') != MASTER_EMAIL:
        return jsonify({"error": "Não autorizado"}), 403

    nome = request.form.get('nome')
    descricao = request.form.get('descricao')
    ingredientes = request.form.get('ingredientes')
    imagem = request.files.get('imagem')

    try:
        dados_update = {
            "nome": nome,
            "descricao": descricao,
            "ingredientes": ingredientes
        }

        if imagem and imagem.filename != '':
            nome_arquivo = sanitize_filename(nome)
            # O método upload com upsert=True substitui a imagem se já existir
            supabase_admin.storage.from_('imagens').upload(
                file=imagem.read(), path=nome_arquivo, file_options={"content-type": imagem.mimetype, "upsert": "true"}
            )
            url_imagem = supabase_admin.storage.from_('imagens').get_public_url(nome_arquivo)
            dados_update['imagem_url'] = url_imagem

        supabase_admin.table('receitas').update(dados_update).eq('id', receita_id).execute()
        updated_data = supabase_admin.table('receitas').select("*").eq('id', receita_id).single().execute().data
        return jsonify(updated_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/remover_receita/<int:receita_id>', methods=['POST'])
def remover_receita(receita_id):
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    if session.get('user') != MASTER_EMAIL:
        flash('Você não tem permissão para realizar esta ação.', 'danger')
        return redirect(url_for('painel'))

    try:
        supabase_admin.table('receitas').delete().eq('id', receita_id).execute()
        flash('Receita removida com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao remover receita: {str(e)}', 'danger')

    return redirect(url_for('painel'))

@app.route('/adicionar_produto', methods=['POST'])
def adicionar_produto():
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    if session.get('user') != MASTER_EMAIL:
        flash('Você não tem permissão para realizar esta ação.', 'danger')
        return redirect(url_for('painel'))
    nome = request.form.get('nome')
    preco = request.form.get('preco')
    quantidade = request.form.get('quantidade')
    imagem = request.files.get('imagem')
    try:
        if imagem and imagem.filename != '':
            nome_arquivo = sanitize_filename(nome)
            supabase_admin.storage.from_('imagens').upload(file=imagem.read(), path=nome_arquivo, file_options={"content-type": imagem.mimetype})
            url_imagem = supabase_admin.storage.from_('imagens').get_public_url(nome_arquivo)
        else:
            url_imagem = None
        supabase_admin.table('produtos').insert({"nome": nome, "preco": preco, "quantidade": quantidade, "imagem_url": url_imagem}).execute()
        flash('Produto adicionado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar produto: {str(e)}', 'danger')
    return redirect(url_for('painel'))

@app.route('/editar_produto/<int:produto_id>', methods=['POST'])
def editar_produto(produto_id):
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    if session.get('user') != MASTER_EMAIL:
        return jsonify({"error": "Não autorizado"}), 403
    nome = request.form.get('nome')
    preco = request.form.get('preco')
    quantidade = request.form.get('quantidade')
    imagem = request.files.get('imagem')
    try:
        dados_update = {"nome": nome, "preco": preco, "quantidade": quantidade}
        if imagem and imagem.filename != '':
            nome_arquivo = sanitize_filename(nome)
            supabase_admin.storage.from_('imagens').upload(file=imagem.read(), path=nome_arquivo, file_options={"content-type": imagem.mimetype, "upsert": "true"})
            url_imagem = supabase_admin.storage.from_('imagens').get_public_url(nome_arquivo)
            dados_update['imagem_url'] = url_imagem
        supabase_admin.table('produtos').update(dados_update).eq('id', produto_id).execute()
        updated_data = supabase_admin.table('produtos').select("*").eq('id', produto_id).single().execute().data
        return jsonify(updated_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/remover_produto/<int:produto_id>', methods=['POST'])
def remover_produto(produto_id):
    if 'user' not in session:
        return redirect(url_for('pagina_login'))
    if session.get('user') != MASTER_EMAIL:
        flash('Você não tem permissão para realizar esta ação.', 'danger')
        return redirect(url_for('painel'))
    supabase_admin.table('produtos').delete().eq('id', produto_id).execute()
    return redirect(url_for('painel'))

if __name__ == '__main__':
    # Para desenvolvimento local. Em produção, o Render usará o Gunicorn.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
