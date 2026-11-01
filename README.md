# SIGA — Sistema de Catraca (simulado) — Sotrigo Alimentos

Projeto de treino: sistema de controle de acesso simulado em software, com
banco de dados de usuários autorizados, painel web de quem passou, e
reconhecimento facial (via upload de foto, já que não há câmera disponível).

## Como rodar

1. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
   (`pyopenssl` é necessário pro servidor rodar com HTTPS, exigido pra
   câmera funcionar pelo celular — ver seção "Salas monitoradas" abaixo)

2. Rode o servidor:
   ```
   python app.py
   ```

3. Abra no navegador:
   ```
   https://localhost:5000
   ```
   (o navegador vai avisar que o certificado não é confiável — normal,
   é autoassinado; clique em "Avançado" > "Continuar mesmo assim")

O banco `catraca.db` (SQLite) é criado automaticamente na primeira execução.

## Login de administrador

Na primeira vez que rodar, o sistema cria um usuário administrador padrão:

- **Usuário:** `admin`
- **Senha:** `catraca123`

Troque essa senha depois de logar (não deixe a padrão em um ambiente real —
ela está em texto aberto no código só pra facilitar o primeiro acesso).
Sem login, nenhuma página do sistema pode ser acessada — todas as rotas
redirecionam pra tela de login.

## Estrutura

```
SIGA/
├── requirements.txt                     # dependências (pip install -r requirements.txt)
├── app.py                              # backend Flask (rotas, lógica, banco, login)
├── reconhecimento_facial.py             # detecção e reconhecimento facial (OpenCV)
├── haarcascade_frontalface_default.xml  # classificador de detecção de rosto (OpenCV)
├── catraca.db                            # criado automaticamente ao rodar
├── templates/
│   ├── base.html                         # layout base (menu, header, botão de sair)
│   ├── login.html                         # tela de login do administrador
│   ├── index.html                         # painel: simular leitura + histórico + relatórios
│   ├── usuarios.html                      # cadastro, horários e gerenciamento de usuários
│   ├── salas.html                          # listagem e criação de salas monitoradas
│   ├── sala_permissoes.html                # quem pode acessar cada sala
│   ├── sala_monitorar.html                 # câmera ao vivo (celular) + análise contínua
│   ├── sala_visualizar.html                # tela pro computador acompanhar a câmera do celular
│   └── alertas.html                        # pessoas identificadas sem permissão
└── static/
    ├── style.css                          # estilo do painel
    ├── logo-sotrigo.jpg                    # logo da marca
    └── rostos/                             # fotos cadastradas (criado automaticamente)
        └── <id_usuario>/
            ├── 1.jpg
            ├── 2.jpg
            └── ...
```

## Como usar

1. Em **Usuários Autorizados**, cadastre uma pessoa com nome + código, e
   envie **de 2 a 5 fotos do rosto** (campo aceita múltiplas fotos de uma
   vez). Quanto mais fotos, em ângulos e iluminação diferentes, mais
   confiável fica o reconhecimento.
2. No **Painel de Acessos**, clique na área "Leitura facial" e envie uma
   foto (pode ser outra foto da mesma pessoa) pra simular a catraca lendo
   o rosto dela.
3. O sistema libera se reconhecer um rosto cadastrado e ativo; bloqueia
   se não reconhecer ninguém, se o cadastro estiver inativo, ou se não
   detectar rosto nenhum na foto.
4. Todo acesso (facial ou por código) fica registrado no histórico, com
   o método usado e — no caso da facial — a "distância" de confiança
   calculada (quanto menor, mais parecido).

## Horários permitidos por usuário

Em **Usuários Autorizados**, cada pessoa pode ter uma janela de horário
(campo "até" no cadastro, ou editável depois direto na tabela). Se
definido, o acesso só é liberado dentro dessa faixa — fora dela, é
bloqueado mesmo que o cartão/rosto seja reconhecido corretamente, com uma
mensagem explicando o motivo. Deixe os campos em branco pra permitir
acesso a qualquer hora (comportamento padrão). Funciona até com faixas
que cruzam a meia-noite (ex.: 22:00 às 06:00, pra turno noturno).

