"""Point d'entrée principal du serveur ctOS exécuté sur la VM serveur."""

from reseau.serveur import ServeurCTOS

if __name__ == "__main__":
    # Instancie et démarre l'écoute TCP sur toutes les interfaces réseau (port 5555)
    ServeurCTOS().start()
