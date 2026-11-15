#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installation ctOS — VM CLIENT ==="

# Accepte soit root (su -), soit un utilisateur disposant de sudo.
if [[ $EUID -eq 0 ]]; then
    APT=(apt-get)
    ROOT_MODE=1
else
    if ! command -v sudo >/dev/null 2>&1; then
        echo "Erreur : utilise root avec 'su -', ou installe sudo et donne les droits à ton utilisateur."
        exit 1
    fi
    APT=(sudo apt-get)
    ROOT_MODE=0
fi

read -r -p "Adresse IP de la VM serveur : " SERVER_IP
if [[ -z "$SERVER_IP" ]]; then
    echo "Adresse IP obligatoire."
    exit 1
fi

"${APT[@]}" update
"${APT[@]}" install -y python3 python3-pyqt6 python3-pyqt6.qtwebengine libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 libgl1-mesa-dri

cat > "$ROOT/config.py" <<EOF
SERVER_IP = "$SERVER_IP"
SERVER_PORT = 5555
EOF

echo
echo "Installation client terminée."
echo "Le client utilisera le serveur $SERVER_IP:5555."

if [[ $ROOT_MODE -eq 1 ]]; then
    echo
    echo "Tu es connecté en root : les dépendances sont installées."
    echo "Quitte root avec 'exit', puis démarre l'interface depuis ton compte utilisateur :"
    echo "  cd '$ROOT' && QTWEBENGINE_CHROMIUM_FLAGS=\"--disable-gpu --no-sandbox\" QT_QPA_PLATFORM=xcb python3 client.py"
    echo "Ne lance pas l'interface graphique en root."
    exit 0
fi

cd "$ROOT"
unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH
export QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --no-sandbox"
QT_QPA_PLATFORM=xcb exec python3 client.py
