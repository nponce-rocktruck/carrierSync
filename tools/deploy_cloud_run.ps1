# Despliegue CarrierSync en Google Cloud Run
param(
    [string]$ServiceName = "carriersync",
    [string]$Region = "us-central1",
    [string]$EnvFile = "env.prod.yaml"
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CarrierSync - Despliegue en Cloud Run" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Servicio: $ServiceName" -ForegroundColor Yellow
Write-Host "Region: $Region" -ForegroundColor Yellow
Write-Host "Archivo de variables: $EnvFile" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: No se encontro el archivo $EnvFile" -ForegroundColor Red
    exit 1
}

$envVars = @()
$lines = Get-Content $EnvFile
$currentKey = $null
$currentValue = ""
$inMultiLine = $false

foreach ($line in $lines) {
    $trimmedLine = $line.Trim()
    if ($trimmedLine.StartsWith('#') -or [string]::IsNullOrWhiteSpace($trimmedLine)) { continue }
    if ($trimmedLine -match '^([A-Z_][A-Z0-9_]*):\s*"(.+)"\s*$') {
        $key = $matches[1]
        $value = $matches[2] -replace '"', '\"'
        $envVars += "$key=$value"
        Write-Host "  OK $key" -ForegroundColor Gray
    }
    elseif ($trimmedLine -match '^([A-Z_][A-Z0-9_]*):\s*(.+?)\s*$') {
        $key = $matches[1]
        $value = $matches[2]
        if ($value -match '^\{"' -or $value.Length -gt 500) {
            $currentKey = $key
            $currentValue = $value
            $inMultiLine = $true
        } else {
            $value = $value -replace '"', '\"'
            $envVars += "$key=$value"
            Write-Host "  OK $key" -ForegroundColor Gray
        }
    }
    elseif ($inMultiLine -and $null -ne $currentKey) {
        $currentValue += $line
        if ($trimmedLine.EndsWith('"')) {
            $finalValue = $currentValue -replace '"', '\"' -replace '\n', '' -replace '\r', ''
            $envVars += "$currentKey=$finalValue"
            $currentKey = $null
            $currentValue = ""
            $inMultiLine = $false
        }
    }
}

if ($null -ne $currentKey -and $currentValue) {
    $finalValue = $currentValue -replace '"', '\"' -replace '\n', '' -replace '\r', ''
    $envVars += "$currentKey=$finalValue"
}

$envVarsString = $envVars -join ','
if ([string]::IsNullOrEmpty($envVarsString)) {
    Write-Host "AVISO: No se encontraron variables en $EnvFile" -ForegroundColor Yellow
    exit 1
}

Write-Host "Variables: $($envVars.Count)" -ForegroundColor Green
Write-Host ""

gcloud run deploy $ServiceName `
    --source . `
    --platform managed `
    --region=$Region `
    --allow-unauthenticated `
    --set-env-vars $envVarsString `
    --memory=1Gi `
    --cpu=1 `
    --timeout=300 `
    --max-instances=10 `
    --min-instances=0 `
    --port=8080 `
    --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Despliegue exitoso!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    $url = gcloud run services describe $ServiceName --region=$Region --format='value(status.url)' 2>$null
    if ($url) {
        Write-Host "URL API: $url" -ForegroundColor Yellow
        Write-Host "  POST $url/api/v1/carga-giros" -ForegroundColor Gray
        Write-Host "  GET  $url/api/v1/carga-giros/{job_id}" -ForegroundColor Gray
        Write-Host "  GET  $url/health" -ForegroundColor Gray
    }
} else {
    Write-Host "Error en el despliegue." -ForegroundColor Red
}
