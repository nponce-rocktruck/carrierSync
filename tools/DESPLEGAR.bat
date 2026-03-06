@echo off
REM CarrierSync - Despliegue Cloud Run (dev o prod)
REM Uso: DESPLEGAR.bat dev   o   DESPLEGAR.bat prod
set AMB=%1
if "%AMB%"=="" set AMB=prod
powershell -ExecutionPolicy Bypass -File "%~dp0deploy_por_ambiente.ps1" -Ambiente %AMB%
