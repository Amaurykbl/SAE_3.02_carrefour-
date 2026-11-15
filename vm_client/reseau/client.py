"""Client réseau TCP asynchrone basé sur QThread pour l'interface PyQt6.

Gère la connexion permanente au serveur ctOS en arrière-plan sans bloquer
le thread principal d'affichage graphique, avec reconnexion automatique.
"""

import json
import socket
import threading
import time
from PyQt6.QtCore import QThread, pyqtSignal
from config import SERVER_IP, SERVER_PORT


class ClientReseau(QThread):
    """Thread d'écoute TCP émettant des signaux PyQt6 vers l'interface graphique.

    Attributes:
        connected (pyqtSignal): Émis lorsque la connexion TCP au serveur réussit.
        disconnected (pyqtSignal): Émis avec le message d'erreur lors d'une coupure.
        response (pyqtSignal): Émis à réception d'une réponse à une requête client.
        event (pyqtSignal): Émis à réception d'un événement diffusé par le serveur.
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal(str)
    response = pyqtSignal(dict)
    event = pyqtSignal(dict)

    def __init__(self):
        """Initialise les paramètres de connexion et les verrous de thread."""
        super().__init__()
        self.host, self.port = SERVER_IP, SERVER_PORT
        self.sock = None
        self._stop = threading.Event()
        # Verrou garantissant qu'un seul thread écrit à la fois sur le socket
        self._send_lock = threading.Lock()

    def run(self):
        """Boucle principale du QThread : maintient la connexion et lit les trames JSON."""
        while not self._stop.is_set():
            try:
                sock = socket.create_connection((self.host, self.port), timeout=4)
                # Repasse en mode bloquant standard une fois la connexion établie
                sock.settimeout(None)
                self.sock = sock
                self.connected.emit()
                buffer = ""
                while not self._stop.is_set():
                    data = sock.recv(4096)
                    if not data:
                        raise ConnectionError("Connexion fermée par le serveur.")
                    buffer += data.decode("utf-8")
                    # Reconstitue les messages complets séparés par '\n'
                    while "\n" in buffer:
                        raw, buffer = buffer.split("\n", 1)
                        if not raw.strip():
                            continue
                        message = json.loads(raw)
                        # Distingue les événements push serveur ('event') des réponses CRUD
                        if "event" in message:
                            self.event.emit(message)
                        else:
                            self.response.emit(message)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                if not self._stop.is_set():
                    self.disconnected.emit(str(exc))
                    # Temporisation avant une nouvelle tentative de reconnexion
                    time.sleep(2)
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except OSError:
                        pass
                    self.sock = None

    def send(self, payload):
        """Sérialise et envoie un dictionnaire JSON au serveur TCP.

        Args:
            payload (dict): Commande à envoyer (ex. {'action': 'INCIDENT_LIST'}).

        Returns:
            bool: True si l'envoi a réussi, False si le socket est déconnecté.
        """
        if not self.sock:
            return False
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            return False

    def stop(self):
        """Demande l'arrêt propre du thread réseau et ferme le socket actif."""
        self._stop.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
