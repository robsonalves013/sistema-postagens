from flask import Flask, render_template, request, redirect, url_for, flash, send_file, after_this_request
import sqlite3
import os
from datetime import datetime, date
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'

DB_FILE = 'postagens.db'
NOME_POSTO = {1: "Shopping_Bolivia", 2: "Hotel_Family"}

class SistemaPostagem:
    def __init__(self, db_name=DB_FILE):
        self.db_name = db_name

    def conectar(self):
        return sqlite3.connect(self.db_name)

    def criar_tabelas(self):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS postagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_postagem DATE NOT NULL,
                posto INTEGER NOT NULL,
                nome_remetente TEXT NOT NULL,
                codigo_rastreio TEXT UNIQUE NOT NULL,
                valor REAL NOT NULL,
                tipo_postagem TEXT NOT NULL CHECK (tipo_postagem IN ('PAC', 'SEDEX')),
                tipo_pagamento TEXT,
                status TEXT DEFAULT 'POSTADO',
                pagamento_pago INTEGER DEFAULT 0,
                data_pagamento DATE,
                observacoes TEXT,
                data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
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
        conn.commit()
        conn.close()

    def adicionar_postagem(self, data_postagem, posto, nome_remetente, codigo_rastreio,
                           valor, tipo_postagem, tipo_pagamento=None, pagamento_pago=0, data_pagamento=None, observacoes=None):
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO postagens (data_postagem, posto, nome_remetente, codigo_rastreio,
                                       valor, tipo_postagem, tipo_pagamento, pagamento_pago, data_pagamento, observacoes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data_postagem, posto, nome_remetente, codigo_rastreio,
                  valor, tipo_postagem, tipo_pagamento, pagamento_pago, data_pagamento, observacoes))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Erro: {e}")
            return False
        finally:
            conn.close()

    def listar_postagens_dia(self, data, posto=None):
        conn = self.conectar()
        cursor = conn.cursor()
        if posto:
            cursor.execute("""
                SELECT id, data_postagem, posto, nome_remetente, codigo_rastreio,
                       valor, tipo_postagem, tipo_pagamento, status, pagamento_pago, data_pagamento, observacoes, data_criacao
                FROM postagens
                WHERE date(data_postagem) = date(?) AND posto = ?
                ORDER BY data_criacao DESC
            """, (data, posto))
        else:
            cursor.execute("""
                SELECT id, data_postagem, posto, nome_remetente, codigo_rastreio,
                       valor, tipo_postagem, tipo_pagamento, status, pagamento_pago, data_pagamento, observacoes, data_criacao
                FROM postagens
                WHERE date(data_postagem) = date(?)
                ORDER BY posto, data_criacao DESC
            """, (data,))
        postagens = cursor.fetchall()
        conn.close()
        return postagens

    def listar_pendentes(self):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, data_postagem, posto, nome_remetente, codigo_rastreio,
                   valor, tipo_postagem, tipo_pagamento, status, pagamento_pago, data_pagamento, observacoes, data_criacao
            FROM postagens
            WHERE pagamento_pago = 0
            ORDER BY data_postagem ASC
        """)
        pendentes = cursor.fetchall()
        conn.close()
        return pendentes

    def resumo_dia(self, data, posto):
        conn = self.conectar()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_postagens,
                COALESCE(SUM(valor), 0) as total_valor,
                SUM(CASE WHEN tipo_postagem = 'PAC' THEN 1 ELSE 0 END) as total_pac,
                SUM(CASE WHEN tipo_postagem = 'SEDEX' THEN 1 ELSE 0 END) as total_sedex,
                COALESCE(SUM(CASE WHEN tipo_pagamento = 'PIX' THEN valor ELSE 0 END), 0) as total_pix,
                COALESCE(SUM(CASE WHEN tipo_pagamento = 'DINHEIRO' THEN valor ELSE 0 END), 0) as total_dinheiro
            FROM postagens
            WHERE date(data_postagem) = date(?) AND posto = ?
        """, (data, posto))
        resultado = cursor.fetchone()
        conn.close()
        return {
            'total_postagens': resultado[0] or 0,
            'total_valor': float(resultado[1] or 0.0),
            'total_pac': resultado[2] or 0,
            'total_sedex': resultado[3] or 0,
            'total_pix': float(resultado[4] or 0.0),
            'total_dinheiro': float(resultado[5] or 0.0),
            'posto': posto
        }

    def realizar_fechamento(self, data, posto, funcionario, observacoes=""):
        resumo = self.resumo_dia(data, posto)
        if resumo['total_postagens'] == 0:
            return False
        conn = self.conectar()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO fechamento_diario
                (data_fechamento, posto, total_postagens, total_valor, total_pac,
                 total_sedex, total_pix, total_dinheiro, funcionario, observacoes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data, posto, resumo['total_postagens'], resumo['total_valor'],
                  resumo['total_pac'], resumo['total_sedex'], resumo['total_pix'],
                  resumo['total_dinheiro'], funcionario, observacoes))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erro no fechamento: {e}")
            return False
        finally:
            conn.close()


