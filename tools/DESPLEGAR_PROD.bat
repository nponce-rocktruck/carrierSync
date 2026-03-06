@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0deploy_por_ambiente.ps1" -Ambiente prod
