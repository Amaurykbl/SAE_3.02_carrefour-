"""Contrôleur de la fenêtre de simulation 2D du carrefour côté client."""

from PyQt6.QtGui import QColor
from ui.interface_simulation import CtosMainWindow


class MainCarrefour(CtosMainWindow):
    """Fenêtre de simulation locale pilotée par les événements réseau de MainClient.

    Attributes:
        reseau (ClientReseau): Référence vers le client réseau TCP.
    """

    def __init__(self, reseau):
        """Initialise la vue tactique du carrefour et affiche l'état de synchronisation.

        Args:
            reseau (ClientReseau): Instance active de communication avec le serveur.
        """
        super().__init__()
        self.reseau = reseau
        self.texte_phase.setPlainText("Synchronisation ctOS établie. Mode attente.")
        self.texte_phase.setDefaultTextColor(QColor("#22c55e"))
