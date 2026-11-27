@echo off
REM Legt eine Verknuepfung "BLUMBOERG" mit Logo auf dem Desktop und im Startmenue an (danach an die Taskleiste anheftbar)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root='%~dp0'; $bat=(Get-ChildItem -LiteralPath $root -Filter 'Start BLUMB*.bat' | Select-Object -First 1).FullName; $ico=Join-Path $root 'app\assets\blumboerg.ico'; $n='BLUMB'+[char]0xD6+'RG'; $sh=New-Object -ComObject WScript.Shell; foreach($dir in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){ $s=$sh.CreateShortcut((Join-Path $dir ($n+'.lnk'))); $s.TargetPath=$bat; $s.WorkingDirectory=$root; $s.IconLocation=$ico+',0'; $s.WindowStyle=7; $s.Description='BLUMBOERG starten'; $s.Save(); Write-Host ('Angelegt: '+(Join-Path $dir ($n+'.lnk'))) }"
echo.
echo Fertig. Das Logo erscheint auf dem Desktop und im Startmenue.
pause
