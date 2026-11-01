"""
Módulo de reconhecimento facial do sistema de catraca.

Usa OpenCV:
- Haar Cascade para DETECTAR o rosto na foto (achar onde está o rosto)
- LBPH (Local Binary Patterns Histograms) para RECONHECER de quem é o rosto,
  comparando com as fotos cadastradas dos usuários autorizados.

Cada usuário pode ter VÁRIAS fotos cadastradas (recomendado: 2 a 5, em
ângulos/iluminação diferentes). Isso é importante: com uma foto só, o LBPH
não tem referência suficiente pra diferenciar rostos parecidos, e acaba
"reconhecendo" pessoas que não deveria (falso positivo). Com várias fotos
da mesma pessoa, o modelo aprende a variação natural do rosto dela e fica
bem mais rigoroso pra rejeitar rostos diferentes.

É treinado "na hora" (a cada tentativa de acesso), lendo as fotos salvas em
static/rostos/<usuario_id>/. Isso é simples e ótimo para fins didáticos; em
um sistema de produção real, o modelo seria treinado uma vez e salvo em disco.
"""
import os
import cv2
import numpy as np

BASE_DIR = os.path.dirname(__file__)
ROSTOS_DIR = os.path.join(BASE_DIR, "static", "rostos")
os.makedirs(ROSTOS_DIR, exist_ok=True)

_cascade_path = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
face_detector = cv2.CascadeClassifier(_cascade_path)

TAMANHO_PADRAO = (200, 200)

# Limiar da distância MÉDIA (não da mínima — ver _distancia_media abaixo).
# Calibrado empiricamente: nos testes reais, rostos genuínos ficaram na
# faixa de ~38 a 60, e uma pessoa diferente ficou na faixa de ~57 a 63.
# Ou seja, AINDA HÁ SOBREPOSIÇÃO nessa faixa — não existe limiar perfeito
# com LBPH e poucas fotos por pessoa. Isso é uma limitação conhecida do
# método, documentada no README.
LIMIAR_CONFIANCA = 58


def extrair_rosto_de_imagem(imagem):
    """Recebe uma imagem já carregada (array BGR do OpenCV) e devolve o
    maior rosto encontrado nela, em escala de cinza e redimensionado.
    Devolve None se nenhum rosto for encontrado.

    Usado tanto por extrair_rosto() (fotos do disco) quanto pela análise
    ao vivo da câmera (frames que chegam direto em memória, sem precisar
    salvar em disco a cada quadro — importante pra não deixar a análise
    contínua lenta)."""
    if imagem is None:
        return None

    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    rostos = face_detector.detectMultiScale(
        cinza, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )

    if len(rostos) == 0:
        return None

    x, y, w, h = max(rostos, key=lambda r: r[2] * r[3])
    rosto = cinza[y:y + h, x:x + w]
    rosto = cv2.resize(rosto, TAMANHO_PADRAO)
    return rosto


def extrair_rosto(caminho_imagem):
    """Lê uma imagem do disco e extrai o maior rosto nela (ver
    extrair_rosto_de_imagem). Devolve None se não abrir o arquivo ou não
    achar nenhum rosto."""
    imagem = cv2.imread(caminho_imagem)
    return extrair_rosto_de_imagem(imagem)


def _pasta_usuario(usuario_id):
    pasta = os.path.join(ROSTOS_DIR, str(usuario_id))
    os.makedirs(pasta, exist_ok=True)
    return pasta


def salvar_foto_usuario(usuario_id, arquivo_upload):
    """Salva uma nova foto do usuário (pode chamar várias vezes pra
    cadastrar várias fotos da mesma pessoa). Cada foto vira um arquivo
    numerado dentro de static/rostos/<usuario_id>/."""
    pasta = _pasta_usuario(usuario_id)
    proximo_numero = len(os.listdir(pasta)) + 1
    caminho = os.path.join(pasta, f"{proximo_numero}.jpg")
    arquivo_upload.save(caminho)
    return caminho


def fotos_usuario(usuario_id):
    """Lista os caminhos de todas as fotos cadastradas de um usuário."""
    pasta = os.path.join(ROSTOS_DIR, str(usuario_id))
    if not os.path.isdir(pasta):
        return []
    arquivos = sorted(os.listdir(pasta))
    return [os.path.join(pasta, f) for f in arquivos]


def caminho_foto_usuario(usuario_id):
    """Devolve a primeira foto cadastrada do usuário (usada como miniatura
    no painel), ou None se não tiver nenhuma."""
    fotos = fotos_usuario(usuario_id)
    return fotos[0] if fotos else None


def _distancia_media(rosto_teste, rostos_referencia):
    """Compara o rosto de teste contra CADA foto de referência
    individualmente e devolve a distância MÉDIA entre elas.

    Isso é mais robusto do que treinar o LBPH com todas as fotos de uma vez
    e pegar o "vizinho mais próximo" (comportamento padrão do
    reconhecedor.predict): com poucas fotos, o vizinho mais próximo pode
    dar uma distância enganosamente baixa por coincidência, mesmo sendo
    outra pessoa. A média de todas as comparações é mais difícil de
    "enganar" por sorte."""
    distancias = []
    for referencia in rostos_referencia:
        reconhecedor = cv2.face.LBPHFaceRecognizer_create()
        reconhecedor.train([referencia], np.array([0]))
        _, confianca = reconhecedor.predict(rosto_teste)
        distancias.append(confianca)
    return float(np.mean(distancias))


def reconhecer(caminho_imagem_teste, usuarios):
    """
    Compara a foto de teste (a "captura da catraca") com TODAS as fotos
    de TODOS os usuários cadastrados que têm foto.

    usuarios: lista de linhas do banco (precisa ter 'id', 'nome', 'ativo')

    Retorna um dicionário com o resultado:
    {
        "rosto_detectado": bool,
        "usuario_id": int | None,
        "confianca": float | None,   # menor = mais parecido
    }
    """
    rosto_teste = extrair_rosto(caminho_imagem_teste)
    return reconhecer_rosto(rosto_teste, usuarios)


def reconhecer_rosto(rosto_teste, usuarios):
    """Igual a reconhecer(), mas recebe o rosto já extraído (array), em
    vez de um caminho de arquivo. Usado pela análise ao vivo da câmera,
    onde os quadros chegam em memória e não vale a pena salvar cada um
    em disco só pra reabrir de novo."""
    if rosto_teste is None:
        return {"rosto_detectado": False, "usuario_id": None, "confianca": None}

    candidatos = []  # (usuario_id, distancia_media)

    for usuario in usuarios:
        rostos_referencia = [
            extrair_rosto(foto) for foto in fotos_usuario(usuario["id"])
        ]
        rostos_referencia = [r for r in rostos_referencia if r is not None]
        if not rostos_referencia:
            continue
        distancia = _distancia_media(rosto_teste, rostos_referencia)
        candidatos.append((usuario["id"], distancia))

    if not candidatos:
        # ninguém tem foto cadastrada ainda pra comparar
        return {"rosto_detectado": True, "usuario_id": None, "confianca": None}

    usuario_id, melhor_distancia = min(candidatos, key=lambda c: c[1])

    if melhor_distancia <= LIMIAR_CONFIANCA:
        return {"rosto_detectado": True, "usuario_id": usuario_id, "confianca": melhor_distancia}

    return {"rosto_detectado": True, "usuario_id": None, "confianca": melhor_distancia}
