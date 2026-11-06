# Histórico de versões

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
