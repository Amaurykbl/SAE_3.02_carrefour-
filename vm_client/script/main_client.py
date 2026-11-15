"""Console opérateur principale ctOS (PyQt6) sur la VM client.

Permet de signaler, valider, refuser, modifier et supprimer des incidents à distance
sur le serveur, et coordonne l'ouverture des vues véhicule et carrefour.
"""

import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QFrame, QDialog, QFormLayout, QComboBox,
    QDialogButtonBox
)
from reseau.client import ClientReseau
from script.main_vehicule import MainVehicule
from script.main_carrefour import MainCarrefour


class EditIncidentDialog(QDialog):
    """Boîte de dialogue modale permettant d'éditer un incident de la BDD serveur.

    Attributes:
        type_edit (QLineEdit): Champ d'édition du type d'incident.
        lieu_edit (QLineEdit): Champ d'édition de la localisation.
        statut_combo (QComboBox): Liste déroulante du statut de l'incident.
    """

    def __init__(self, ident, type_incident, lieu, statut, parent=None):
        """Construit le formulaire pré-rempli avec les valeurs actuelles de la ligne.

        Args:
            ident (int): Identifiant de l'incident en base.
            type_incident (str): Type actuel de l'incident.
            lieu (str): Localisation actuelle de l'incident.
            statut (str): Statut actuel ('EN ATTENTE', 'VALIDÉ' ou 'REFUSÉ').
            parent (QWidget | None): Fenêtre parente de la boîte de dialogue.
        """
        super().__init__(parent)
        self.setWindowTitle(f"Modifier l'incident #{ident}")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)

        self.type_edit = QLineEdit(type_incident)
        self.lieu_edit = QLineEdit(lieu)
        self.statut_combo = QComboBox()
        self.statut_combo.addItems(["EN ATTENTE", "VALIDÉ", "REFUSÉ"])
        idx = self.statut_combo.findText(statut)
        if idx >= 0:
            self.statut_combo.setCurrentIndex(idx)

        layout.addRow("Type d'incident :", self.type_edit)
        layout.addRow("Lieu :", self.lieu_edit)
        layout.addRow("Statut :", self.statut_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class MainClient(QMainWindow):
    """Fenêtre principale de l'opérateur ctOS connectée au serveur TCP distant.

    Attributes:
        reseau (ClientReseau): Thread réseau gérant la communication TCP JSON.
        vehicule (MainVehicule | None): Fenêtre GPS du véhicule d'urgence actif.
        carrefour (MainCarrefour | None): Fenêtre de simulation 2D du carrefour.
    """

    def __init__(self):
        """Initialise l'interface graphique, connecte les signaux réseau et démarre le polling."""
        super().__init__()
        self.setWindowTitle("ctOS — Console opérateur")
        self.resize(1120, 720)

        # Connexion des signaux émis par le thread réseau aux slots graphiques
        self.reseau = ClientReseau()
        self.reseau.connected.connect(self.on_connected)
        self.reseau.disconnected.connect(self.on_disconnected)
        self.reseau.response.connect(self.on_response)
        self.reseau.event.connect(self.on_event)

        self.vehicule = None
        self.carrefour = None
        self._pending_refresh = False
        self._build_ui()

        # Démarre le thread réseau en arrière-plan
        self.reseau.start()

        # Rafraîchissement périodique de la liste des incidents toutes les 5 secondes
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_incidents)
        self.refresh_timer.start(5000)

    def _build_ui(self):
        """Construit l'arborescence des widgets PyQt6 et applique le thème sombre ctOS."""
        root = QWidget()
        layout = QVBoxLayout(root)

        # En-tête supérieur avec titre et voyant d'état de connexion TCP
        header = QHBoxLayout()
        title = QLabel("ctOS")
        title.setStyleSheet("font-size:32px;font-weight:800;color:#00bfff;")
        self.status = QLabel("● Connexion au serveur…")
        self.status.setStyleSheet("color:#ffb020;font-weight:bold;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        layout.addLayout(header)

        subtitle = QLabel("CONSOLE OPÉRATEUR — GESTION CENTRALISÉE DES INCIDENTS")
        subtitle.setStyleSheet("color:#82909c;letter-spacing:2px;")
        layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- ONGLET 1 : SIGNALEMENT ET VALIDATION DES INCIDENTS ---
        incidents_tab = QWidget()
        il = QVBoxLayout(incidents_tab)
        form = QFrame()
        form.setObjectName("panel")
        fl = QHBoxLayout(form)
        self.type_input = QLineEdit()
        self.type_input.setPlaceholderText("Type d'incident (ex. Accident)")
        self.place_input = QLineEdit()
        self.place_input.setPlaceholderText("Lieu de l'incident")
        add = QPushButton("＋ SIGNALER")
        add.clicked.connect(self.create_incident)
        fl.addWidget(self.type_input, 1)
        fl.addWidget(self.place_input, 1)
        fl.addWidget(add)
        il.addWidget(form)

        self.incidents = QTableWidget(0, 4)
        self.incidents.setHorizontalHeaderLabels(["ID", "TYPE", "LOCALISATION", "STATUT"])
        self._style_table(self.incidents)
        il.addWidget(self.incidents)

        actions = QHBoxLayout()
        self.validate_btn = QPushButton("✓ VALIDER ET ENVOYER LE VÉHICULE")
        self.validate_btn.clicked.connect(lambda: self.decide("VALIDER"))
        self.reject_btn = QPushButton("✕ REFUSER")
        self.reject_btn.clicked.connect(lambda: self.decide("REFUSER"))
        actions.addWidget(self.validate_btn)
        actions.addWidget(self.reject_btn)
        il.addLayout(actions)
        self.tabs.addTab(incidents_tab, "Incidents")

        # --- ONGLET 2 : CONSULTATION ET ÉDITION DISTANTE DE LA BDD SERVEUR ---
        db_tab = QWidget()
        dl = QVBoxLayout(db_tab)
        db_note = QLabel("Données consultées et modifiées à distance depuis la base SQLite hébergée sur la VM SERVEUR.")
        db_note.setStyleSheet("color:#8b9aa6;padding:8px;")
        dl.addWidget(db_note)

        self.db_tabs = QTabWidget()
        self.incident_db = QTableWidget(0, 4)
        self.incident_db.setHorizontalHeaderLabels(["ID", "TYPE", "LIEU", "STATUT"])
        # Double-clic sur une ligne pour ouvrir rapidement la fenêtre d'édition
        self.incident_db.cellDoubleClicked.connect(lambda *_: self.edit_incident_db())

        self.intervention_db = QTableWidget(0, 6)
        self.intervention_db.setHorizontalHeaderLabels(["ID", "ID INCIDENT", "UNITÉ", "HEURE", "INCIDENT", "LIEU"])
        self._style_table(self.incident_db)
        self._style_table(self.intervention_db)
        self.db_tabs.addTab(self.incident_db, "Table incidents")
        self.db_tabs.addTab(self.intervention_db, "Table interventions")
        dl.addWidget(self.db_tabs)

        db_actions = QHBoxLayout()
        refresh = QPushButton("↻ ACTUALISER LES DONNÉES")
        refresh.clicked.connect(self.refresh_database)
        edit_btn = QPushButton("✎ MODIFIER L'INCIDENT")
        edit_btn.clicked.connect(self.edit_incident_db)
        delete_btn = QPushButton("🗑 SUPPRIMER L'INCIDENT")
        delete_btn.setStyleSheet("background:#b91c1c;")
        delete_btn.clicked.connect(self.delete_incident_db)
        db_actions.addWidget(refresh)
        db_actions.addWidget(edit_btn)
        db_actions.addWidget(delete_btn)
        dl.addLayout(db_actions)
        self.tabs.addTab(db_tab, "Base de données")

        self.setCentralWidget(root)
        # Feuille de style QSS globale (noir profond + alternance bleu foncé lisible)
        self.setStyleSheet("""
            QMainWindow,QWidget,QDialog {background:#080c10;color:#d8dee4;font-family:Arial;font-size:14px;}
            QTabWidget::pane {border:1px solid #26323c;background:#10161c;}
            QTabBar::tab {background:#151e26;color:#cbd5e1;padding:12px 22px;margin-right:3px;}
            QTabBar::tab:selected {background:#075071;color:#ffffff;}
            QFrame#panel {background:#10161c;border:1px solid #26323c;border-radius:8px;padding:8px;}
            QLineEdit,QComboBox {background:#080c10;border:1px solid #303c47;border-radius:6px;padding:10px;color:#ffffff;}
            QComboBox QAbstractItemView {background:#0d2233;color:#ffffff;selection-background-color:#075071;selection-color:#ffffff;}
            QTableWidget {
                background-color:#10161c;
                alternate-background-color:#0d2233;
                color:#e6f1f8;
                gridline-color:#1f3344;
                border:1px solid #26323c;
                selection-background-color:#075071;
                selection-color:#ffffff;
            }
            QTableWidget::item {
                padding:6px;
                color:#e6f1f8;
            }
            QTableWidget::item:selected {
                background-color:#075071;
                color:#ffffff;
            }
            QHeaderView::section {
                background-color:#132230;
                color:#9bc2d9;
                padding:9px;
                border:0;
                border-bottom:1px solid #26323c;
                border-right:1px solid #1f3344;
                font-weight:bold;
            }
            QTableCornerButton::section {
                background-color:#132230;
                border:0;
                border-bottom:1px solid #26323c;
                border-right:1px solid #1f3344;
            }
            QPushButton {background:#087eae;border:0;border-radius:6px;padding:12px;color:white;font-weight:bold;}
            QPushButton:hover {background:#079bd5;}
        """)

    def _style_table(self, table):
        """Configure le comportement standard d'un tableau (sélection par ligne, lecture seule).

        Args:
            table (QTableWidget): Tableau PyQt6 à configurer.
        """
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def on_connected(self):
        """Met à jour le statut visuel en vert et charge les données initiales dès connexion."""
        self.status.setText(f"● CONNECTÉ — {self.reseau.host}:{self.reseau.port}")
        self.status.setStyleSheet("color:#22c55e;font-weight:bold;")
        self.refresh_database()
        self.refresh_incidents()

    def on_disconnected(self, error):
        """Affiche un avertissement orange lorsque la connexion avec le serveur est perdue.

        Args:
            error (str): Description technique de la coupure réseau.
        """
        self.status.setText("● SERVEUR INJOIGNABLE — nouvelle tentative…")
        self.status.setStyleSheet("color:#ffb020;font-weight:bold;")

    def on_response(self, msg):
        """Traite les réponses JSON retournées par le serveur suite à une requête client.

        Args:
            msg (dict): Dictionnaire JSON reçu du serveur.
        """
        if not msg.get("ok"):
            QMessageBox.warning(self, "ctOS", msg.get("error", "Erreur serveur"))
            return
        action = msg.get("action")
        if action in ("INCIDENT_CREATE", "INCIDENT_DECIDE", "INCIDENT_UPDATE", "INCIDENT_DELETE"):
            self.refresh_database()
            self.refresh_incidents()
        elif action == "INCIDENT_LIST":
            self._fill(self.incidents, msg.get("rows", []), ["id", "type_incident", "lieu", "statut"])
        elif action == "INTERVENTION_LIST":
            self._fill(self.intervention_db, msg.get("rows", []),
                       ["id", "id_incident", "unite_envoyee", "heure", "type_incident", "lieu"])
        elif action == "INCIDENT_LIST_DB":
            self._fill(self.incident_db, msg.get("rows", []),
                       ["id", "type_incident", "lieu", "statut"])

    def _fill(self, table, rows, keys):
        """Remplit un QTableWidget à partir d'une liste de dictionnaires SQLite.

        Args:
            table (QTableWidget): Tableau cible à remplir.
            rows (list[dict]): Lignes retournées par le serveur.
            keys (list[str]): Clés ordonnées correspondant aux colonnes du tableau.
        """
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(keys):
                table.setItem(r, c, QTableWidgetItem(str(row.get(key, ""))))

    def create_incident(self):
        """Valide le formulaire de saisie et envoie une requête INCIDENT_CREATE au serveur."""
        typ, lieu = self.type_input.text().strip(), self.place_input.text().strip()
        if not typ or not lieu:
            QMessageBox.information(self, "Incident", "Renseigne le type et le lieu.")
            return
        if self.reseau.send({"action": "INCIDENT_CREATE", "type": typ, "lieu": lieu}):
            self.type_input.clear()
            self.place_input.clear()
        else:
            QMessageBox.warning(self, "Réseau", "Pas de connexion au serveur.")

    def decide(self, decision):
        """Envoie la décision de l'opérateur ('VALIDER' ou 'REFUSER') sur l'incident sélectionné.

        Args:
            decision (str): Action choisie ('VALIDER' ou 'REFUSER').
        """
        row = self.incidents.currentRow()
        if row < 0:
            QMessageBox.information(self, "Incident", "Sélectionne un incident.")
            return
        ident_item = self.incidents.item(row, 0)
        status_item = self.incidents.item(row, 3)
        if not ident_item or not status_item or status_item.text() != "EN ATTENTE":
            QMessageBox.information(self, "Incident", "Cet incident a déjà été traité.")
            return
        self.reseau.send({"action": "INCIDENT_DECIDE", "id": int(ident_item.text()), "decision": decision})

    def edit_incident_db(self):
        """Ouvre la boîte de dialogue d'édition pour l'incident sélectionné dans l'onglet BDD."""
        if self.db_tabs.currentWidget() is not self.incident_db:
            QMessageBox.information(self, "Base de données", "Sélectionne une ligne dans l'onglet 'Table incidents'.")
            return
        row = self.incident_db.currentRow()
        if row < 0:
            QMessageBox.information(self, "Base de données", "Sélectionne un incident à modifier.")
            return
        ident = int(self.incident_db.item(row, 0).text())
        typ = self.incident_db.item(row, 1).text()
        lieu = self.incident_db.item(row, 2).text()
        statut = self.incident_db.item(row, 3).text()

        dlg = EditIncidentDialog(ident, typ, lieu, statut, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_typ = dlg.type_edit.text().strip()
            new_lieu = dlg.lieu_edit.text().strip()
            new_statut = dlg.statut_combo.currentText()
            if not new_typ or not new_lieu:
                QMessageBox.warning(self, "Base de données", "Le type et le lieu sont obligatoires.")
                return
            if not self.reseau.send({
                "action": "INCIDENT_UPDATE",
                "id": ident,
                "type": new_typ,
                "lieu": new_lieu,
                "statut": new_statut
            }):
                QMessageBox.warning(self, "Réseau", "Pas de connexion au serveur.")

    def delete_incident_db(self):
        """Demande confirmation puis envoie une suppression distante INCIDENT_DELETE."""
        if self.db_tabs.currentWidget() is not self.incident_db:
            QMessageBox.information(self, "Base de données", "Sélectionne une ligne dans l'onglet 'Table incidents'.")
            return
        row = self.incident_db.currentRow()
        if row < 0:
            QMessageBox.information(self, "Base de données", "Sélectionne un incident à supprimer.")
            return
        ident = int(self.incident_db.item(row, 0).text())
        confirm = QMessageBox.question(
            self,
            "Confirmation",
            f"Supprimer définitivement l'incident #{ident} de la base de données serveur ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if not self.reseau.send({"action": "INCIDENT_DELETE", "id": ident}):
                QMessageBox.warning(self, "Réseau", "Pas de connexion au serveur.")

    def refresh_incidents(self):
        """Demande au serveur la liste à jour des incidents pour l'onglet principal."""
        self.reseau.send({"action": "INCIDENT_LIST"})

    def refresh_database(self):
        """Demande au serveur le contenu complet des tables `incidents` et `interventions`."""
        self.reseau.send({"action": "INCIDENT_LIST_DB"})
        self.reseau.send({"action": "INTERVENTION_LIST"})

    def on_event(self, event):
        """Réagit aux événements push diffusés par le serveur (véhicule, urgence, BDD).

        Args:
            event (dict): Dictionnaire JSON contenant la clé 'event'.
        """
        name = event.get("event")
        if name == "BDD_UPDATED":
            self.refresh_database()
            self.refresh_incidents()
        elif name == "GO_VEHICULE":
            # Ouvre une nouvelle fenêtre GPS pour chaque incident validé.
            # Une ancienne fenêtre masquée ne doit pas bloquer l'incident suivant.
            if self.vehicule is not None and not self.vehicule.isVisible():
                self.vehicule = None

            if self.vehicule is None:
                self.vehicule = MainVehicule(self.reseau, event.get("incident"))
                self.vehicule.show()
                self.vehicule.raise_()
                self.vehicule.activateWindow()
                self.vehicule.demarrer_trajet()
        elif name == "URGENCE":
            # Le véhicule est arrivé : libère sa référence pour le prochain incident.
            if self.vehicule is not None:
                self.vehicule.timer_mouvement.stop()
                self.vehicule.hide()
                self.vehicule = None

            # Une fenêtre Qt fermée est simplement masquée par défaut.
            # Il faut donc la réafficher même si self.carrefour existe déjà.
            if self.carrefour is None:
                self.carrefour = MainCarrefour(self.reseau)

            self.carrefour.show()
            self.carrefour.raise_()
            self.carrefour.activateWindow()
            self.carrefour.combo_direction.setCurrentText("sud")
            self.carrefour.combo_manoeuvre.setCurrentText("tout_droit")
            if self.carrefour.mode != "urgence":
                self.carrefour._declencher_urgence()

    def closeEvent(self, event):
        """Arrête proprement le timer et le thread réseau lors de la fermeture de la fenêtre.

        Args:
            event (QCloseEvent): Événement de fermeture Qt.
        """
        self.refresh_timer.stop()
        self.reseau.stop()
        self.reseau.wait(1500)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainClient()
    window.show()
    sys.exit(app.exec())
