# Gyroflow Auto - by Paroneto - instalador Windows
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$App = Join-Path $env:LOCALAPPDATA 'GyroflowAuto'
$Bin = Join-Path $App 'bin'

Write-Host '=============================================='
Write-Host '   GYROFLOW AUTO - by Paroneto  (instalador)'
Write-Host '=============================================='
Write-Host ''

# 1) para versão antiga se estiver rodando
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*GyroflowAuto*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2) arquivos do app (config e histórico ficam)
New-Item -ItemType Directory -Force -Path $App, $Bin, (Join-Path $App 'luts') | Out-Null
Get-ChildItem $Src -File | Where-Object { $_.Extension -in '.py', '.pyw', '.ico' } | Copy-Item -Destination $App -Force
Copy-Item (Join-Path $Src 'luts\*.cube') (Join-Path $App 'luts') -Force
Write-Host "OK  Arquivos copiados para: $App"

# 3) Python próprio (via uv, não mexe no sistema)
$Uv = Join-Path $Bin 'uv.exe'
if (-not (Test-Path $Uv)) {
  Write-Host 'Baixando uv (gerenciador de Python)...'
  $env:UV_UNMANAGED_INSTALL = $Bin
  $env:INSTALLER_NO_MODIFY_PATH = '1'
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path $App 'python'
$Venv = Join-Path $App 'venv'
if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
Write-Host 'Preparando Python...'
& $Uv venv $Venv --python 3.12 -q
$Py = Join-Path $Venv 'Scripts\python.exe'
$Pyw = Join-Path $Venv 'Scripts\pythonw.exe'
& $Py -c "import sys, tkinter; print('OK  Python', sys.version.split()[0], '+ janelas')"

# 4) ffmpeg / ffprobe (build oficial BtbN, com NVIDIA/Intel/AMD)
if (-not (Test-Path (Join-Path $Bin 'ffprobe.exe'))) {
  Write-Host 'Baixando ffmpeg (~140 MB, pode demorar)...'
  $zip = Join-Path $env:TEMP 'gfa_ffmpeg.zip'
  $tmp = Join-Path $env:TEMP 'gfa_ffmpeg'
  Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile $zip
  if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
  Expand-Archive $zip -DestinationPath $tmp -Force
  Get-ChildItem $tmp -Recurse -Include ffmpeg.exe, ffprobe.exe | Copy-Item -Destination $Bin -Force
  Remove-Item -Recurse -Force $zip, $tmp
}
Write-Host 'OK  ffmpeg pronto'

# 5) mp4_merge (junta os arquivos que a O4 corta)
$Merge = Join-Path $Bin 'mp4_merge.exe'
if (-not (Test-Path $Merge)) {
  Write-Host 'Baixando mp4_merge...'
  Invoke-WebRequest 'https://github.com/gyroflow/mp4-merge/releases/download/v0.1.11/mp4_merge-windows64.exe' -OutFile $Merge
}
Write-Host 'OK  mp4_merge pronto'

# 6) Gyroflow
$found = & $Py -c "import sys; sys.path.insert(0, r'$App'); import plataforma as P, gyroflow_auto as g; print(P.find_gyroflow(g.load_json(g.CONFIG_FILE, g.DEFAULT_CONFIG)) or '')"
if (-not $found) {
  Write-Host ''
  Write-Host 'Nao achei o Gyroflow. Se ainda nao instalou, instale em gyroflow.xyz/download.'
  Write-Host 'Se ja instalou, escolha o Gyroflow.exe na janela que vai abrir.'
  Start-Process 'https://gyroflow.xyz/download'
  Add-Type -AssemblyName System.Windows.Forms
  $dlg = New-Object System.Windows.Forms.OpenFileDialog
  $dlg.Title = 'Onde está o Gyroflow.exe?'
  $dlg.Filter = 'Gyroflow|Gyroflow.exe;gyroflow.exe|Programas (*.exe)|*.exe'
  if ($dlg.ShowDialog() -eq 'OK') { $found = $dlg.FileName }
}
if ($found) {
  & $Py -c "import sys; sys.path.insert(0, r'$App'); import gyroflow_auto as g; c=g.load_json(g.CONFIG_FILE, g.DEFAULT_CONFIG); c['gyroflow_path']=r'$found'; g.save_json(g.CONFIG_FILE, c)"
  Write-Host "OK  Gyroflow: $found"
} else {
  Write-Host 'ATENCAO: sem Gyroflow o app nao estabiliza. Instale e rode este instalador de novo.'
}

# 7) atalhos na Área de Trabalho e no Menu Iniciar
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))) {
  $lnk = $ws.CreateShortcut((Join-Path $dir 'Gyroflow Auto.lnk'))
  $lnk.TargetPath = $Pyw
  $lnk.Arguments = '"' + (Join-Path $App 'painel.pyw') + '"'
  $lnk.WorkingDirectory = $App
  $lnk.IconLocation = (Join-Path $App 'icone.ico')
  $lnk.Description = 'Gyroflow Auto - by Paroneto'
  $lnk.Save()
}
Write-Host 'OK  Atalho "Gyroflow Auto" criado na Area de Trabalho'

Write-Host ''
Write-Host '=============================================='
Write-Host ' PRONTO! Abrindo o Gyroflow Auto...'
Write-Host ' - Janela aberta = ligado (pode minimizar)'
Write-Host ' - Plugue o cartao da GoPro ou da O4 Pro'
Write-Host ' - Para desligar: feche a janela'
Write-Host '=============================================='
Start-Process $Pyw -ArgumentList ('"' + (Join-Path $App 'painel.pyw') + '"') -WorkingDirectory $App
