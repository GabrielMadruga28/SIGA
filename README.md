# SIGA: Sistema Integrado de Gestão de Acesso

Projeto Integrador do curso de Inteligência Artificial da Universidade Evangélica de Goiás (UniEVANGÉLICA), Anápolis, Goiás.

O SIGA é um sistema web de controle de acesso com reconhecimento facial. Ele registra quem passa pela entrada de um ambiente restrito, bloqueia quem não está autorizado e monitora salas específicas por câmera, gerando alertas quando uma pessoa sem permissão é identificada. O protótipo foi desenvolvido para o cenário de uma empresa de alimentos (Sotrigo Alimentos), mas a lógica vale para qualquer ambiente com acesso controlado.

## Autores

- Gabriel Henrique Madruga Neres (Gabriel97mneres@gmail.com)
- João Pedro Batista de Oliveira Santos

## O que o sistema faz

- **Cadastro de usuários autorizados:** cada pessoa é cadastrada com nome, código e de 2 a 5 fotos do rosto. Quanto mais fotos, em ângulos e iluminações diferentes, mais confiável fica o reconhecimento.
- **Catraca simulada:** como o protótipo não usa câmera na entrada, a leitura facial é simulada pelo envio de uma foto. O sistema libera o acesso se reconhecer um rosto cadastrado e ativo, e bloqueia se não reconhecer ninguém, se o cadastro estiver inativo ou se a foto não tiver nenhum rosto. O acesso por código também funciona.
- **Horários permitidos:** cada usuário pode ter uma janela de horário. Fora dela o acesso é bloqueado mesmo com o rosto reconhecido, e o sistema explica o motivo. Faixas que cruzam a meia-noite, como 22:00 às 06:00, funcionam normalmente.
- **Histórico e relatórios:** todo acesso fica registrado com data, resultado, método e grau de confiança do reconhecimento. O painel exporta o histórico completo em CSV e em PDF.
- **Salas monitoradas:** cada sala tem uma lista de pessoas com permissão. A câmera do celular, aberta pelo navegador, envia um quadro a cada 3 segundos para o servidor, que reconhece o rosto e confere a permissão. Se a pessoa não tiver permissão ou não for reconhecida, o sistema gera um alerta. No computador, a tela de visualização acompanha a sala em tempo quase real.
- **Alertas:** lista as pessoas identificadas sem permissão, com contador atualizado automaticamente no menu.
- **Login de administrador:** todas as telas de gestão exigem login.

## Tecnologias

Python 3, Flask, OpenCV (com o módulo de reconhecimento facial LBPH), NumPy, SQLite, fpdf2 para os relatórios em PDF e pyOpenSSL para o HTTPS local.

## Como executar

1. Baixe o código (botão **Code** e depois **Download ZIP**) e extraia em uma pasta. Se preferir, clone o repositório com o git.
2. Abra o terminal dentro da pasta que contém o arquivo `app.py`.
3. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

   No Windows, se o comando `pip` não for reconhecido, use `py -m pip install -r requirements.txt`.

4. Inicie o servidor:

   ```
   python app.py
   ```

   No Windows, também pode ser `py app.py`.

5. Abra no navegador:

   ```
   https://localhost:5000
   ```

   O navegador avisa que o certificado não é confiável. Isso é esperado, porque o certificado é autoassinado e serve só para testes locais. Escolha **Avançado** e depois **Continuar mesmo assim**. O HTTPS é necessário porque o navegador só libera a câmera do celular em conexão segura. Para usar a câmera de um celular, ele e o computador precisam estar na mesma rede Wi-Fi, e a página deve ser aberta pelo IP do computador, por exemplo `https://192.168.0.10:5000`.

O banco de dados `catraca.db` (SQLite) é criado automaticamente na primeira execução.

## Acesso ao sistema

Na primeira execução o sistema cria um administrador padrão:

- Usuário: `admin`
- Senha: `catraca123`

Essa senha existe apenas para facilitar o primeiro acesso e deve ser trocada em qualquer uso real. As senhas são guardadas no banco apenas como hash.

## Privacidade e LGPD

O SIGA trata dados biométricos, que a Lei nº 13.709/2018 (LGPD) classifica como dados pessoais sensíveis. Por isso o sistema tem uma página própria de política de privacidade, acessível sem login pelo rodapé de qualquer tela ou em `/privacidade`.

A página explica que nenhum rosto deve ser cadastrado sem o consentimento livre, específico e destacado da pessoa, e descreve os dados coletados, a finalidade do tratamento e a base legal. Também trata de armazenamento e segurança, retenção e anonimização, compartilhamento, limitações do reconhecimento facial e direitos do titular (artigo 18 da LGPD). Os pedidos relacionados à privacidade são encaminhados aos autores do projeto.