def gerar_pdf_fechamento(resumo, postagens):
    pasta_base = 'Fechamento Diario'
    if not os.path.exists(pasta_base):
        os.mkdir(pasta_base)
    pasta_data = os.path.join(pasta_base, NOME_POSTO.get(resumo['posto'], f"Posto{resumo['posto']}"), datetime.today().strftime('%d-%m-%Y'))
    if not os.path.exists(pasta_data):
        os.makedirs(pasta_data)

    nome_posto = NOME_POSTO.get(resumo['posto'], f"Posto{resumo['posto']}")
    nome_arquivo = os.path.join(pasta_data, f"{nome_posto}_{datetime.today().strftime('%d-%m-%Y')}.pdf")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Fechamento Diário dos Postos de Postagem", ln=True, align="C")
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data: {datetime.today().strftime('%d/%m/%Y')}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Resumo do Dia - {nome_posto}", ln=True)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Total de Postagens: {resumo['total_postagens']}", ln=True)
    pdf.cell(0, 10, f"Valor Total: R$ {resumo['total_valor']:.2f}", ln=True)
    pdf.cell(0, 10, f"PAC: {resumo['total_pac']}  |  SEDEX: {resumo['total_sedex']}", ln=True)
    pdf.cell(0, 10, f"PIX: R$ {resumo['total_pix']:.2f}  |  Dinheiro: R$ {resumo['total_dinheiro']:.2f}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Lista de Postagens:", ln=True)
    pdf.set_font("Arial", '', 11)
    for p in postagens:
        pdf.cell(0, 9, f"- {p[3]} ({p[4]}) - R$ {p[5]:.2f} - {p[6]}/{p[7]}", ln=True)
    pdf.output(nome_arquivo)
    return nome_arquivo


sistema = SistemaPostagem()
sistema.criar_tabelas()


@app.route('/')
def index():
    hoje = date.today().strftime('%d/%m/%Y')
    hoje_db = date.today().strftime('%d-%m-%Y')
    postagens_hoje = sistema.listar_postagens_dia(hoje_db)
    resumo_posto1 = sistema.resumo_dia(hoje_db, 1)
    resumo_posto2 = sistema.resumo_dia(hoje_db, 2)
    return render_template('index.html',
                           postagens=postagens_hoje,
                           resumo_posto1=resumo_posto1,
                           resumo_posto2=resumo_posto2,
                           data_hoje=hoje,
                           NOME_POSTO=NOME_POSTO)


@app.route('/nova_postagem', methods=['GET', 'POST'])
def nova_postagem():
    data_hoje = date.today().strftime('%d/%m/%Y')
    data_hoje_db = date.today().strftime('%d-%m-%Y')
    if request.method == 'POST':
        try:
            data_postagem = request.form['data_postagem']
            posto = int(request.form['posto'])
            nome_remetente = request.form['nome_remetente'].strip()
            codigo_rastreio = request.form['codigo_rastreio'].strip().upper()
            valor = float(request.form['valor'])
            tipo_postagem = request.form['tipo_postagem']
            pagamento_pago = int(request.form.get('pagamento_pago', 0))
            data_pagamento = request.form.get('data_pagamento')
            if pagamento_pago == 0:
                data_pagamento = None
                tipo_pagamento = None
            else:
                tipo_pagamento = request.form['tipo_pagamento']
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
    else:
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
    hoje = date.today().strftime('%d/%m/%Y')
    hoje_db = date.today().strftime('%d-%m-%Y')
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
        data_fechamento = request.form['data_fechamento']
        posto = int(request.form['posto'])
        funcionario = request.form['funcionario'].strip()
        observacoes = request.form.get('observacoes', '').strip()
        if not funcionario:
            flash('Nome do funcionário é obrigatório!', 'error')
            return redirect(url_for('fechamento'))
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
