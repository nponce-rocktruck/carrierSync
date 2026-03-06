# Elige env y servicio segun ambiente (dev/prod) y llama a deploy_cloud_run.ps1
param(
    [Parameter(Mandatory=$false)]
    [string]$Ambiente = "prod"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

if ([string]::IsNullOrWhiteSpace($Ambiente)) { $Ambiente = "prod" }
if ($Ambiente -eq "production") { $Ambiente = "prod" }

if ($Ambiente -eq "dev") {
    $EnvFile = "env.dev.yaml"
    $ServiceName = "carriersync-dev"
    $Etiqueta = "DESARROLLO"
} elseif ($Ambiente -eq "prod") {
    $EnvFile = "env.prod.yaml"
    $ServiceName = "carriersync"
    $Etiqueta = "PRODUCCION"
    if (-not (Test-Path (Join-Path $rootDir $EnvFile)) -and (Test-Path (Join-Path $rootDir "env.cloud-functions.yaml"))) {
        $EnvFile = "env.cloud-functions.yaml"
        Write-Host "Usando env.cloud-functions.yaml para produccion (compatibilidad)." -ForegroundColor Gray
    }
} else {
    Write-Host "Uso: DESPLEGAR.bat dev  o  DESPLEGAR.bat prod" -ForegroundColor Yellow
    Write-Host "  dev  = desarrollo (env.dev.yaml, servicio carriersync-dev)" -ForegroundColor Gray
    Write-Host "  prod = produccion (env.prod.yaml, servicio carriersync)" -ForegroundColor Gray
    exit 1
}

$envPath = Join-Path $rootDir $EnvFile
if (-not (Test-Path $envPath)) {
    Write-Host "Error: No se encontro $EnvFile" -ForegroundColor Red
    if ($Ambiente -eq "dev") { Write-Host "Copia env.dev.yaml.example a env.dev.yaml" -ForegroundColor Yellow }
    exit 1
}

Set-Location $rootDir
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CarrierSync - Despliegue en Cloud Run - $Etiqueta" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Servicio: $ServiceName" -ForegroundColor Yellow
Write-Host "Archivo:  $EnvFile" -ForegroundColor Yellow
Write-Host ""

& "$scriptDir\deploy_cloud_run.ps1" -ServiceName $ServiceName -Region "us-central1" -EnvFile $EnvFile