## Licença e autores

A página `/licenca`, também pública e ligada ao rodapé, tem três abas: Autores e Desenvolvedores, Licença e Termos de Uso e Como Citar.

O SIGA é distribuído no modelo **Source-Available (Avaliação Acadêmica)**. O código pode ser lido, executado e citado para estudo e avaliação, mas não é software livre e continua sendo propriedade dos autores, protegido pela Lei do Software (nº 9.609/1998) e pela Lei de Direitos Autorais (nº 9.610/1998). Há dois níveis de uso:

- **Licença de avaliação acadêmica:** gratuita, para estudo, testes e ensino.
- **Licença comercial:** necessária para qualquer uso com finalidade econômica, como instalar o sistema em uma empresa em operação real, oferecê-lo como produto ou serviço, vendê-lo ou redistribuí-lo. É concedida somente por contrato escrito com os autores, que define escopo, prazo, valor, suporte e responsabilidades.

O nome e o logotipo da Sotrigo Alimentos pertencem à empresa e não fazem parte desta licença. As bibliotecas de terceiros continuam sob as licenças de seus respectivos autores.

## Estrutura do projeto

```
SIGA/
├── app.py                               # servidor Flask: rotas, banco de dados, login
├── reconhecimento_facial.py             # detecção e reconhecimento facial (OpenCV)
├── haarcascade_frontalface_default.xml  # classificador de detecção de rosto
├── requirements.txt                     # dependências
├── templates/
│   ├── base.html                        # layout base (menu e rodapé)
│   ├── login.html                       # login do administrador
│   ├── index.html                       # painel de acessos, histórico e relatórios
│   ├── usuarios.html                    # cadastro e gestão de usuários
│   ├── salas.html                       # cadastro de salas monitoradas
│   ├── sala_permissoes.html             # quem pode estar em cada sala
│   ├── sala_monitorar.html              # câmera do celular com análise contínua
│   ├── sala_visualizar.html             # acompanhamento da sala no computador
│   ├── alertas.html                     # pessoas identificadas sem permissão
│   ├── privacidade.html                 # Privacidade e LGPD
│   └── licenca.html                     # Licença, autores e como citar
└── static/
    ├── style.css                        # estilo do painel
    └── logo-sotrigo.jpg                 # logotipo
```

As pastas `static/rostos` (fotos cadastradas) e `static/capturas` (fotos enviadas na catraca simulada) são criadas automaticamente durante o uso e guardam dados biométricos, por isso não fazem parte do repositório.

## Limitações conhecidas

**Precisão do reconhecimento facial.** O sistema usa o algoritmo LBPH (Local Binary Patterns Histograms), uma técnica clássica de visão computacional que compara a textura da imagem e não aprende características estruturais do rosto como uma rede neural. Com uma única foto por pessoa, o sistema chegava a liberar rostos de pessoas diferentes. Aceitar várias fotos por pessoa e usar a distância média até todas elas melhorou bastante o resultado, mas ainda sobra uma pequena sobreposição: nos testes, a faixa de distância de fotos da própria pessoa (38 a 60) se encontra com a de uma pessoa diferente (57 a 63). Por isso nenhum limiar separa todos os casos. O limiar atual é 58.

**Identificação pelo rosto, não pelo corpo.** O sistema reconhece a pessoa pelo rosto. A detecção de silhueta diria apenas que há uma pessoa na imagem, sem informar quem ela é.

**Uma câmera por sala.** O protótipo simula uma câmera por sala. A rota de análise já aceita quadros de vários dispositivos, mas isso não foi testado com um segundo aparelho.

**Imagens servidas sem login.** As fotos ficam em subpastas de `static`, que o Flask serve sem exigir login para quem conhece o endereço do arquivo. Em uso real, essas imagens devem ficar fora dessa pasta e ser entregues por uma rota protegida.

**Uso local.** O servidor roda no modo de desenvolvimento do Flask com certificado autoassinado, o que serve para teste e demonstração, não para produção.

## Próximos passos

- Trocar o LBPH por reconhecimento facial baseado em redes neurais (embeddings faciais), com bibliotecas como `face_recognition` ou `deepface`, o que resolve a limitação de precisão.
- Alinhar o rosto (rotação e normalização) antes de comparar.
- Treinar e salvar o modelo uma vez, em vez de retreinar a cada tentativa de acesso.
- Substituir a catraca simulada por leitura real de RFID ou QR Code.
- Criar um dashboard com gráficos de acessos por dia e por usuário.
- Permitir a troca da senha do administrador pela própria interface.
- Mover as fotos para fora de `static` e protegê-las com login.
