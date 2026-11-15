"""Module d'accès et de persistance SQLite pour le serveur ctOS.

Centralise toutes les opérations CRUD sur les tables `incidents` et
`interventions` stockées dans le fichier `ctos_database.db`.
"""

import datetime
import sqlite3
from pathlib import Path

# Chemin absolu vers le fichier SQLite situé dans le même répertoire que ce script
CHEMIN_DB = Path(__file__).with_name("ctos_database.db")


class GestionBDD:
    """Gestionnaire statique des opérations SQLite exécutées sur la VM serveur."""

    @staticmethod
    def _connexion():
        """Ouvre une connexion SQLite configurée avec accès par nom de colonne.

        Returns:
            sqlite3.Connection: Connexion active avec clés étrangères activées.
        """
        # Timeout de 10s pour éviter les verrouillages lors d'accès concurrents entre threads
        conn = sqlite3.connect(CHEMIN_DB, timeout=10)
        # Permet d'accéder aux résultats sous forme de dictionnaire (row["colonne"])
        conn.row_factory = sqlite3.Row
        # Active l'intégrité référentielle des clés étrangères dans SQLite
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def initialiser_bdd():
        """Crée les tables `incidents` et `interventions` si elles n'existent pas."""
        with GestionBDD._connexion() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type_incident TEXT NOT NULL,
                    lieu TEXT NOT NULL,
                    statut TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interventions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_incident INTEGER,
                    unite_envoyee TEXT,
                    heure TEXT,
                    FOREIGN KEY (id_incident) REFERENCES incidents(id)
                );
            """)

    @staticmethod
    def ajouter_incident(type_incident, lieu):
        """Insère un nouvel incident dans la base avec le statut initial 'EN ATTENTE'.

        Args:
            type_incident (str): Nature de l'incident signalé (ex. 'Accident').
            lieu (str): Localisation ou adresse de l'incident.

        Returns:
            int: Identifiant unique (clé primaire) de l'incident créé.
        """
        with GestionBDD._connexion() as conn:
            cur = conn.execute(
                "INSERT INTO incidents(type_incident, lieu, statut) VALUES (?, ?, ?)",
                (type_incident, lieu, "EN ATTENTE")
            )
            return cur.lastrowid

    @staticmethod
    def valider_incident(id_incident, unite="Ambulance ctOS"):
        """Valide un incident en attente et enregistre l'intervention associée.

        Args:
            id_incident (int): Identifiant de l'incident à valider.
            unite (str): Nom de l'unité d'urgence mobilisée.

        Returns:
            bool: True si l'incident a bien été mis à jour, False sinon.
        """
        with GestionBDD._connexion() as conn:
            # Mise à jour conditionnelle : uniquement si l'incident est encore en attente
            cur = conn.execute(
                "UPDATE incidents SET statut='VALIDÉ' WHERE id=? AND statut='EN ATTENTE'",
                (id_incident,)
            )
            if cur.rowcount:
                # Trace horodatée de l'envoi du véhicule dans la table interventions
                conn.execute(
                    "INSERT INTO interventions(id_incident, unite_envoyee, heure) VALUES (?, ?, ?)",
                    (id_incident, unite, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
            return cur.rowcount > 0

    @staticmethod
    def refuser_incident(id_incident):
        """Passe le statut d'un incident en attente à 'REFUSÉ'.

        Args:
            id_incident (int): Identifiant de l'incident à refuser.

        Returns:
            bool: True si l'incident a été refusé, False s'il était introuvable ou déjà traité.
        """
        with GestionBDD._connexion() as conn:
            cur = conn.execute(
                "UPDATE incidents SET statut='REFUSÉ' WHERE id=? AND statut='EN ATTENTE'",
                (id_incident,)
            )
            return cur.rowcount > 0

    @staticmethod
    def lister_incidents():
        """Récupère l'ensemble des incidents triés du plus récent au plus ancien.

        Returns:
            list[dict]: Liste de dictionnaires représentant chaque ligne de `incidents`.
        """
        with GestionBDD._connexion() as conn:
            rows = conn.execute(
                "SELECT id, type_incident, lieu, statut FROM incidents ORDER BY id DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def lister_interventions():
        """Récupère l'historique des interventions enrichi avec les infos d'incident.

        Returns:
            list[dict]: Liste des interventions jointes aux détails de l'incident associé.
        """
        with GestionBDD._connexion() as conn:
            # LEFT JOIN + COALESCE pour conserver l'historique même si l'incident lié est supprimé
            rows = conn.execute("""
                SELECT i.id, i.id_incident, i.unite_envoyee, i.heure,
                       COALESCE(x.type_incident, 'Incident supprimé') AS type_incident,
                       COALESCE(x.lieu, '') AS lieu
                FROM interventions i
                LEFT JOIN incidents x ON x.id = i.id_incident
                ORDER BY i.id DESC
            """).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def modifier_incident(id_incident, type_incident, lieu, statut):
        """Met à jour les champs d'un incident existant depuis la console opérateur.

        Args:
            id_incident (int): Identifiant de l'incident à modifier.
            type_incident (str): Nouveau libellé du type d'incident.
            lieu (str): Nouvelle localisation de l'incident.
            statut (str): Nouveau statut ('EN ATTENTE', 'VALIDÉ' ou 'REFUSÉ').

        Returns:
            bool: True si une ligne a été modifiée, False si l'ID n'existe pas.
        """
        with GestionBDD._connexion() as conn:
            cur = conn.execute(
                """UPDATE incidents
                   SET type_incident=?, lieu=?, statut=?
                   WHERE id=?""",
                (type_incident, lieu, statut, id_incident)
            )
            return cur.rowcount > 0

    @staticmethod
    def supprimer_incident(id_incident):
        """Supprime définitivement un incident ainsi que ses interventions liées.

        Args:
            id_incident (int): Identifiant de l'incident à supprimer.

        Returns:
            bool: True si l'incident a été supprimé, False sinon.
        """
        with GestionBDD._connexion() as conn:
            # Suppression préalable dans interventions pour respecter la contrainte FOREIGN KEY
            conn.execute("DELETE FROM interventions WHERE id_incident=?", (id_incident,))
            cur = conn.execute("DELETE FROM incidents WHERE id=?", (id_incident,))
            return cur.rowcount > 0
