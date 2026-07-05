param (
    [string]$envFile = "C:\projects\Project_BPS\webapp\.env",
    [string]$localBackupDir = "C:\projects\Project_BPS\backups",
    [string]$rcloneRemote = "gdrive:Backup_BPS"
)

# 1. Parse .env file
if (-not (Test-Path $envFile)) {
    Write-Error "File .env tidak ditemukan di $envFile"
    exit 1
}

$envVars = @{}
Get-Content $envFile | Where-Object { $_ -match "^(.*?)=(.*)$" } | ForEach-Object {
    $envVars[$matches[1].Trim()] = $matches[2].Trim()
}

$dbName = $envVars["DB_NAME"]
$dbUser = $envVars["DB_USER"]
$dbPass = $envVars["DB_PASSWORD"]
$dbHost = $envVars["DB_HOST"]
$dbPort = $envVars["DB_PORT"]

# 2. Setup Variables
$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$filename = "backup_${dbName}_${timestamp}.dump"
$localBackupPath = Join-Path $localBackupDir $filename

if (-not (Test-Path $localBackupDir)) {
    New-Item -ItemType Directory -Force -Path $localBackupDir | Out-Null
}

# 3. Execute pg_dump
$env:PGPASSWORD = $dbPass
$pgDumpExe = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

Write-Host "Mulai backup database $dbName ke $localBackupPath..."
& $pgDumpExe -U $dbUser -h $dbHost -p $dbPort -F c -f $localBackupPath $dbName

if ($LASTEXITCODE -ne 0) {
    Write-Error "Backup lokal gagal."
    exit 1
}
Write-Host "Backup lokal berhasil."

# 4. Copy to Google Drive via rclone
# Find rclone.exe in scripts directory
$rcloneExe = Get-ChildItem -Path "C:\projects\Project_BPS\scripts" -Recurse -Filter "rclone.exe" | Select-Object -First 1 | Select-Object -ExpandProperty FullName

if ($rcloneExe) {
    Write-Host "Menemukan rclone di: $rcloneExe"
    Write-Host "Mengupload ke Google Drive ($rcloneRemote)..."
    & $rcloneExe copy $localBackupPath $rcloneRemote
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Upload ke Google Drive berhasil."
        # Hapus file lama di Google Drive (> 14 hari)
        & $rcloneExe delete $rcloneRemote --min-age 14d
        Write-Host "Cleanup file lama di Google Drive selesai."
    } else {
        Write-Error "Gagal upload ke Google Drive. Pastikan kamu sudah setup 'rclone config' dengan nama 'gdrive'."
    }
} else {
    Write-Warning "rclone.exe tidak ditemukan. Lewati proses upload."
}

# 5. Clean up old files in local dir (> 7 days)
Get-ChildItem -Path $localBackupDir -Filter "*.dump" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force
Write-Host "Proses backup selesai."
