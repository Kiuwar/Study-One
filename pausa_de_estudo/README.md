# Pausa de Estudo

Lembrete de pausas para estudar, para **Windows 10/11**. Roda em segundo plano, conta o
tempo de estudo e avisa com uma **tela cheia futurista** (todos os monitores) ou com uma
**notificação nativa**. Cada aviso vai para um histórico em SQLite.

## Requisitos e dependências

- Windows 10/11 e **Python 3.9+** (instalador do python.org, com "tcl/tk" marcado, que é o padrão).
- **Nenhuma dependência extra.** O `requirements.txt` está vazio de propósito: tudo usa a
  biblioteca padrão (`tkinter`, `sqlite3`, `json`, `ctypes`, `socket`, `queue`).
- Para notificação e atalho o app chama o **PowerShell que já vem no Windows**, só na hora
  de usar. Isso evita bibliotecas como `winotify`, `pystray` e `Pillow`.

## Como rodar

```bat
cd pausa_de_estudo
python main.py
```

`python main.py` mantém um console aberto; para rodar sem console use `pythonw main.py`.
Ao abrir, o app mostra o **painel de controle** (contagem até a próxima pausa, "Pausar
agora", reiniciar ou suspender a contagem, resumo, configurações, atualização e encerrar). Fechar o painel **não** encerra o app: ele segue
em segundo plano. Abrir o app de novo (duplo clique no atalho) traz o painel de volta.
Na primeira execução ele cria o `config.json` ao lado do `main.py` (50 min de estudo, 10 min
de pausa); tudo isso também pode ser mudado pelo painel, em **Configurações**.

| Comando | O que faz |
|---|---|
| `pythonw main.py` | inicia o app, abre o painel e começa a contar o tempo de estudo |
| `pythonw main.py --painel` | abre o painel (ou use o atalho do app) |
| `pythonw main.py --silencioso` | inicia sem abrir o painel (é o que o início com o Windows usa) |
| `pythonw main.py --estatisticas` | abre o resumo (ou dá o duplo clique em `Estatisticas.bat`) |
| `pythonw main.py --agora` | dispara a pausa imediatamente (bom para testar) |
| `pythonw main.py --sair` | encerra o app em execução (ou `Sair.bat`) |

Só existe **uma instância** por vez. Abrir de novo apenas repassa o comando à que já roda.
O app **não tem ícone na bandeja**: o controle é pelo painel (abra o app de novo) ou por esses comandos.

## config.json

```json
{
  "minutos_estudo": 50,
  "minutos_pausa": 10,
  "modo_aviso": "tela_cheia",
  "adiar_minutos": 5,
  "som": true,
  "iniciar_com_windows": false,
  "cor_destaque": "ciano"
}
```

| Chave | Valores |
|---|---|
| `minutos_estudo`, `minutos_pausa`, `adiar_minutos` | número maior que 0 (aceita decimais, ex.: `0.5`) |
| `modo_aviso` | `"tela_cheia"` ou `"notificacao"` |
| `som` | `true` / `false` (som curto nos avisos) |
| `iniciar_com_windows` | `true` cria o atalho na pasta Inicializar; `false` remove |
| `cor_destaque` | `"ciano"`, `"violeta"`, `"verde"` ou `"magenta"` |
| `verificar_atualizacoes` | `true` consulta o GitHub ao iniciar e a cada 24 h (a única conexão de rede do app) |
| `ciclos_pausa_longa` | a cada N ciclos de estudo a pausa é longa (`0` desliga; só neste arquivo) |
| `minutos_pausa_longa` | duração da pausa longa, em minutos (padrão 20) |

O arquivo é relido **no início de cada ciclo**, então a mudança vale a partir do próximo
ciclo, sem reiniciar. Valor inválido volta ao padrão só naquele campo. JSON quebrado mantém
a última configuração válida e **não sobrescreve** o seu arquivo (o erro vai para `erros.log`).

## Como funciona o aviso

**Tela cheia.** Painel escuro levemente translúcido sobre todos os monitores, com o cartão
no monitor principal: anel de contagem, sugestão aleatória e três botões.

- **Iniciar pausa**: começa a contagem regressiva. Ao chegar a 0 a tela fecha sozinha
  (ação `feita`), toca um som curto e o ciclo recomeça.
- **Adiar 5 min**: fecha, grava `adiada` e avisa de novo depois de `adiar_minutos`.
- **Pular**: fecha, grava `pulada` e o ciclo recomeça.
- **Esc** fecha a qualquer momento (grava `pulada`; se a contagem já tinha começado, com o
  tempo realmente descansado).

**Notificação.** Mostra um toast nativo, sem abrir janela. Como não há botões, o app
**assume que a pausa foi feita**: espera `minutos_pausa`, grava `feita` e avisa que é hora
de voltar a estudar.

## Histórico

`historico.db` (SQLite, ao lado do app) guarda: data e hora, duração planejada, duração
real (segundos) e ação (`feita`, `adiada`, `pulada`). A tela de resumo mostra o total do
dia, a sequência de dias e um gráfico dos últimos 7 dias, com botão **Exportar CSV** (`historico.csv`). A conexão é aberta só ao gravar ou ler e fechada em
seguida; nada fica em memória.

## Início automático com o Windows

**Automático (recomendado):** ponha `"iniciar_com_windows": true` no `config.json`. No
início do próximo ciclo o app cria o atalho `Pausa de Estudo.lnk` em
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`. Com `false`, ele remove.

**Manual:**
1. Aperte `Win + R`, digite `shell:startup` e Enter.
2. Clique com o botão direito > Novo > Atalho.
3. Local do item: `"C:\caminho\do\python\pythonw.exe" "C:\caminho\pausa_de_estudo\main.py"`.
4. Nomeie e conclua. Em Propriedades, "Iniciar em" deve ser a pasta do app.

## Instalar no Windows (sem Python)

O GitHub Actions compila o `.exe` num Windows real (workflow `.github/workflows/windows.yml`).
Em **Actions > Windows (.exe e instalador) > Artifacts** baixe `PausaDeEstudo-Windows`:

- `PausaDeEstudo-Setup.exe`: instalador. Instala só para o seu usuário, sem pedir
  administrador, em `%LOCALAPPDATA%\Programs\PausaDeEstudo`, e cria os atalhos no Menu
  Iniciar (app, resumo das pausas e encerrar). Ao terminar, ele abre o painel. Para desinstalar, use "Aplicativos instalados" do Windows.
- `PausaDeEstudo-portatil.zip`: descompacte numa pasta com permissão de escrita e abra
  `PausaDeEstudo.exe`.

Para publicar uma *release* com os dois arquivos, crie uma tag: `git tag v1.0.0 && git push origin v1.0.0`.
O Windows pode exibir o aviso "SmartScreen" porque o `.exe` não é assinado digitalmente:
clique em "Mais informações" > "Executar assim mesmo".

## Atualizar o app

No painel, **Verificar atualização**. Se houver versão nova, o botão vira **Atualizar para vX**: o
app baixa o instalador da release do GitHub, **confere o SHA-256** (recusa se não bater ou se o
checksum faltar), roda o instalador em modo silencioso e volta a abrir sozinho. O app também
verifica ao iniciar e a cada 24 h e avisa com uma notificação (desligue em Configurações).

- Só baixa de `github.com/Kiuwar/Study-One/releases/download/` (e o nome antigo `Kiuwar/New`).
- **Requer que o repositório seja público**: com repositório privado o GitHub responde 404 para
  quem não está logado e o painel mostra "Nenhuma versão pública encontrada".
- Na versão portátil (zip) o botão apenas abre a página de download.
- O instalador não é assinado digitalmente; o SHA-256 garante a integridade do arquivo baixado,
  não a identidade de quem publicou.

### Para publicar uma versão nova
1. Aumente `VERSAO` em `versao.py` e descreva a mudança em `CHANGELOG.md` (seção `## X.Y.Z`).
2. Faça merge na `main`. O workflow compila, testa e publica a release `vX.Y.Z` (cria a tag
   sozinho) com `PausaDeEstudo-Setup.exe`, o `.sha256` e o `.zip`. Crie a tag à mão só se
   preferir (o CI recusa se a tag e `versao.py` divergirem).
3. **Aumente `versao.py` a cada lançamento:** um novo push na `main` com a mesma versão
   reenvia os arquivos da release existente.

## Gerar o .exe manualmente (opcional)

```bat
pip install pyinstaller
pyinstaller --noconsole --onedir --name PausaDeEstudo main.py
```

A pasta `dist\PausaDeEstudo\` contém o `PausaDeEstudo.exe`. O `config.json` e o
`historico.db` ficam **ao lado do .exe**. Prefira `--onedir`: o `--onefile` extrai tudo
para uma pasta temporária a cada abertura, o que é mais lento. Para gerar o instalador,
instale o Inno Setup 6 e rode `iscc instalador.iss` na pasta do app.

## Como medir a memória (meta: < 40 MB)

1. Abra o app (`pythonw main.py`) e deixe uns minutos.
2. `Ctrl + Shift + Esc` > aba **Detalhes**. Procure `pythonw.exe` (ou `PausaDeEstudo.exe`).
3. Clique com o botão direito no cabeçalho das colunas > **Selecionar colunas** > marque
   **Conjunto de trabalho particular** (ou "Memória (conjunto de trabalho privado ativo)").
   Esse é o número a comparar com a meta.
4. Meça em três momentos: **parado** (contando), **com a tela cheia aberta** e **depois de
   fechar**. A tela só existe durante o aviso; ao fechar, o valor deve voltar para perto
   do parado.
5. No modo `notificacao` o `tkinter` nem é carregado. O toast usa um `powershell.exe`
   separado e de curta duração, que não conta para o app.

## Testes

```bat
python -m unittest discover -s testes -v
```

Cobrem config, histórico, espera/comandos e o reagendamento do "Adiar".

## Premissas e limitações (leia)

- **Não foi testado em Windows real.** Foi desenvolvido e testado em Linux: lógica
  (6 testes automáticos), ciclo de ponta a ponta no modo notificação, e a interface
  (tela cheia, Esc, Adiar, contagem completa, estatísticas) sob `tkinter` virtual.
  **Sem teste no Windows:** toast, criação do `.lnk`, detecção de vários monitores,
  `-transparentcolor` e a memória real. Valide esses pontos.
- **Memória:** a meta de 40 MB **não foi medida no Windows**. Em Linux o app parado
  (sem `tkinter`) usou ~17 MB. O `tkinter` e a tela cheia somam mais enquanto abertos.
- **Sem ícone na bandeja** (exigiria `pystray` + `Pillow`). Sem janela flutuante
  permanente: ela deixaria o app na lista "Aplicativos" do Gerenciador de Tarefas e
  quebraria o critério de não sobrar janela. O visual flutuante (halo neon, translucidez,
  janela sem borda arrastável) fica na tela de pausa e no resumo.
- **Toast** depende do Windows PowerShell 5.1 (padrão no Win 10/11) e respeita o
  "Assistente de foco / Não incomodar": se ele estiver ativo, o aviso pode não aparecer.
  Nesse caso o app toca o som e registra o motivo em `erros.log`.
- **Esc na tela cheia** depende do foco do teclado. O app pede o foco ao abrir, mas, se
  outro programa roubá-lo, clique na tela uma vez. Saída de emergência: `pythonw main.py --sair`.
- **Esc** grava `pulada`; a tela cheia fica aberta até uma ação (não fecha sozinha se você
  nunca clicar); no modo notificação a pausa é sempre dada como `feita`.
- `config.json`, `historico.db` e `erros.log` ficam na pasta do app. Se instalar em uma
  pasta protegida (ex.: `Program Files`), mova o app para uma pasta com permissão de escrita.
- Comunicação entre instâncias: mutex do Windows + porta local livre escolhida na hora
  (registrada em `%TEMP%\PausaDeEstudo.porta`), sem porta fixa que possa estar bloqueada.
- Se o app não conseguir iniciar, ele mostra uma mensagem de erro e grava o motivo em `erros.log`.
  O mesmo arquivo recebe falhas fatais e erros de janela; se o app fechar sozinho, abra-o e me envie o conteúdo.
- "Pausar agora" fecha o painel para mostrar a pausa e o reabre ao terminar. Com o painel fechado o app
  continua em segundo plano: abra o app de novo para voltar a ele.
- Hibernação/suspensão do PC pode estender o ciclo em curso pelo tempo em que ficou suspenso.

## Estrutura

| Arquivo | Função |
|---|---|
| `main.py` | ponto de entrada, laço do ciclo, comandos e instância única |
| `config.py` | leitura, validação e gravação do `config.json` |
| `painel.py` | painel de controle (janela principal) e configurações |
| `overlay.py` | tela cheia da pausa (multi-monitor) |
| `gerar_icone.py` / `icone.ico` | ícone do app e do instalador |
| `notificacoes.py` | toast nativo e som curto |
| `historico.py` | gravação e consulta no SQLite |
| `estatisticas.py` | tela de resumo (hoje e 7 dias) |
| `tema.py` | paleta, fontes e desenhos neon reutilizáveis (extra) |
| `sistema.py` | pasta do app, PowerShell, DPI e monitores (extra) |
| `inicializacao.py` | atalho na pasta Inicializar (extra) |
| `atualizador.py` / `versao.py` | verificação, download e instalação de atualizações (extra) |
| `textos.py` | sugestões e mensagens (extra) |
