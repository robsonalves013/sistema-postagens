import os
from datetime import datetime, date
from calendar import monthrange
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, after_this_request
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sua_chave_padrao')

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Database config
DATABASE_URL = os.environ.get('DATABASE_URL')
NOME_POSTO = {1: "Shopping Bolívia", 2: "Hotel Family"}

# Role decorators
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Acesso restrito a administradores', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def balcao_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role not in ('admin', 'balcao'):
            flash('Acesso restrito ao balcão', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

@app.template_filter('datetimeformat')
def datetimeformat(value, fmt='%d/%m/%Y'):
    if not value:
        return ''
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
    else:
        dt = value
    return dt.strftime(fmt)

class User(UserMixin):
    def __init__(self, id, username, pwd_hash, nome_completo, role):
        self.id = id
        self.username = username
        self.password_hash = pwd_hash
        self.nome_completo = nome_completo
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = sistema.conectar(); cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE id=%s", (int(user_id),))
    u = cur.fetchone(); conn.close()
    if u:
        return User(u['id'], u['username'], u['password_hash'], u['nome_completo'], u['role'])
    return None

class SistemaPostagem:
    def __init__(self, db_url=DATABASE_URL):
        self.db_url = db_url

    def conectar(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def criar_tabelas(self):
        sql = """
        CREATE TABLE IF NOT EXISTS postagens (
            id SERIAL PRIMARY KEY,
            data_postagem DATE NOT NULL,
            posto INTEGER NOT NULL,
            nome_remetente TEXT NOT NULL,
            codigo_rastreio TEXT UNIQUE NOT NULL,
            valor NUMERIC NOT NULL,
            tipo_postagem TEXT NOT NULL CHECK (tipo_postagem IN ('PAC','SEDEX')),
            tipo_pagamento TEXT,
            pagamento_pago BOOLEAN DEFAULT FALSE,
            data_pagamento DATE,
            observacoes TEXT,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fechamento_diario (
            id SERIAL PRIMARY KEY,
            data_fechamento DATE NOT NULL,
            posto INTEGER NOT NULL,
            total_postagens INTEGER NOT NULL,
            total_valor NUMERIC NOT NULL,
            total_pac INTEGER NOT NULL,
            total_sedex INTEGER NOT NULL,
            total_pix NUMERIC NOT NULL,
            total_dinheiro NUMERIC NOT NULL,
            funcionario TEXT NOT NULL,
            observacoes TEXT,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(data_fechamento, posto)
        );
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nome_completo TEXT NOT NULL,
            role TEXT DEFAULT 'balcao',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        conn = self.conectar(); cur = conn.cursor()
        cur.execute(sql); conn.commit(); conn.close()

    def adicionar_postagem(self, dp, posto, nom, cod, val, tp, tpag=None, pago=False, dpag=None, obs=None):
        conn = self.conectar(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO postagens (
              data_postagem, posto, nome_remetente, codigo_rastreio,
              valor, tipo_postagem, tipo_pagamento, pagamento_pago,
              data_pagamento, observacoes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (dp, posto, nom, cod, val, tp, tpag, pago, dpag, obs))
        conn.commit(); conn.close()

    def listar_postagens_dia(self, data, posto=None):
        conn = self.conectar(); cur = conn.cursor()
        if posto:
            cur.execute(
                "SELECT * FROM postagens WHERE data_postagem=%s AND posto=%s ORDER BY data_criacao DESC",
                (data, posto)
            )
        else:
            cur.execute(
                "SELECT * FROM postagens WHERE data_postagem=%s ORDER BY posto,data_criacao DESC",
                (data,)
            )
        rows = cur.fetchall(); conn.close(); return rows

    def listar_pendentes(self):
        conn = self.conectar(); cur = conn.cursor()
        cur.execute("SELECT * FROM postagens WHERE pagamento_pago=FALSE ORDER BY data_postagem", ())
        rows = cur.fetchall(); conn.close(); return rows

    def resumo_dia(self, data, posto):
        conn = self.conectar(); cur = conn.cursor()
        cur.execute("""
            SELECT
              COUNT(*) AS total_postagens,
              COALESCE(SUM(valor),0) AS total_valor,
              SUM(CASE WHEN tipo_postagem='PAC' THEN 1 ELSE 0 END) AS total_pac,
              SUM(CASE WHEN tipo_postagem='SEDEX' THEN 1 ELSE 0 END) AS total_sedex,
              COALESCE(SUM(CASE WHEN tipo_pagamento='PIX' THEN valor ELSE 0 END),0) AS total_pix,
              COALESCE(SUM(CASE WHEN tipo_pagamento='DINHEIRO' THEN valor ELSE 0 END),0) AS total_dinheiro
            FROM postagens
            WHERE data_postagem=%s AND posto=%s
        """, (data, posto))
        res = cur.fetchone(); conn.close(); return res

    def realizar_fechamento(self, data, posto, func, obs):
        res = self.resumo_dia(data, posto)
        if res['total_postagens']==0:
            return False
        conn = self.conectar(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO fechamento_diario (
              data_fechamento, posto, total_postagens, total_valor,
              total_pac, total_sedex, total_pix, total_dinheiro,
              funcionario, observacoes
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (data_fechamento,posto) DO UPDATE SET
              total_postagens=EXCLUDED.total_postagens,
              total_valor=EXCLUDED.total_valor,
              total_pac=EXCLUDED.total_pac,
              total_sedex=EXCLUDED.total_sedex,
              total_pix=EXCLUDED.total_pix,
              total_dinheiro=EXCLUDED.total_dinheiro,
              funcionario=EXCLUDED.funcionario,
              observacoes=EXCLUDED.observacoes
        """, (data, posto,
              res['total_postagens'], res['total_valor'],
              res['total_pac'], res['total_sedex'],
              res['total_pix'], res['total_dinheiro'],
              func, obs))
        conn.commit(); conn.close(); return True

    def listar_postagens_mes(self, start, end):
        conn = self.conectar(); cur = conn.cursor()
        cur.execute(
            "SELECT * FROM postagens WHERE data_postagem BETWEEN %s AND %s ORDER BY data_postagem",
            (start, end)
        )
        rows = cur.fetchall(); conn.close(); return rows

    def resumo_mes(self, start, end):
        conn = self.conectar(); cur = conn.cursor()
        cur.execute("""
            SELECT
              COUNT(*) AS total_postagens,
              COALESCE(SUM(valor),0) AS total_valor,
              SUM(CASE WHEN tipo_postagem='PAC' THEN 1 ELSE 0 END) AS total_pac,
              SUM(CASE WHEN tipo_postagem='SEDEX' THEN 1 ELSE 0 END) AS total_sedex,
              COALESCE(SUM(CASE WHEN tipo_pagamento='PIX' THEN valor ELSE 0 END),0) AS total_pix,
              COALESCE(SUM(CASE WHEN tipo_pagamento='DINHEIRO' THEN valor ELSE 0 END),0) AS total_dinheiro
            FROM postagens
            WHERE data_postagem BETWEEN %s AND %s
        """, (start, end))
        res = cur.fetchone(); conn.close(); return res

sistema = SistemaPostagem()
sistema.criar_tabelas()

# Authentication routes
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u = request.form['username']; s = request.form['password']
        conn = sistema.conectar(); cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE username=%s", (u,))
        user = cur.fetchone(); conn.close()
        if user and check_password_hash(user['password_hash'], s):
            login_user(User(user['id'],user['username'],user['password_hash'],user['nome_completo'],user['role']))
            return redirect(url_for('index'))
        flash('Credenciais inválidas','error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
@admin_required
def register():
    if request.method=='POST':
        un = request.form['username'].strip()
        pw = request.form['password']
        nc = request.form['nome_completo'].strip()
        role = request.form['role']
        ph = generate_password_hash(pw)
        conn = sistema.conectar(); cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO usuarios (username,password_hash,nome_completo,role) VALUES (%s,%s,%s,%s)",
                (un,ph,nc,role)
            )
            conn.commit(); flash('Usuário criado','success'); return redirect(url_for('index'))
        except psycopg2.IntegrityError:
            flash('Usuário já existe','error')
        finally:
            conn.close()
    return render_template('register.html')

# Application routes
@app.route('/')
@balcao_required
def index():
    hoje = date.today().strftime('%d/%m/%Y'); dbd = date.today().isoformat()
    p = sistema.listar_postagens_dia(dbd)
    r1 = sistema.resumo_dia(dbd,1); r2 = sistema.resumo_dia(dbd,2)
    return render_template('index.html', postagens=p,
                           resumo_posto1=r1, resumo_posto2=r2,
                           data_hoje=hoje, NOME_POSTO=NOME_POSTO)

@app.route('/nova_postagem', methods=['GET','POST'])
@balcao_required
def nova_postagem():
    hoje = date.today().strftime('%Y-%m-%d')
    if request.method=='POST':
        sistema.adicionar_postagem(
            request.form['data_postagem'],
            int(request.form['posto']),
            request.form['nome_remetente'].strip(),
            request.form['codigo_rastreio'].strip().upper(),
            float(request.form['valor']),
            request.form['tipo_postagem'],
            request.form.get('tipo_pagamento'),
            bool(request.form.get('pagamento_pago')),
            request.form.get('data_pagamento'),
            request.form.get('observacoes')
        )
        flash('Postagem adicionada','success')
        return redirect(url_for('index'))
    return render_template('nova_postagem.html', data_hoje=hoje)

@app.route('/pendentes')
@balcao_required
def listar_pendentes():
    pend = sistema.listar_pendentes()
    return render_template('pendentes.html', pendentes=pend, NOME_POSTO=NOME_POSTO)

@app.route('/marcar_pago/<int:id>', methods=['GET','POST'])
@balcao_required
def marcar_pago(id):
    conn = sistema.conectar(); cur = conn.cursor()
    if request.method=='POST':
        cur.execute("""
            UPDATE postagens SET pagamento_pago=TRUE,
              data_pagamento=%s, tipo_pagamento=%s, observacoes=%s
            WHERE id=%s
        """, (request.form['data_pagamento'],request.form['tipo_pagamento'],request.form.get('observacoes'),id))
        conn.commit(); conn.close()
        flash('Pagamento marcado','success')
        return redirect(url_for('listar_pendentes'))
    cur.execute("SELECT * FROM postagens WHERE id=%s",(id,))
    p = cur.fetchone(); conn.close()
    return render_template('marcar_pago.html', postagem=p, NOME_POSTO=NOME_POSTO)

@app.route('/fechamento')
@balcao_required
def fechamento():
    hoje = date.today().strftime('%d/%m/%Y'); db = date.today().isoformat()
    r1 = sistema.resumo_dia(db,1); r2 = sistema.resumo_dia(db,2)
    p1 = sistema.listar_postagens_dia(db,1); p2 = sistema.listar_postagens_dia(db,2)
    return render_template('fechamento.html',
                           resumo_posto1=r1, resumo_posto2=r2,
                           postagens_posto1=p1, postagens_posto2=p2,
                           data_hoje=hoje, NOME_POSTO=NOME_POSTO)

@app.route('/realizar_fechamento', methods=['POST'])
@balcao_required
def realizar_fechamento():
    raw = request.form['data_fechamento']
    dt = datetime.strptime(raw,'%d/%m/%Y').date().isoformat()
    posto = int(request.form['posto'])
    func = request.form['funcionario'].strip()
    obs = request.form.get('observacoes','').strip()
    sucesso = sistema.realizar_fechamento(dt,posto,func,obs)
    if not sucesso:
        flash('Nenhuma postagem para fechar','error')
        return redirect(url_for('fechamento'))
    return redirect(url_for('fechamento'))

@app.route('/relatorio_mensal', methods=['GET','POST'])
@balcao_required
def relatorio_mensal():
    year = date.today().year
    if request.method=='POST':
        m = int(request.form['mes']); y = int(request.form['ano'])
        start = f"{y}-{m:02d}-01"; end = f"{y}-{m:02d}-{monthrange(y,m)[1]:02d}"
        posts = sistema.listar_postagens_mes(start,end)
        res = sistema.resumo_mes(start,end)
        resumo = dict(res)
        return render_template('relatorio_mensal_resultado.html',
                               postagens=posts, resumo=resumo,
                               mes=m, ano=y, NOME_POSTO=NOME_POSTO)
    return render_template('relatorio_mensal.html', current_year=year)

@app.route('/relatorio_mensal/pdf/<int:mes>/<int:ano>')
@balcao_required
def gerar_pdf_relatorio_mensal(mes, ano):
    start = f"{ano}-{mes:02d}-01"; end = f"{ano}-{mes:02d}-{monthrange(ano,mes)[1]:02d}"
    posts = sistema.listar_postagens_mes(start,end)
    res = sistema.resumo_mes(start,end)
    filename = f"relatorio_{ano}_{mes:02d}.pdf"
    pdf = FPDF(); pdf.add_page()
    pdf.set_font('Arial','B',14); pdf.cell(0,10,f"Relatório Mensal {mes:02d}/{ano}",ln=True,align='C')
    pdf.ln(5); pdf.set_font('Arial','',12)
    pdf.cell(0,8,f"Total Postagens: {res['total_postagens']}",ln=True)
    pdf.cell(0,8,f" Valor Total: R$ {res['total_valor']:.2f}",ln=True)
    pdf.ln(5); pdf.set_font('Arial','B',10)
    pdf.cell(30,8,'Data',1); pdf.cell(30,8,'Posto',1)
    pdf.cell(40,8,'Remetente',1); pdf.cell(30,8,'Código',1)
    pdf.cell(20,8,'Valor',1); pdf.ln()
    pdf.set_font('Arial','',9)
    for p in posts:
        pdf.cell(30,8,p['data_postagem'],1)
        pdf.cell(30,8,NOME_POSTO[p['posto']],1)
        pdf.cell(40,8,p['nome_remetente'][:20],1)
        pdf.cell(30,8,p['codigo_rastreio'],1)
        pdf.cell(20,8,f"R$ {p['valor']:.2f}",1)
        pdf.ln()
    pdf.output(filename)
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)))