## Relatórios (CSV e PDF)

No **Painel de Acessos**, os botões "CSV" e "PDF" no topo do histórico
exportam **todos** os registros de acesso já feitos (não só os últimos
50 mostrados na tela), prontos pra anexar num relatório ou planilha.

## Salas monitoradas por câmera (celular ao vivo)

Além da catraca (entrada geral), o sistema monitora **salas específicas**
usando a câmera do celular direto pelo navegador — sem precisar instalar
nenhum app.

**Como configurar:**
1. Em **Salas**, cadastre a sala (ex.: "Sala do Servidor").
2. Clique em **Permissões** e marque quem pode estar naquela sala.
3. No **celular**, clique em **Abrir câmera** — aponte a câmera pra
   entrada da sala.
4. No **computador**, clique em **Visualizar** na mesma sala — a tela
   mostra ao vivo o que a câmera do celular está vendo (atualiza
   sozinha, tipo uma câmera de segurança), junto com o último resultado
   do reconhecimento (autorizado ou alerta).

**Como funciona:** a página captura um quadro da câmera a cada 3
segundos e manda pro servidor, que roda o mesmo reconhecimento facial da
catraca e verifica se aquela pessoa tem permissão pra estar ali. Se não
tiver (ou não for reconhecida), gera um **alerta** — visível na aba
**Alertas** do painel, com contador atualizado automaticamente no menu.
O mesmo quadro enviado também fica disponível pra tela de
**Visualizar**, que qualquer outro dispositivo logado (o computador, por
exemplo) pode abrir pra acompanhar a câmera em "tempo quase real"
(atualiza a cada 1,2s — não é streaming de vídeo de verdade, é uma foto
se atualizando sozinha, mas cumpre o papel de acompanhar a sala à
distância).

**Importante — acesso por HTTPS:** o navegador só libera o uso da câmera
em conexão segura (HTTPS) ou em localhost. Como você vai abrir a página pelo
IP do computador no celular (ex.: `https://192.168.0.10:5000`), o
`app.py` já sobe com HTTPS autoassinado (`ssl_context="adhoc"`) — o
navegador vai avisar que o certificado "não é confiável"; isso é
esperado (é autoassinado, só pra teste local), escolha "Avançado" >
"Continuar mesmo assim" / "Acessar mesmo assim" pra prosseguir. Celular
e computador precisam estar na **mesma rede Wi-Fi**.

**Sobre "detectar o corpo inteiro":** o sistema identifica a pessoa pelo
**rosto** (igual à catraca), não pelo corpo. Detecção de silhueta/corpo
inteiro consegue dizer "tem uma pessoa aqui", mas não "quem é essa
pessoa" — pra saber se ela tem permissão, é preciso reconhecer a
identidade, e isso só é confiável pelo rosto com as técnicas disponíveis
aqui. Ver a seção de limitações do reconhecimento facial mais abaixo —
ela vale igualmente pra esse monitoramento de salas.

**Limitação atual:** por enquanto o sistema simula com **1 câmera por
sala** (o celular). O pedido original de "2 câmeras por sala" dá pra
expandir cadastrando a mesma sala apontada por dois dispositivos
diferentes (dois celulares/notebooks abrindo a mesma página de
monitoramento ao mesmo tempo) — a rota `/salas/<id>/analisar_frame` já
aceita quadros de qualquer origem que esteja logada, então múltiplos
dispositivos monitorando a mesma sala já funcionaria sem mudar o
código; só não foi testado com hardware real por não haver um segundo
dispositivo disponível agora.

## Bugs corrigidos nesta revisão

Ao revisar o código, encontrei e corrigi:

