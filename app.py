import os
import sqlite3
from datetime import datetime, date
from calendar import monthrange

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, after_this_request, jsonify
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'

DB_FILE = 'postagens.db'
NOME_POSTO = {1: "Shopping_Bolivia", 2: "Hotel_Family"}

@app.template_filter('datetimeformat')
def datetimeformat(value, fmt='%d/%m/%Y'):
    if not value:
        return ''
    if isinstance(value, str):
        for fmt_in in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(value, fmt_in)
                break
            except ValueError:
                continue
        else:
            return value
    else:
        dt = value
    return dt.strftime(fmt)

class SistemaPostagem:
    def __init__(self, db_name=DB_FILE):
        self.db_name = db_name

    def conectar(self):
        return sqlite3.connect(self.db_name)

    def criar_tabelas(self):
        conn = self.conectar(); c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS postagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_postagem DATE NOT NULL,
                posto INTEGER NOT NULL,
                nome_remetente TEXT NOT NULL,
                codigo_rastreio TEXT UNIQUE NOT NULL,
                valor REAL NOT NULL,
                tipo_postagem TEXT NOT NULL CHECK (tipo_postagem IN ('PAC','SEDEX')),
                tipo_pagamento TEXT,
                pagamento_pago INTEGER DEFAULT 0,
                data_pagamento DATE,
                observacoes TEXT,
                data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS fechamento_diario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_fechamento DATE NOT NULL,
                posto INTEGER NOT NULL,
                total_postagens INTEGER NOT NULL,
                total_valor REAL NOT NULL,
                total_pac INTEGER NOT NULL,
                total_sedex INTEGER NOT NULL,
                total_pix REAL NOT NULL,
                total_dinheiro REAL NOT NULL,
                funcionario TEXT NOT NULL,
                observacoes TEXT,
                data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(data_fechamento, posto)
            )
        ''')
        conn.commit(); conn.close()

    def adicionar_postagem(self, dp, posto, nom, cod, val, tp, tpag=None, pago=0, dpag=None, obs=None):
        conn = self.conectar(); c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO postagens
                (data_postagem, posto, nome_remetente, codigo_rastreio,
                 valor, tipo_postagem, tipo_pagamento, pagamento_pago,
                 data_pagamento, observacoes)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (dp, posto, nom, cod, val, tp, tpag, pago, dpag, obs))
            conn.commit(); return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def listar_postagens_dia(self, data, posto=None):
        conn = self.conectar(); c = conn.cursor()
        if posto:
            c.execute("""
                SELECT * FROM postagens
                WHERE date(data_postagem)=date(?) AND posto=?
                ORDER BY data_criacao DESC
            """, (data, posto))
        else:
            c.execute("""
                SELECT * FROM postagens
                WHERE date(data_postagem)=date(?)
                ORDER BY posto,data_criacao DESC
            """, (data,))
        rows = c.fetchall(); conn.close(); return rows

    def listar_pendentes(self):
        conn = self.conectar(); c = conn.cursor()
        c.execute("""
            SELECT * FROM postagens
            WHERE pagamento_pago=0
            ORDER BY data_postagem ASC
        """)
        rows = c.fetchall(); conn.close(); return rows

    def resumo_dia(self, data, posto):
        conn = self.conectar(); c = conn.cursor()
        c.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(valor),0),
                SUM(CASE WHEN tipo_postagem='PAC' THEN 1 ELSE 0 END),
                SUM(CASE WHEN tipo_postagem='SEDEX' THEN 1 ELSE 0 END),
                COALESCE(SUM(CASE WHEN tipo_pagamento='PIX' THEN valor ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN tipo_pagamento='DINHEIRO' THEN valor ELSE 0 END),0)
            FROM postagens
            WHERE date(data_postagem)=date(?) AND posto=?
        """, (data, posto))
        res = c.fetchone(); conn.close()
        return {
            'total_postagens': res[0],
            'total_valor': res[1],
            'total_pac': res[2],
            'total_sedex': res[3],
            'total_pix': res[4],
            'total_dinheiro': res[5],
            'posto': posto
        }

    def realizar_fechamento(self, data, posto, func, obs):
        resumo = self.resumo_dia(data, posto)
        if resumo['total_postagens']==0:
            return False
        conn = self.conectar(); c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO fechamento_diario
            (data_fechamento,posto,total_postagens,total_valor,
             total_pac,total_sedex,total_pix,total_dinheiro,
             funcionario,observacoes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (data, posto,
              resumo['total_postagens'],resumo['total_valor'],
              resumo['total_pac'],resumo['total_sedex'],
              resumo['total_pix'],resumo['total_dinheiro'],
              func, obs))
        conn.commit(); conn.close(); return True

    def listar_postagens_mes(self, inicio, fim):
        conn = self.conectar(); c = conn.cursor()
        c.execute("""
            SELECT * FROM postagens
            WHERE data_postagem BETWEEN ? AND ?
            ORDER BY data_postagem ASC
        """, (inicio, fim))
        rows = c.fetchall(); conn.close(); return rows

    def resumo_mes(self, inicio, fim):
        conn = self.conectar(); c = conn.cursor()
        c.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(valor),0),
                SUM(CASE WHEN tipo_postagem='PAC' THEN 1 ELSE 0 END),
                SUM(CASE WHEN tipo_postagem='SEDEX' THEN 1 ELSE 0 END),
                COALESCE(SUM(CASE WHEN tipo_pagamento='PIX' THEN valor ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN tipo_pagamento='DINHEIRO' THEN valor ELSE 0 END),0)
            FROM postagens
            WHERE data_postagem BETWEEN ? AND ?
        """, (inicio, fim))
        res = c.fetchone(); conn.close(); return res

def gerar_pdf_fechamento(resumo, postagens):
    nome = f'fechamento_{resumo["posto"]}_{resumo["total_postagens"]}.pdf'
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f'Fechamento Posto {resumo["posto"]}', ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 8, f'Total Postagens: {resumo["total_postagens"]}', ln=True)
    pdf.cell(0, 8, f'Valor Total: R$ {resumo["total_valor"]:.2f}', ln=True)
    pdf.cell(0, 8, f'PAC: {resumo["total_pac"]}  SEDEX: {resumo["total_sedex"]}', ln=True)
    pdf.cell(0, 8, f'PIX: R$ {resumo["total_pix"]:.2f}  Dinheiro: R$ {resumo["total_dinheiro"]:.2f}', ln=True)
    pdf.ln(8)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 8, 'Data', 1)
    pdf.cell(40, 8, 'Remetente', 1)
    pdf.cell(40, 8, 'Cód. Rastreio', 1)
    pdf.cell(30, 8, 'Valor', 1)
    pdf.ln()
    pdf.set_font("Arial", '', 9)
    for p in postagens:
        pdf.cell(30, 8, p[1], 1)
        pdf.cell(40, 8, p[3][:20], 1)
        pdf.cell(40, 8, p[4], 1)
        pdf.cell(30, 8, f'R$ {p[5]:.2f}', 1)
        pdf.ln()
    pdf.output(nome)
    return nome

sistema = SistemaPostagem()
sistema.criar_tabelas()

@app.route('/')
def index():
    hoje = date.today().strftime('%d/%m/%Y')
    hoje_db = date.today().strftime('%Y-%m-%d')
    postagens = sistema.listar_postagens_dia(hoje_db)
    resumo_posto1 = sistema.resumo_dia(hoje_db,1)
    resumo_posto2 = sistema.resumo_dia(hoje_db,2)
    return render_template('index.html',
                           postagens=postagens,
                           resumo_posto1=resumo_posto1,
                           resumo_posto2=resumo_posto2,
                           data_hoje=hoje,
                           NOME_POSTO=NOME_POSTO)

@app.route('/api/postagens/<int:posto>')
def api_postagens(posto):
    hoje = date.today().strftime('%Y-%m-%d')
    rows = sistema.listar_postagens_dia(hoje,posto)
    return jsonify(postagens=[{
        'nome_remetente':r[3],
        'tipo_postagem':r[6],
        'valor':r[5],
        'tipo_pagamento':r[7] or 'Pendente',
        'data_postagem':r[1]
    } for r in rows])

@app.route('/nova_postagem', methods=['GET', 'POST'])
def nova_postagem():
    data_hoje = date.today().strftime('%d %m %Y')
    data_hoje_db = date.today().strftime('%Y-%m-%d')
    if request.method == 'POST':
        try:
            data_postagem = request.form['data_postagem']
            posto = int(request.form['posto'])
            nome_remetente = request.form['nome_remetente'].strip()
            codigo_rastreio = request.form['codigo_rastreio'].strip().upper()
            valor = float(request.form['valor'])
            tipo_postagem = request.form['tipo_postagem']
            pagamento_pago = int(request.form.get('pagamento_pago', 0))
            if pagamento_pago == 1:
                data_pagamento = datetime.today().strftime('%d %m %Y')
                tipo_pagamento = request.form.get('tipo_pagamento')
            else:
                data_pagamento = None
                tipo_pagamento = None
            observacoes = request.form.get('observacoes')

            if not nome_remetente or not codigo_rastreio:
                flash('Nome do remetente e código de rastreio são obrigatórios!', 'error')
                return render_template('nova_postagem.html', data_hoje=data_hoje)
            if valor <= 0:
                flash('Valor deve ser maior que zero!', 'error')
                return render_template('nova_postagem.html', data_hoje=data_hoje)
            if posto not in [1, 2]:
                flash('Posto deve ser Shopping Bolivia ou Hotel Family!', 'error')
                return render_template('nova_postagem.html', data_hoje=data_hoje)

            sucesso = sistema.adicionar_postagem(
                data_postagem, posto, nome_remetente, codigo_rastreio,
                valor, tipo_postagem, tipo_pagamento, pagamento_pago, data_pagamento, observacoes
            )
            if sucesso:
                flash(f'Postagem {codigo_rastreio} adicionada com sucesso!', 'success')
                return redirect(url_for('index'))
            else:
                flash(f'Erro: Código {codigo_rastreio} já existe!', 'error')
        except ValueError:
            flash('Erro nos dados informados. Verifique os valores numéricos.', 'error')
        except Exception as e:
            flash(f'Erro inesperado: {str(e)}', 'error')
        return render_template('nova_postagem.html', data_hoje=data_hoje)
    return render_template('nova_postagem.html', data_hoje=data_hoje)

@app.route('/pendentes')
def listar_pendentes():
    pendentes = sistema.listar_pendentes()
    return render_template('pendentes.html', pendentes=pendentes, NOME_POSTO=NOME_POSTO)

@app.route('/marcar_pago/<int:id>', methods=['GET', 'POST'])
def marcar_pago(id):
    if request.method == 'POST':
        data_pagamento = request.form['data_pagamento']
        tipo_pagamento = request.form['tipo_pagamento']
        observacoes = request.form.get('observacoes', '').strip()
        conn = sistema.conectar()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE postagens
            SET pagamento_pago = 1,
                data_pagamento = ?,
                tipo_pagamento = ?,
                observacoes = ?
            WHERE id = ?
        """, (data_pagamento, tipo_pagamento, observacoes, id))
        conn.commit()
        conn.close()
        flash('Pagamento marcado com sucesso!', 'success')
        return redirect(url_for('listar_pendentes'))
    else:
        conn = sistema.conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM postagens WHERE id = ?", (id,))
        postagem = cursor.fetchone()
        conn.close()
        return render_template('marcar_pago.html', postagem=postagem, NOME_POSTO=NOME_POSTO)

@app.route('/fechamento')
def fechamento():
    hoje = date.today().strftime('%d %m %Y')
    hoje_db = date.today().strftime('%Y-%m-%d')
    resumo_posto1 = sistema.resumo_dia(hoje_db, 1)
    resumo_posto2 = sistema.resumo_dia(hoje_db, 2)
    postagens_posto1 = sistema.listar_postagens_dia(hoje_db, 1)
    postagens_posto2 = sistema.listar_postagens_dia(hoje_db, 2)
    return render_template('fechamento.html',
                           resumo_posto1=resumo_posto1,
                           resumo_posto2=resumo_posto2,
                           postagens_posto1=postagens_posto1,
                           postagens_posto2=postagens_posto2,
                           data_hoje=hoje,
                           NOME_POSTO=NOME_POSTO)

@app.route('/realizar_fechamento', methods=['POST'])
def realizar_fechamento():
    try:
        data_fechamento_raw = request.form['data_fechamento']
        posto = int(request.form['posto'])
        funcionario = request.form['funcionario'].strip()
        observacoes = request.form.get('observacoes', '').strip()
        if not funcionario:
            flash('Nome do funcionário é obrigatório!', 'error')
            return redirect(url_for('fechamento'))
        try:
            data_fechamento = datetime.strptime(data_fechamento_raw, '%d %m %Y').strftime('%Y-%m-%d')
        except:
            data_fechamento = data_fechamento_raw

        sucesso = sistema.realizar_fechamento(data_fechamento, posto, funcionario, observacoes)
        if sucesso:
            flash(f'Fechamento do Posto {posto} realizado com sucesso!', 'success')
            resumo = sistema.resumo_dia(data_fechamento, posto)
            postagens = sistema.listar_postagens_dia(data_fechamento, posto)
            nome_pdf = gerar_pdf_fechamento(resumo, postagens)
            @after_this_request
            def remover_arquivo(response):
                try:
                    os.remove(nome_pdf)
                except Exception as e:
                    print(f'Erro ao remover arquivo temporário: {e}')
                return response
            return send_file(nome_pdf, as_attachment=True)
        else:
            flash(f'Não há postagens para fechar no Posto {posto}!', 'error')
            return redirect(url_for('fechamento'))
    except Exception as e:
        flash(f'Erro no fechamento: {str(e)}', 'error')
        return redirect(url_for('fechamento'))

@app.route('/relatorio_mensal', methods=['GET', 'POST'])
def relatorio_mensal():
    current_year = datetime.now().year
    if request.method == 'POST':
        mes = int(request.form['mes'])
        ano = int(request.form['ano'])

        primeiro_dia = f"{ano}-{mes:02d}-01"
        ultimo_dia_num = monthrange(ano, mes)[1]
        ultimo_dia = f"{ano}-{mes:02d}-{ultimo_dia_num:02d}"

        postagens = sistema.listar_postagens_mes(primeiro_dia, ultimo_dia)
        resumo = sistema.resumo_mes(primeiro_dia, ultimo_dia)
        resumo_dict = {
            'total_postagens': resumo[0],
            'total_valor': resumo[1],
            'total_pac': resumo[2],
            'total_sedex': resumo[3],
            'total_pix': resumo[4],
            'total_dinheiro': resumo[5]
        }
        # Passe NOME_POSTO para o template para evitar erro no Jinja
        return render_template('relatorio_mensal_resultado.html',
                               postagens=postagens,
                               resumo=resumo_dict,
                               mes=mes,
                               ano=ano,
                               NOME_POSTO=NOME_POSTO)
    else:
        return render_template('relatorio_mensal.html', current_year=current_year)


@app.route('/relatorio_mensal/pdf/<int:mes>/<int:ano>')
def gerar_pdf_relatorio_mensal(mes, ano):
    primeiro_dia = f"{ano}-{mes:02d}-01"
    ultimo_dia_num = monthrange(ano, mes)[1]
    ultimo_dia = f"{ano}-{mes:02d}-{ultimo_dia_num:02d}"

    postagens = sistema.listar_postagens_mes(primeiro_dia, ultimo_dia)
    resumo = sistema.resumo_mes(primeiro_dia, ultimo_dia)
    resumo_dict = {
        'total_postagens': resumo[0],
        'total_valor': resumo[1],
        'total_pac': resumo[2],
        'total_sedex': resumo[3],
        'total_pix': resumo[4],
        'total_dinheiro': resumo[5]
    }

    nome_pdf = f'relatorio_mensal_{ano}_{mes:02d}.pdf'
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"Relatório Mensal - {mes:02d}/{ano}", ln=True, align="C")
    pdf.set_font("Arial", '', 12)
    pdf.ln(6)
    pdf.cell(0, 8, f"Total de Postagens: {resumo_dict['total_postagens']}", ln=True)
    pdf.cell(0, 8, f"Valor Total: R$ {resumo_dict['total_valor']:.2f}", ln=True)
    pdf.cell(0, 8, f"PAC: {resumo_dict['total_pac']}  SEDEX: {resumo_dict['total_sedex']}", ln=True)
    pdf.cell(0, 8, f"PIX: R$ {resumo_dict['total_pix']:.2f}  Dinheiro: R$ {resumo_dict['total_dinheiro']:.2f}", ln=True)
    pdf.ln(8)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(25, 8, "Data", 1)
    pdf.cell(30, 8, "Posto", 1)
    pdf.cell(35, 8, "Remetente", 1)
    pdf.cell(35, 8, "Cód.Rastreio", 1)
    pdf.cell(20, 8, "Valor", 1)
    pdf.cell(15, 8, "Tipo", 1)
    pdf.cell(25, 8, "Pagamento", 1)
    pdf.ln()
    pdf.set_font("Arial", '', 9)
    for p in postagens:
        pdf.cell(25, 8, p[1] or 'Pendente', 1)
        pdf.cell(30, 8, NOME_POSTO.get(p[2], str(p[2])), 1)
        pdf.cell(35, 8, (p[3] or 'Pendente')[:20], 1)
        pdf.cell(35, 8, p[4] or '', 1)
        pdf.cell(20, 8, f"R$ {p[5]:.2f}", 1)
        pdf.cell(15, 8, p[6] or 'Pendente', 1)
        pdf.cell(25, 8, (p[7] or 'Pendente'), 1)
        pdf.ln()
    pdf.output(nome_pdf)
    return send_file(nome_pdf, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
