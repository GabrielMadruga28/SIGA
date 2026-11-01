from flask import (
    Flask, render_template, request, redirect, url_for, jsonify,
    session, Response, send_file, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, time as dtime
import os
import io
import csv
import uuid
import base64
import functools
import numpy as np
import cv2
import reconhecimento_facial as facial

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave-de-desenvolvimento-troque-em-producao")

DB_PATH = os.path.join(os.path.dirname(__file__), "catraca.db")

CAPTURAS_DIR = os.path.join(os.path.dirname(__file__), "static", "capturas")
os.makedirs(CAPTURAS_DIR, exist_ok=True)

# Guarda em memória o último quadro recebido de cada sala (bytes JPEG) e o
# último resultado de reconhecimento, pra alimentar a tela de visualização
# ao vivo no computador. Não precisa ir pro banco — é só um "espelho" do
# que está acontecendo agora, se perder ao reiniciar o servidor não tem
# problema.
ultimo_quadro_sala = {}     # sala_id -> bytes JPEG
ultimo_resultado_sala = {}  # sala_id -> dict com nome/permitido/quando

# credenciais padrão do administrador — criadas automaticamente na primeira
# execução, SE ainda não existir nenhum admin no banco. Troque a senha
# depois de logar pela primeira vez (Usuários > Administrador, ou direto
# no banco) — isso aqui é só pra você conseguir entrar da primeira vez.
ADMIN_PADRAO_USUARIO = "admin"
ADMIN_PADRAO_SENHA = "catraca123"

# autores do projeto (aparecem nas páginas "Licença e Autores" e "Privacidade
# e LGPD"). Preencha o e-mail de cada um pra ele aparecer no cartão; se ficar
# vazio, a linha de contato simplesmente não é exibida.
AUTORES = [
    {"nome": "Gabriel Henrique Madruga Neres", "email": "Gabriel97mneres@gmail.com"},
    {"nome": "João Pedro Batista de Oliveira Santos", "email": ""},
]
INSTITUICAO = "Universidade Evangélica de Goiás (UniEVANGÉLICA)"
ANO_PROJETO = 2026


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            codigo TEXT NOT NULL UNIQUE,
            ativo INTEGER NOT NULL DEFAULT 1,
            hora_inicio TEXT,
            hora_fim TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS registros_acesso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            usuario_id INTEGER,
            nome TEXT,
            data_hora TEXT NOT NULL,
            liberado INTEGER NOT NULL,
            metodo TEXT NOT NULL DEFAULT 'codigo',
            confianca REAL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS salas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sala_permissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sala_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            FOREIGN KEY (sala_id) REFERENCES salas (id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
            UNIQUE (sala_id, usuario_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eventos_sala (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sala_id INTEGER NOT NULL,
            usuario_id INTEGER,
            nome TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            permitido INTEGER NOT NULL,
            confianca REAL,
            visto INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (sala_id) REFERENCES salas (id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    """)
    conn.commit()
    conn.close()

    # migração simples: bancos de versões anteriores sem essas colunas
    conn = get_conn()
    colunas_registros = [c["name"] for c in conn.execute("PRAGMA table_info(registros_acesso)")]
    if "metodo" not in colunas_registros:
        conn.execute("ALTER TABLE registros_acesso ADD COLUMN metodo TEXT NOT NULL DEFAULT 'codigo'")
    if "confianca" not in colunas_registros:
        conn.execute("ALTER TABLE registros_acesso ADD COLUMN confianca REAL")

    colunas_usuarios = [c["name"] for c in conn.execute("PRAGMA table_info(usuarios)")]
    if "hora_inicio" not in colunas_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN hora_inicio TEXT")
    if "hora_fim" not in colunas_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN hora_fim TEXT")
    conn.commit()

    # cria o admin padrão se ainda não existir nenhum
    existe_admin = conn.execute("SELECT COUNT(*) AS n FROM admins").fetchone()["n"]
    if existe_admin == 0:
        conn.execute(
            "INSERT INTO admins (usuario, senha_hash) VALUES (?, ?)",
            (ADMIN_PADRAO_USUARIO, generate_password_hash(ADMIN_PADRAO_SENHA)),
        )
        conn.commit()
    conn.close()


# ---------- AUTENTICAÇÃO ----------

def login_obrigatorio(rota):
    """Decorator: protege uma rota, exigindo que o admin esteja logado.
    Se não estiver, manda pra tela de login."""
    @functools.wraps(rota)
    def rota_protegida(*args, **kwargs):
        if not session.get("admin_logado"):
            return redirect(url_for("login", proximo=request.path))
        return rota(*args, **kwargs)
    return rota_protegida


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")

        conn = get_conn()
        admin = conn.execute("SELECT * FROM admins WHERE usuario = ?", (usuario,)).fetchone()
        conn.close()

        if admin and check_password_hash(admin["senha_hash"], senha):
            session["admin_logado"] = True
            session["admin_usuario"] = admin["usuario"]
            proximo = request.args.get("proximo") or url_for("index")
            return redirect(proximo)

        erro = "Usuário ou senha incorretos."

    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- HORÁRIOS PERMITIDOS ----------

def _parse_hora(texto):
    """Converte 'HH:MM' em um objeto time. Devolve None se vazio/inválido."""
    if not texto:
        return None
    try:
        h, m = texto.split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def dentro_do_horario_permitido(usuario):
    """Verifica se o horário atual está dentro da janela permitida do
    usuário. Se ele não tiver horário configurado (hora_inicio/hora_fim
    vazios), o acesso é permitido a qualquer hora."""
    inicio = _parse_hora(usuario["hora_inicio"])
    fim = _parse_hora(usuario["hora_fim"])

    if inicio is None or fim is None:
        return True  # sem restrição de horário cadastrada

    agora = datetime.now().time()

    if inicio <= fim:
        # janela normal, ex.: 08:00 às 18:00
        return inicio <= agora <= fim
    else:
        # janela que cruza a meia-noite, ex.: 22:00 às 06:00
        return agora >= inicio or agora <= fim


# ---------- PÁGINAS ----------

@app.route("/")
@login_obrigatorio
def index():
    conn = get_conn()
    registros = conn.execute(
        "SELECT * FROM registros_acesso ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    mensagem = request.args.get("mensagem")
    resultado = request.args.get("resultado")
    return render_template("index.html", registros=registros, mensagem=mensagem, resultado=resultado)


@app.route("/usuarios")
@login_obrigatorio
def usuarios():
    conn = get_conn()
    lista = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    conn.close()

    usuarios_com_foto = []
    for u in lista:
        u_dict = dict(u)
        qtd_fotos = len(facial.fotos_usuario(u["id"]))
        u_dict["tem_foto"] = qtd_fotos > 0
        u_dict["qtd_fotos"] = qtd_fotos
        usuarios_com_foto.append(u_dict)

    return render_template("usuarios.html", usuarios=usuarios_com_foto)


# ---------- AÇÕES ----------

@app.route("/cadastrar", methods=["POST"])
@login_obrigatorio
def cadastrar():
    nome = request.form.get("nome", "").strip()
    codigo = request.form.get("codigo", "").strip()
    hora_inicio = request.form.get("hora_inicio", "").strip() or None
    hora_fim = request.form.get("hora_fim", "").strip() or None
    fotos = [f for f in request.files.getlist("fotos") if f and f.filename]

    if nome and codigo:
        conn = get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO usuarios (nome, codigo, ativo, hora_inicio, hora_fim) VALUES (?, ?, 1, ?, ?)",
                (nome, codigo, hora_inicio, hora_fim),
            )
            usuario_id = cursor.lastrowid
            conn.commit()

            for foto in fotos:
                facial.salvar_foto_usuario(usuario_id, foto)

        except sqlite3.IntegrityError:
            pass  # código já existe
        conn.close()

    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/horario", methods=["POST"])
@login_obrigatorio
def atualizar_horario(usuario_id):
    """Atualiza (ou remove) a janela de horário permitido de um usuário
    já cadastrado."""
    hora_inicio = request.form.get("hora_inicio", "").strip() or None
    hora_fim = request.form.get("hora_fim", "").strip() or None

    conn = get_conn()
    conn.execute(
        "UPDATE usuarios SET hora_inicio = ?, hora_fim = ? WHERE id = ?",
        (hora_inicio, hora_fim, usuario_id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/adicionar_foto", methods=["POST"])
@login_obrigatorio
def adicionar_foto(usuario_id):
    fotos = [f for f in request.files.getlist("fotos") if f and f.filename]
    for foto in fotos:
        facial.salvar_foto_usuario(usuario_id, foto)
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/toggle", methods=["POST"])
@login_obrigatorio
def toggle_usuario(usuario_id):
    conn = get_conn()
    conn.execute(
        "UPDATE usuarios SET ativo = 1 - ativo WHERE id = ?", (usuario_id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_usuario(usuario_id):
    conn = get_conn()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("usuarios"))


# ---------- SALAS E MONITORAMENTO AO VIVO ----------

COOLDOWN_ALERTA_SEGUNDOS = 20  # evita logar o mesmo evento a cada quadro


@app.route("/salas")
@login_obrigatorio
def salas():
    conn = get_conn()
    lista = conn.execute("SELECT * FROM salas ORDER BY nome").fetchall()

    salas_info = []
    for s in lista:
        qtd_permitidos = conn.execute(
            "SELECT COUNT(*) AS n FROM sala_permissoes WHERE sala_id = ?", (s["id"],)
        ).fetchone()["n"]
        qtd_alertas = conn.execute(
            "SELECT COUNT(*) AS n FROM eventos_sala WHERE sala_id = ? AND permitido = 0 AND visto = 0",
            (s["id"],),
        ).fetchone()["n"]
        s_dict = dict(s)
        s_dict["qtd_permitidos"] = qtd_permitidos
        s_dict["qtd_alertas"] = qtd_alertas
        salas_info.append(s_dict)

    conn.close()
    return render_template("salas.html", salas=salas_info)


@app.route("/salas/criar", methods=["POST"])
@login_obrigatorio
def criar_sala():
    nome = request.form.get("nome", "").strip()
    if nome:
        conn = get_conn()
        try:
            conn.execute("INSERT INTO salas (nome) VALUES (?)", (nome,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # já existe uma sala com esse nome
        conn.close()
    return redirect(url_for("salas"))


@app.route("/salas/<int:sala_id>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_sala(sala_id):
    conn = get_conn()
    conn.execute("DELETE FROM sala_permissoes WHERE sala_id = ?", (sala_id,))
    conn.execute("DELETE FROM eventos_sala WHERE sala_id = ?", (sala_id,))
    conn.execute("DELETE FROM salas WHERE id = ?", (sala_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("salas"))


@app.route("/salas/<int:sala_id>/permissoes", methods=["GET", "POST"])
@login_obrigatorio
def sala_permissoes(sala_id):
    conn = get_conn()
    sala = conn.execute("SELECT * FROM salas WHERE id = ?", (sala_id,)).fetchone()
    if sala is None:
        conn.close()
        return redirect(url_for("salas"))

    if request.method == "POST":
        ids_permitidos = {int(i) for i in request.form.getlist("usuario_id")}
        conn.execute("DELETE FROM sala_permissoes WHERE sala_id = ?", (sala_id,))
        for usuario_id in ids_permitidos:
            conn.execute(
                "INSERT INTO sala_permissoes (sala_id, usuario_id) VALUES (?, ?)",
                (sala_id, usuario_id),
            )
        conn.commit()
        conn.close()
        return redirect(url_for("salas"))

    todos_usuarios = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    permitidos_ids = {
        row["usuario_id"]
        for row in conn.execute(
            "SELECT usuario_id FROM sala_permissoes WHERE sala_id = ?", (sala_id,)
        ).fetchall()
    }
    conn.close()

    usuarios_marcados = [
        {**dict(u), "permitido": u["id"] in permitidos_ids} for u in todos_usuarios
    ]
    return render_template("sala_permissoes.html", sala=sala, usuarios=usuarios_marcados)


@app.route("/salas/<int:sala_id>/monitorar")
@login_obrigatorio
def sala_monitorar(sala_id):
    conn = get_conn()
    sala = conn.execute("SELECT * FROM salas WHERE id = ?", (sala_id,)).fetchone()
    conn.close()
    if sala is None:
        return redirect(url_for("salas"))
    return render_template("sala_monitorar.html", sala=sala)


def _identidade_evento_recente(conn, sala_id, usuario_id, nome):
    """Verifica se já existe um evento igual (mesma sala + mesma pessoa
    ou mesmo 'desconhecido') registrado há menos de COOLDOWN_ALERTA_SEGUNDOS.
    Evita lotar o histórico/alertas com um evento por quadro da câmera."""
    if usuario_id is not None:
        ultimo = conn.execute(
            """SELECT data_hora FROM eventos_sala
               WHERE sala_id = ? AND usuario_id = ?
               ORDER BY id DESC LIMIT 1""",
            (sala_id, usuario_id),
        ).fetchone()
    else:
        ultimo = conn.execute(
            """SELECT data_hora FROM eventos_sala
               WHERE sala_id = ? AND usuario_id IS NULL AND nome = ?
               ORDER BY id DESC LIMIT 1""",
            (sala_id, nome),
        ).fetchone()

    if ultimo is None:
        return False

    instante = datetime.strptime(ultimo["data_hora"], "%d/%m/%Y %H:%M:%S")
    return (datetime.now() - instante).total_seconds() < COOLDOWN_ALERTA_SEGUNDOS


@app.route("/salas/<int:sala_id>/analisar_frame", methods=["POST"])
@login_obrigatorio
def sala_analisar_frame(sala_id):
    """Recebe um quadro capturado ao vivo da câmera (celular), reconhece
    o rosto, verifica se a pessoa tem permissão pra estar nessa sala e
    registra um evento (liberado ou alerta). Pensado pra ser chamado
    repetidamente (poucos em poucos segundos) enquanto a página de
    monitoramento está aberta."""
    dados = request.get_json(silent=True) or {}
    imagem_base64 = dados.get("imagem", "")

    if "," in imagem_base64:
        imagem_base64 = imagem_base64.split(",", 1)[1]

    try:
        binario = base64.b64decode(imagem_base64)
        buffer = np.frombuffer(binario, dtype=np.uint8)
        imagem = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:
        return jsonify({"status": "erro", "mensagem": "Não foi possível ler a imagem enviada."}), 400

    # guarda o quadro bruto pra tela de visualização ao vivo no computador,
    # independente de ter achado rosto ou não — assim quem está vendo pelo
    # computador acompanha exatamente o que a câmera do celular está vendo
    if imagem is not None:
        ultimo_quadro_sala[sala_id] = binario

    rosto = facial.extrair_rosto_de_imagem(imagem)

    conn = get_conn()
    sala = conn.execute("SELECT * FROM salas WHERE id = ?", (sala_id,)).fetchone()
    if sala is None:
        conn.close()
        return jsonify({"status": "erro", "mensagem": "Sala não encontrada."}), 404

    if rosto is None:
        conn.close()
        ultimo_resultado_sala[sala_id] = {
            "status": "sem_rosto", "nome": None, "permitido": None,
            "quando": datetime.now().strftime("%H:%M:%S"),
        }
        return jsonify({"status": "sem_rosto", "mensagem": "Nenhum rosto no quadro."})

    usuarios_lista = conn.execute("SELECT * FROM usuarios WHERE ativo = 1").fetchall()
    resultado = facial.reconhecer_rosto(rosto, usuarios_lista)

    if resultado["usuario_id"] is None:
        usuario_id = None
        nome = "Pessoa não identificada"
        permitido = False
    else:
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE id = ?", (resultado["usuario_id"],)
        ).fetchone()
        usuario_id = usuario["id"]
        nome = usuario["nome"]
        tem_permissao = conn.execute(
            "SELECT 1 FROM sala_permissoes WHERE sala_id = ? AND usuario_id = ?",
            (sala_id, usuario_id),
        ).fetchone()
        permitido = tem_permissao is not None

    duplicado = _identidade_evento_recente(conn, sala_id, usuario_id, nome)

    if not duplicado:
        conn.execute(
            """INSERT INTO eventos_sala (sala_id, usuario_id, nome, data_hora, permitido, confianca)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                sala_id, usuario_id, nome,
                datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                int(permitido), resultado["confianca"],
            ),
        )
        conn.commit()

    conn.close()

    ultimo_resultado_sala[sala_id] = {
        "status": "ok", "nome": nome, "permitido": permitido,
        "quando": datetime.now().strftime("%H:%M:%S"),
    }

    return jsonify({
        "status": "ok",
        "nome": nome,
        "permitido": permitido,
        "novo_evento": not duplicado,
    })


@app.route("/salas/<int:sala_id>/visualizar")
@login_obrigatorio
def sala_visualizar(sala_id):
    """Tela pra abrir NO COMPUTADOR: mostra o que a câmera do celular está
    vendo (atualiza sozinha, tipo uma câmera de segurança) junto com o
    último resultado do reconhecimento."""
    conn = get_conn()
    sala = conn.execute("SELECT * FROM salas WHERE id = ?", (sala_id,)).fetchone()
    conn.close()
    if sala is None:
        return redirect(url_for("salas"))
    return render_template("sala_visualizar.html", sala=sala)


@app.route("/salas/<int:sala_id>/ultimo_quadro")
@login_obrigatorio
def sala_ultimo_quadro(sala_id):
    """Devolve o último quadro (JPEG) recebido da câmera dessa sala. A
    tela de visualização busca essa imagem de novo a cada 1-2 segundos
    pra parecer uma câmera ao vivo."""
    quadro = ultimo_quadro_sala.get(sala_id)
    if quadro is None:
        # nenhum quadro chegou ainda — devolve uma imagem cinza simples
        # em vez de erro, pra tela de visualização não quebrar
        imagem_vazia = np.full((360, 640, 3), 40, dtype=np.uint8)
        cv2.putText(imagem_vazia, "Aguardando sinal da camera...", (30, 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
        _, buffer = cv2.imencode(".jpg", imagem_vazia)
        quadro = buffer.tobytes()

    return Response(
        quadro,
        mimetype="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.route("/salas/<int:sala_id>/status_ao_vivo")
@login_obrigatorio
def sala_status_ao_vivo(sala_id):
    """JSON com o último resultado de reconhecimento dessa sala — a tela
    de visualização consulta isso junto com a imagem pra mostrar
    'Autorizado: Fulano' / 'ALERTA' embaixo do vídeo."""
    resultado = ultimo_resultado_sala.get(sala_id)
    tem_quadro = sala_id in ultimo_quadro_sala
    return jsonify({"resultado": resultado, "tem_sinal": tem_quadro})


# ---------- ALERTAS ----------

@app.route("/alertas")
@login_obrigatorio
def alertas():
    mostrar_todos = request.args.get("todos") == "1"
    conn = get_conn()
    if mostrar_todos:
        eventos = conn.execute(
            """SELECT eventos_sala.*, salas.nome AS sala_nome
               FROM eventos_sala JOIN salas ON salas.id = eventos_sala.sala_id
               WHERE eventos_sala.permitido = 0
               ORDER BY eventos_sala.id DESC LIMIT 200"""
        ).fetchall()
    else:
        eventos = conn.execute(
            """SELECT eventos_sala.*, salas.nome AS sala_nome
               FROM eventos_sala JOIN salas ON salas.id = eventos_sala.sala_id
               WHERE eventos_sala.permitido = 0 AND eventos_sala.visto = 0
               ORDER BY eventos_sala.id DESC LIMIT 200"""
        ).fetchall()
    conn.close()
    return render_template("alertas.html", eventos=eventos, mostrar_todos=mostrar_todos)


@app.route("/alertas/<int:evento_id>/marcar_visto", methods=["POST"])
@login_obrigatorio
def marcar_alerta_visto(evento_id):
    conn = get_conn()
    conn.execute("UPDATE eventos_sala SET visto = 1 WHERE id = ?", (evento_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("alertas"))


@app.route("/api/alertas/contagem")
@login_obrigatorio
def api_alertas_contagem():
    conn = get_conn()
    contagem = conn.execute(
        "SELECT COUNT(*) AS n FROM eventos_sala WHERE permitido = 0 AND visto = 0"
    ).fetchone()["n"]
    conn.close()
    return jsonify({"contagem": contagem})


@app.route("/simular", methods=["POST"])
@login_obrigatorio
def simular():
    """Simula a leitura de um cartão/código na catraca."""
    codigo = request.form.get("codigo", "").strip()
    conn = get_conn()

    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE codigo = ?", (codigo,)
    ).fetchone()

    mensagem = None
    liberado = bool(usuario and usuario["ativo"] == 1)
    nome = usuario["nome"] if usuario else "Desconhecido"
    usuario_id = usuario["id"] if usuario else None

    if usuario and liberado and not dentro_do_horario_permitido(usuario):
        liberado = False
        mensagem = f"{nome} está fora do horário permitido ({usuario['hora_inicio']}–{usuario['hora_fim']})."

    conn.execute(
        """INSERT INTO registros_acesso (codigo, usuario_id, nome, data_hora, liberado, metodo)
           VALUES (?, ?, ?, ?, ?, 'codigo')""",
        (codigo, usuario_id, nome, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), int(liberado)),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index", mensagem=mensagem, resultado="liberado" if liberado else "bloqueado"))


@app.route("/simular_facial", methods=["POST"])
@login_obrigatorio
def simular_facial():
    """Simula a leitura da catraca por reconhecimento facial: recebe uma
    foto enviada pelo formulário, compara com as fotos dos usuários
    cadastrados e libera se reconhecer alguém ativo e dentro do horário."""
    foto = request.files.get("foto")

    if not foto or not foto.filename:
        return redirect(url_for("index"))

    nome_arquivo = f"{uuid.uuid4().hex}.jpg"
    caminho_captura = os.path.join(CAPTURAS_DIR, nome_arquivo)
    foto.save(caminho_captura)

    conn = get_conn()
    usuarios_lista = conn.execute("SELECT * FROM usuarios").fetchall()

    resultado_facial = facial.reconhecer(caminho_captura, usuarios_lista)

    codigo_registro = "NÃO CADASTRADO"
    mensagem = None

    if not resultado_facial["rosto_detectado"]:
        nome = "Nenhum rosto detectado"
        usuario_id = None
        liberado = False
        mensagem = "Não conseguimos identificar um rosto nessa foto. Tente outra, bem de frente e com boa iluminação."
    elif resultado_facial["usuario_id"] is None:
        nome = "Rosto não reconhecido"
        usuario_id = None
        liberado = False
        mensagem = "Rosto detectado, mas não bate com nenhum usuário cadastrado."
    else:
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE id = ?", (resultado_facial["usuario_id"],)
        ).fetchone()
        usuario_id = usuario["id"]
        nome = usuario["nome"]
        liberado = bool(usuario["ativo"] == 1)
        codigo_registro = usuario["codigo"]

        if not liberado:
            mensagem = f"{nome} foi reconhecido, mas o cadastro está inativo."
        elif not dentro_do_horario_permitido(usuario):
            liberado = False
            mensagem = f"{nome} foi reconhecido, mas está fora do horário permitido ({usuario['hora_inicio']}–{usuario['hora_fim']})."

    conn.execute(
        """INSERT INTO registros_acesso
           (codigo, usuario_id, nome, data_hora, liberado, metodo, confianca)
           VALUES (?, ?, ?, ?, ?, 'facial', ?)""",
        (
            codigo_registro,
            usuario_id,
            nome,
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            int(liberado),
            resultado_facial["confianca"],
        ),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index", mensagem=mensagem, resultado="liberado" if liberado else "bloqueado"))


# ---------- RELATÓRIOS ----------

@app.route("/relatorio/csv")
@login_obrigatorio
def relatorio_csv():
    conn = get_conn()
    registros = conn.execute(
        "SELECT * FROM registros_acesso ORDER BY id DESC"
    ).fetchall()
    conn.close()

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["Data/Hora", "Método", "Código", "Nome", "Status", "Confiança"])
    for r in registros:
        escritor.writerow([
            r["data_hora"],
            "Facial" if r["metodo"] == "facial" else "Código",
            r["codigo"] or "—",
            r["nome"],
            "Liberado" if r["liberado"] else "Negado",
            f"{r['confianca']:.1f}" if r["confianca"] is not None else "—",
        ])

    nome_arquivo = f"relatorio_acessos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@app.route("/relatorio/pdf")
@login_obrigatorio
def relatorio_pdf():
    from fpdf import FPDF

    conn = get_conn()
    registros = conn.execute(
        "SELECT * FROM registros_acesso ORDER BY id DESC"
    ).fetchall()
    conn.close()

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Sotrigo Alimentos - Relatorio de Acessos", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} - {len(registros)} registros", ln=True)
    pdf.ln(4)

    colunas = ["Data/Hora", "Metodo", "Codigo", "Nome", "Status", "Confianca"]
    larguras = [38, 22, 28, 70, 25, 25]

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(5, 90, 57)
    pdf.set_text_color(255, 255, 255)
    for coluna, largura in zip(colunas, larguras):
        pdf.cell(largura, 8, coluna, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(20, 20, 20)
    for i, r in enumerate(registros):
        pdf.set_fill_color(240, 245, 242) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
        linha = [
            r["data_hora"],
            "Facial" if r["metodo"] == "facial" else "Codigo",
            (r["codigo"] or "-"),
            _remover_acentos(r["nome"] or "-"),
            "Liberado" if r["liberado"] else "Negado",
            f"{r['confianca']:.1f}" if r["confianca"] is not None else "-",
        ]
        for valor, largura in zip(linha, larguras):
            pdf.cell(largura, 7, str(valor)[:40], border=1, fill=True)
        pdf.ln()

    nome_arquivo = f"relatorio_acessos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    saida = bytes(pdf.output())
    return Response(
        saida,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


def _remover_acentos(texto):
    """FPDF com fonte padrão (Helvetica) não suporta bem alguns acentos
    fora do latin-1. Essa função troca por uma versão sem acento só pra
    exibição no PDF (o banco de dados continua com o nome original)."""
    substituicoes = str.maketrans(
        "áàãâäéèêëíìîïóòõôöúùûüçÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇ",
        "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC",
    )
    return texto.translate(substituicoes)


# ---------- API (opcional, útil pra testar sem HTML) ----------

@app.route("/api/registros")
@login_obrigatorio
def api_registros():
    conn = get_conn()
    registros = conn.execute(
        "SELECT * FROM registros_acesso ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in registros])



# ---------- PÁGINAS PÚBLICAS (privacidade, licença e autores) ----------
# Ficam sem login de propósito: qualquer pessoa cujo rosto seja cadastrado
# precisa conseguir ler a política antes de dar o consentimento.

@app.route("/privacidade")
def privacidade():
    return render_template("privacidade.html", autores=AUTORES, instituicao=INSTITUICAO)


@app.route("/licenca")
def licenca():
    return render_template(
        "licenca.html", autores=AUTORES, instituicao=INSTITUICAO, ano=ANO_PROJETO
    )


if __name__ == "__main__":
    init_db()
    # ssl_context="adhoc" gera um certificado HTTPS autoassinado na hora —
    # necessário pra o navegador do celular liberar o acesso à câmera
    # quando você abrir pelo IP do computador na rede local (câmera só
    # funciona em conexão segura, HTTPS, exceto em localhost). O navegador
    # vai avisar que o certificado não é confiável; isso é esperado (é
    # autoassinado, só pra teste) — escolha "Avançado" > "Continuar
    # mesmo assim" pra prosseguir.
    app.run(debug=True, host="0.0.0.0", port=5000, ssl_context="adhoc")
