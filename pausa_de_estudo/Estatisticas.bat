@echo off
rem Abre o resumo do historico (inicia o app se nao estiver rodando)
cd /d "%~dp0"
start "" pythonw main.py --estatisticas
