"""Point d'entrée principal de l'application cliente PyQt6 exécutée sur la VM client."""

import sys
from PyQt6.QtWidgets import QApplication
from script.main_client import MainClient

if __name__ == "__main__":
    # Initialise la boucle événementielle graphique PyQt6
    app = QApplication(sys.argv)
    window = MainClient()
    window.show()
    sys.exit(app.exec())
