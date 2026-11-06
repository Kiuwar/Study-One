# Histórico de versões

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
