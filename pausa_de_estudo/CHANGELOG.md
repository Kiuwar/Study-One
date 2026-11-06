# Histórico de versões

## 1.3.0
- **Bem menos memória:** o app em segundo plano agora é um processo leve (sem tkinter, rede nem
  logging): ~15 MB no Linux, contra ~25 MB antes (e ~38 MB depois de abrir o painel, sem nunca
  devolver). Painel, tela de pausa e resumo abrem como **processos separados** que terminam ao fechar
  e devolvem a memória; a verificação de atualização também roda num processo curto.
- **Não interromper apresentações/jogos:** se o Windows indicar apresentação, jogo ou vídeo em tela
  cheia, a pausa em tela cheia é adiada (avisa por notificação e tenta de novo a cada 1 min).
  "Pausar agora" ignora a checagem. Opção em Configurações.
- **Meta diária de pausas:** progresso no painel e no resumo, e notificação ao atingir.
- **Estudo por matéria:** cadastre matérias em Configurações, escolha a ativa no painel; o histórico
  guarda matéria e tempo de estudo, e o resumo mostra o total por matéria. O CSV ganhou as colunas
  `materia` e `estudo_s`. Bancos antigos são migrados sozinhos.
- O painel **continua aberto durante a pausa** (antes fechava e reabria).
- Segurança: a comunicação entre o app e as janelas usa um token; janelas órfãs (app encerrado)
  fecham sozinhas.
- Windows: o app libera o foco do teclado para a janela que abre (para o Esc funcionar).

## 1.2.0
- **Correção:** depois de "Pausar agora" o painel sumia e o app parecia ter fechado. Agora o painel
  **volta sozinho** ao fim da pausa, já com a nova contagem de estudo.
- **Reiniciar contagem:** novo botão no painel (volta o cronômetro atual ao início).
- A tela de pausa agora fecha com `--sair` (antes o comando ficava esperando a pausa terminar).
- O painel redesenha depois do clique terminar (mais robusto ao suspender, retomar e reiniciar).
- **Exportar CSV** do histórico, no resumo (abre direto no Excel).
- **Diagnóstico:** falhas fatais e erros de janela agora ficam registrados em `erros.log`.
- **Atualização:** aceita o novo nome do repositório (`Kiuwar/Study-One`); sem isso o download seria recusado.
- O CI abre a tela de pausa no Windows e falha se houver erro, para pegar problemas que só
  aparecem lá.

## 1.1.0
- **Atualização pelo app:** botão "Verificar atualização" no painel; baixa o instalador da
  release do GitHub, confere o SHA-256 e instala sozinho. Verifica ao iniciar e a cada 24 h
  (desligável em Configurações).
- **Painel de controle** ao abrir o app (contagem, pausar agora, resumo, configurações, encerrar).
- **Suspender/retomar a contagem** (ex.: durante uma aula ou prova).
- **Pausa longa** a cada N ciclos (`ciclos_pausa_longa` e `minutos_pausa_longa` no `config.json`).
- **Sequência de dias** com pausas feitas, no resumo.
- **Instância única robusta** (mutex + porta livre) e mensagem clara se o app não iniciar.
- `--sair`, `--agora` e `--estatisticas` funcionam com o painel ou o resumo abertos.
- Ícone próprio do app e do instalador; início com o Windows abre sem o painel.

## 1.0.0
- Primeira versão: ciclos configuráveis, tela cheia ou notificação, histórico em SQLite e resumo.