1. **A animação de "acesso liberado/bloqueado" nunca aparecia.** A rota
   `/` lia o parâmetro `resultado` da URL mas esquecia de repassar ele
   pro template (`render_template(...)` não incluía `resultado=resultado`).
   Corrigido.
2. **Risco de erro (`UnboundLocalError`)** em `/simular_facial` se o
   formulário fosse enviado sem nenhuma foto selecionada. Agora a rota
   verifica isso antes e simplesmente volta pro painel sem gerar erro.
3. **Reconhecimento facial liberando (quase) qualquer rosto.** Essa era
   a causa raiz do problema relatado ("libera todo mundo na facial, não
   aparece bloqueado no histórico pra quem não é cadastrado"). Ver seção
   abaixo.

## ⚠️ Limitação conhecida do reconhecimento facial (importante pra apresentação)

O sistema usava **LBPH** (Local Binary Patterns Histograms), um algoritmo
clássico de visão computacional — não é uma rede neural. Testei com fotos
reais (uma pessoa cadastrada, mais fotos de duas pessoas diferentes
tentando o acesso) e cheguei a uma conclusão importante:

- Com **1 foto cadastrada** por pessoa, o sistema praticamente liberava
  qualquer rosto — inclusive de pessoas completamente diferentes — porque
  o LBPH não tinha referência suficiente pra diferenciar.
- Depois de corrigido pra aceitar **múltiplas fotos por pessoa** e usar a
  **distância média** entre o rosto testado e todas as fotos cadastradas
  (em vez da distância só até a foto mais parecida), a precisão melhorou
  bastante, mas **ainda não é perfeita**: em teste com dados reais, a
  faixa de confiança de fotos genuínas (38–60) ainda se sobrepõe um
  pouco com a de uma pessoa diferente (57–63). Ou seja, **nenhum valor
  de limiar separa 100% dos casos** com esse método.

**Por que isso acontece:** o LBPH compara textura de pixels, não
características faciais estruturais de verdade. Ele é sensível a
iluminação, ângulo e qualidade da câmera — coisas que variam entre fotos
da mesma pessoa tanto quanto entre pessoas diferentes, especialmente
quando as fotos são tiradas no mesmo ambiente (mesma sala, roupa
parecida, etc., como no caso de teste aqui).

**O que resolveria isso de verdade:** um modelo de reconhecimento facial
baseado em rede neural (embeddings faciais), como os usados pelas
bibliotecas `face_recognition`/`dlib`, `deepface` ou serviços de nuvem
(AWS Rekognition, Azure Face API, etc.). Esses modelos aprendem
características faciais muito mais robustas a variação de luz/ângulo.
Não deu pra usar aqui porque:
- `dlib` não tem pacote pré-compilado pra essa plataforma/versão do
  Python — só compilando do zero, o que é lento e nem sempre funciona
- Modelos prontos como o SFace (OpenCV Zoo) ficam hospedados via Git LFS,
  que não é acessível no ambiente de teste usado aqui

**Isso é, na verdade, um ótimo ponto pra sua apresentação** — mostra que
você entende as limitações da técnica que usou e sabe qual seria o
próximo passo pra evoluir o projeto de verdade (que é justamente o
projeto real da faculdade).

## Ideias para evoluir o projeto (incluindo o projeto real da faculdade)

- Trocar o LBPH por reconhecimento facial baseado em rede neural
  (`face_recognition`, `deepface`, ou uma API de nuvem) — resolve a
  limitação de precisão acima
- Fazer alinhamento de rosto (rotação/normalização) antes de comparar,
  o que ajuda até o LBPH tradicional
- Trocar a simulação por leitura real de RFID/QR Code (Arduino/ESP32)
- Dashboard com gráficos (quantidade de acessos por dia, top usuários)
- Treinar e salvar o modelo de reconhecimento uma vez, em vez de
  retreinar a cada tentativa de acesso
- Permitir trocar a senha do administrador pela própria interface
  (hoje precisa mexer direto no banco)
