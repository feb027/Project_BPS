$taskName = "BPS_Database_Backup"
$scriptPath = "C:\projects\Project_BPS\scripts\backup_db.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Settings $settings -Force

Write-Host "Task Scheduler '$taskName' berhasil dibuat dan akan berjalan setiap jam 2:00 pagi."
