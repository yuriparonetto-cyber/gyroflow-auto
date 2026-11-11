#!/bin/bash
# Gyroflow Auto — by Paroneto — instalador para Mac
# Dois cliques neste arquivo (se o Mac bloquear: botão direito > Abrir).
set -e
cd "$(dirname "$0")"
SRC="$(cd ../arquivos && pwd)"
APP="${GFA_APP_DIR:-$HOME/Library/Application Support/GyroflowAuto}"
DESK="${GFA_DESKTOP:-$HOME/Desktop}"
ARCH="$(uname -m)"

clear 2>/dev/null || true
echo "=============================================="
echo "   GYROFLOW AUTO — by Paroneto  (instalador)"
echo "=============================================="
echo

# 1) Gyroflow
if [ ! -d /Applications/Gyroflow.app ] && [ ! -d "$HOME/Applications/Gyroflow.app" ]; then
  echo "⚠️  O Gyroflow não está instalado em Aplicativos."
  echo "   Vou abrir a página de download. Instale o Gyroflow e depois rode este instalador de novo."
  open "https://gyroflow.xyz/download" || true
  echo; read -n 1 -s -r -p "Aperte qualquer tecla para fechar…"; exit 1
fi
echo "✅ Gyroflow encontrado"

# 2) para versão antiga se estiver rodando
if [ -z "$GFA_NO_OPEN" ]; then
  pkill -f "Gyroflow Auto.app/Contents/MacOS/applet" 2>/dev/null || true
  [ -f "$APP/gyroflow_auto.pid" ] && kill "$(cat "$APP/gyroflow_auto.pid")" 2>/dev/null || true
fi

# 3) arquivos do app (config e histórico ficam)
mkdir -p "$APP/bin" "$APP/luts"
cp "$SRC"/*.py "$SRC"/painel.pyw "$SRC"/app.applescript "$SRC"/icone.icns "$APP/"
cp "$SRC"/luts/*.cube "$APP/luts/"
echo "✅ Arquivos copiados para: $APP"

# 4) Python próprio (via uv, não mexe no sistema)
if [ ! -x "$APP/bin/uv" ]; then
  echo "⬇️  Baixando uv (gerenciador de Python)…"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$APP/bin" INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
fi
export UV_PYTHON_INSTALL_DIR="$APP/python"
rm -rf "$APP/venv"
echo "⬇️  Preparando Python…"
"$APP/bin/uv" venv "$APP/venv" --python 3.12 -q
PY="$APP/venv/bin/python3"
"$PY" -c "import sys; print('✅ Python', sys.version.split()[0])"

# 5) ffmpeg / ffprobe (usa o do Homebrew se já existir)
if [ ! -x "$APP/bin/ffmpeg" ] || [ ! -x "$APP/bin/ffprobe" ]; then
  if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
    ln -sf "$(command -v ffmpeg)" "$APP/bin/ffmpeg"; ln -sf "$(command -v ffprobe)" "$APP/bin/ffprobe"
  else
    A="arm64"; [ "$ARCH" = "x86_64" ] && A="amd64"
    T="$(mktemp -d)"
    for t in ffmpeg ffprobe; do
      echo "⬇️  Baixando $t…"
      curl -fsSL "https://ffmpeg.martin-riedl.de/redirect/latest/macos/$A/release/$t.zip" -o "$T/$t.zip"
      unzip -o -q "$T/$t.zip" -d "$APP/bin"
    done
    rm -rf "$T"
  fi
fi
echo "✅ ffmpeg: $("$APP/bin/ffmpeg" -version | head -1 | cut -c1-40)"

# 6) mp4_merge (junta os arquivos que a O4 corta)
if [ ! -x "$APP/bin/mp4_merge" ]; then
  M="mp4_merge-mac-arm64"; [ "$ARCH" = "x86_64" ] && M="mp4_merge-mac64"
  echo "⬇️  Baixando mp4_merge…"
  curl -fsSL "https://github.com/gyroflow/mp4-merge/releases/download/v0.1.11/$M" -o "$APP/bin/mp4_merge"
  chmod +x "$APP/bin/mp4_merge"
fi
xattr -dr com.apple.quarantine "$APP/bin" 2>/dev/null || true
echo "✅ mp4_merge pronto"

# 7) cria o app "Gyroflow Auto" na Área de Trabalho
echo "🔨 Criando o app…"
T="$(mktemp -d)"
sed "s#__PYTHON__#'$PY'#g" "$APP/app.applescript" > "$T/app.applescript"
osacompile -s -o "$T/Gyroflow Auto.app" "$T/app.applescript"
rm -f "$T/Gyroflow Auto.app/Contents/Resources/Assets.car"
cp "$APP/icone.icns" "$T/Gyroflow Auto.app/Contents/Resources/applet.icns"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$T/Gyroflow Auto.app/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.paroneto.gyroflowauto" "$T/Gyroflow Auto.app/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.paroneto.gyroflowauto" "$T/Gyroflow Auto.app/Contents/Info.plist"
codesign --force -s - "$T/Gyroflow Auto.app" 2>/dev/null || true
rm -rf "$DESK/Gyroflow Auto.app"
mv "$T/Gyroflow Auto.app" "$DESK/"
rm -rf "$T"
touch "$DESK/Gyroflow Auto.app"
echo "✅ App criado: Área de Trabalho > Gyroflow Auto"

echo
echo "=============================================="
echo " PRONTO! Abrindo o Gyroflow Auto…"
echo " • Ícone no Dock com bolinha = ligado"
echo " • Plugue o cartão da GoPro ou da O4 Pro"
echo " • Para desligar: feche o app (⌘Q)"
echo " • Na 1ª vez, aceite o acesso a volumes removíveis"
echo "=============================================="
[ -z "$GFA_NO_OPEN" ] && open "$DESK/Gyroflow Auto.app"
echo; read -t 15 -n 1 -s -r -p "Pode fechar esta janela." || true
