"""Module serveur TCP multithread du système ctOS.

Écoute les connexions clientes sur le port 5555, exécute les opérations demandées
sur la base SQLite et diffuse en temps réel les événements d'urgence.
"""

import json
import socket
import threading
from bdd.gestion_bdd import GestionBDD


class ServeurCTOS:
    """Serveur TCP central hébergeant la logique métier et l'accès à la BDD.

    Attributes:
        host (str): Adresse IP d'écoute du serveur ('0.0.0.0' pour toutes les interfaces).
        port (int): Port TCP d'écoute (5555 par défaut).
        sock (socket.socket | None): Socket principal d'écoute serveur.
        clients (set[socket.socket]): Ensemble des sockets clients actuellement connectés.
        lock (threading.Lock): Verrou protégeant l'accès concurrent à `self.clients`.
        running (threading.Event): Drapeau d'état indiquant si le serveur est actif.
    """

    def __init__(self, host="0.0.0.0", port=5555):
        """Initialise les paramètres réseau et les structures de synchronisation.

        Args:
            host (str): Interface réseau d'écoute. Par défaut '0.0.0.0'.
            port (int): Numéro de port TCP. Par défaut 5555.
        """
        self.host, self.port = host, port
        self.sock = None
        self.clients = set()
        self.lock = threading.Lock()
        self.running = threading.Event()

    def start(self):
        """Initialise la BDD, ouvre le socket TCP et accepte les clients en boucle."""
        GestionBDD.initialiser_bdd()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Autorise la réutilisation immédiate du port après un redémarrage du serveur
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(10)
        self.running.set()
        print(f"[ctOS] Serveur actif sur {self.host}:{self.port}")
        try:
            while self.running.is_set():
                # Bloque jusqu'à l'arrivée d'une nouvelle connexion cliente
                conn, addr = self.sock.accept()
                print(f"[ctOS] Client connecté : {addr[0]}:{addr[1]}")
                with self.lock:
                    self.clients.add(conn)
                # Délègue chaque client à un thread démon dédié pour ne pas bloquer accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
        except OSError:
            if self.running.is_set():
                raise
        finally:
            self.stop()

    def _send(self, conn, payload):
        """Sérialise un dictionnaire en JSON terminé par un saut de ligne et l'envoie.

        Args:
            conn (socket.socket): Socket du client destinataire.
            payload (dict): Données à transmettre au client.
        """
        # Le caractère '\n' sert de délimiteur de fin de trame dans le flux TCP
        conn.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

    def _handle_client(self, conn):
        """Boucle de réception exécutée dans un thread dédié pour un client donné.

        Args:
            conn (socket.socket): Socket actif du client connecté.
        """
        buffer = ""
        try:
            with conn:
                while self.running.is_set():
                    data = conn.recv(4096)
                    if not data:
                        # Un retour vide signifie que le client a fermé proprement la connexion
                        break
                    buffer += data.decode("utf-8")
                    # Découpe chaque message JSON complet délimité par '\n'
                    while "\n" in buffer:
                        raw, buffer = buffer.split("\n", 1)
                        if raw.strip():
                            self._process(conn, json.loads(raw))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[ctOS] Connexion client terminée : {exc}")
        finally:
            # Nettoie la référence du socket client à la déconnexion
            with self.lock:
                self.clients.discard(conn)

    def _process(self, conn, req):
        """Interprète une requête JSON cliente, met à jour la BDD et répond.

        Args:
            conn (socket.socket): Socket du client ayant émis la requête.
            req (dict): Requête décodée contenant au minimum la clé 'action'.
        """
        action = req.get("action")
        try:
            if action == "PING":
                result = {"ok": True, "action": "PONG"}

            elif action == "INCIDENT_CREATE":
                typ, lieu = req.get("type", "").strip(), req.get("lieu", "").strip()
                if not typ or not lieu:
                    raise ValueError("Le type et le lieu sont obligatoires.")
                ident = GestionBDD.ajouter_incident(typ, lieu)
                result = {"ok": True, "action": action, "id": ident}

            elif action in ("INCIDENT_LIST", "INCIDENT_LIST_DB"):
                result = {"ok": True, "action": action, "rows": GestionBDD.lister_incidents()}

            elif action == "INTERVENTION_LIST":
                result = {"ok": True, "action": action, "rows": GestionBDD.lister_interventions()}

            elif action == "INCIDENT_DECIDE":
                ident, decision = int(req.get("id")), req.get("decision")
                if decision == "VALIDER":
                    changed = GestionBDD.valider_incident(ident)
                elif decision == "REFUSER":
                    changed = GestionBDD.refuser_incident(ident)
                else:
                    raise ValueError("Décision inconnue.")
                if not changed:
                    raise ValueError("Incident introuvable ou déjà traité.")
                result = {"ok": True, "action": action, "id": ident, "decision": decision}
                # En cas de validation, déclenche l'ouverture de l'interface véhicule sur les clients
                if decision == "VALIDER":
                    incident = next((row for row in GestionBDD.lister_incidents()
                                     if row["id"] == ident), None)
                    self.broadcast({"event": "GO_VEHICULE", "incident_id": ident,
                                    "incident": incident or {}})

            elif action == "INCIDENT_UPDATE":
                ident = int(req.get("id"))
                typ = req.get("type", "").strip()
                lieu = req.get("lieu", "").strip()
                statut = req.get("statut", "").strip()
                if not typ or not lieu or not statut:
                    raise ValueError("Le type, le lieu et le statut sont obligatoires.")
                changed = GestionBDD.modifier_incident(ident, typ, lieu, statut)
                if not changed:
                    raise ValueError("Incident introuvable.")
                result = {"ok": True, "action": action, "id": ident}
                # Notifie tous les clients connectés de rafraîchir leurs tableaux BDD
                self.broadcast({"event": "BDD_UPDATED"})

            elif action == "INCIDENT_DELETE":
                ident = int(req.get("id"))
                changed = GestionBDD.supprimer_incident(ident)
                if not changed:
                    raise ValueError("Incident introuvable.")
                result = {"ok": True, "action": action, "id": ident}
                self.broadcast({"event": "BDD_UPDATED"})

            elif action == "ARRIVE_CARREFOUR":
                result = {"ok": True, "action": action}
                # L'ambulance est arrivée : bascule la simulation du carrefour en mode urgence
                self.broadcast({"event": "URGENCE"})

            else:
                raise ValueError("Commande inconnue.")

            self._send(conn, result)
        except Exception as exc:
            self._send(conn, {"ok": False, "action": action, "error": str(exc)})

    def broadcast(self, payload):
        """Diffuse un événement JSON à l'ensemble des clients connectés.

        Args:
            payload (dict): Événement à diffuser (ex. {'event': 'URGENCE'}).
        """
        dead = []
        with self.lock:
            clients = list(self.clients)
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        for client in clients:
            try:
                client.sendall(data)
            except OSError:
                dead.append(client)
        # Purge les sockets clients devenus injoignables
        if dead:
            with self.lock:
                for client in dead:
                    self.clients.discard(client)

    def stop(self):
        """Arrête proprement le serveur et ferme tous les sockets ouverts."""
        self.running.clear()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        with self.lock:
            clients = list(self.clients)
            self.clients.clear()
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
                client.close()
            except OSError:
                pass


if __name__ == "__main__":
    ServeurCTOS().start()
