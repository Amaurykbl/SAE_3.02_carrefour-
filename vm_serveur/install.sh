#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installation ctOS — VM SERVEUR ==="

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

"${APT[@]}" update
"${APT[@]}" install -y python3

echo
echo "Installation serveur terminée."
echo "Adresse IP de cette VM :"
hostname -I || true
echo
echo "Base de données : $ROOT/bdd/ctos_database.db"
echo "Port TCP : 5555"

if [[ $ROOT_MODE -eq 1 ]]; then
    echo
    echo "Tu es connecté en root : les dépendances sont installées."
    echo "Quitte root avec 'exit', puis démarre le serveur avec :"
    echo "  cd '$ROOT' && python3 server.py"
    exit 0
fi

read -r -p "Démarrer maintenant le serveur ctOS ? [O/n] " REPONSE
if [[ ! "$REPONSE" =~ ^[Nn]$ ]]; then
    cd "$ROOT"
    exec python3 server.py
fi
echo "Pour démarrer plus tard : cd '$ROOT' && python3 server.py"
