"""Interface graphique 2D de supervision et de simulation du carrefour ctOS.

Modélise le trafic routier, le cycle des feux tricolores, les panneaux à messages
variables (VMS) interactifs et le dégagement d'un corridor de secours pour ambulance.
"""

import math
import sys
from datetime import datetime

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QGraphicsEllipseItem, QGraphicsItemGroup, QGraphicsLineItem,
    QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem,
    QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget
)

# Dimensions de la scène graphique 2D du carrefour
LARGEUR_SCENE = 760
HAUTEUR_SCENE = 560

# --- Palette graphique ctOS ---
COULEUR_FOND = QColor("#0B1016")
COULEUR_GRILLE = QColor("#121A22")
COULEUR_ROUTE = QColor("#262C33")
COULEUR_MARQUAGE = QColor("#89B2C4")
COULEUR_BATIMENT_TRAIT = QColor("#4F7184")
COULEUR_BATIMENT_FOND = QColor("#121820")
COULEUR_TEXTE = QColor("#B9D6E3")
ROUGE = QColor("#E5544B")
ORANGE = QColor("#FFB300")
VERT = QColor("#48B868")

# Définition des phases du cycle normal : (durée_ms, état_horizontal, état_vertical, libellé)
PHASES = [
    (4000, "vert", "rouge", "Cycle normal : route horizontale"),
    (1000, "orange", "rouge", "Cycle normal : transition"),
    (4000, "rouge", "vert", "Cycle normal : route verticale"),
    (1000, "rouge", "orange", "Cycle normal : transition"),
]
DUREE_CYCLE = sum(duree for duree, _, _, _ in PHASES)

# Lignes d'arrêt avant le carrefour pour chaque axe
ARRET_EST = 320
ARRET_OUEST = 440
ARRET_SUD = 220
ARRET_NORD = 340
ZONE_ARRET = 30
DISTANCE_MINIMALE = 34

# Association vecteur vitesse initial -> (feu concerné, fonction de distance à la ligne d'arrêt)
INFOS_SENS = {
    (1.8, 0): ("ouest", lambda x, y: ARRET_EST - x),
    (-1.8, 0): ("est", lambda x, y: x - ARRET_OUEST),
    (0, 1.8): ("nord", lambda x, y: ARRET_SUD - y),
    (0, -1.8): ("sud", lambda x, y: y - ARRET_NORD),
}


# ==========================================
# L'INTERFACE PURE DU CARREFOUR
# ==========================================
class PanneauInteractif(QGraphicsItemGroup):
    """Panneau à messages variables (VMS) cliquable sur un accotement du carrefour.

    Attributes:
        direction (str): Axe routier associé ('nord', 'sud', 'est' ou 'ouest').
        callback (callable): Fonction appelée lors d'un clic gauche sur le panneau.
    """

    def __init__(self, direction, callback):
        """Construit les éléments graphiques du panneau VMS et active l'interaction souris.

        Args:
            direction (str): Point cardinal de l'accotement.
            callback (callable): Gestionnaire de clic prenant `direction` en paramètre.
        """
        super().__init__()
        self.direction = direction
        self.callback = callback
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(25)

        self.fond = QGraphicsRectItem(0, 0, 126, 28)
        self.fond.setBrush(QBrush(QColor("#09131A")))
        self.fond.setPen(QPen(QColor("#2D6578"), 1.2))
        self.addToGroup(self.fond)

        self.liseret = QGraphicsRectItem(0, 0, 126, 3)
        self.liseret.setBrush(QBrush(QColor("#42D8F4")))
        self.liseret.setPen(QPen(Qt.PenStyle.NoPen))
        self.addToGroup(self.liseret)

        self.voyant = QGraphicsEllipseItem(6, 10, 5, 5)
        self.voyant.setBrush(QBrush(QColor("#42D8F4")))
        self.voyant.setPen(QPen(Qt.PenStyle.NoPen))
        self.addToGroup(self.voyant)

        self.texte = QGraphicsTextItem()
        self.texte.setDefaultTextColor(QColor("#A9EFFF"))
        self.texte.setFont(QFont("Consolas", 6, QFont.Weight.Bold))
        self.texte.setPos(15, 6)
        self.addToGroup(self.texte)

        self.setToolTip(f"Panneau {direction.upper()} — cliquer pour changer la consigne")

    def mousePressEvent(self, event):
        """Déclenche le changement de consigne VMS lors d'un clic gauche.

        Args:
            event (QGraphicsSceneMouseEvent): Événement souris reçu par l'item.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.callback(self.direction)
            event.accept()
            return
        super().mousePressEvent(event)


class CtosMainWindow(QMainWindow):
    """Fenêtre principale de simulation 2D et de supervision du carrefour ctOS.

    Attributes:
        scene (QGraphicsScene): Scène 2D contenant routes, feux, panneaux et véhicules.
        view (QGraphicsView): Vue affichant la scène avec anticrénelage.
        feux (dict): Dictionnaire des feux tricolores par direction.
        voitures (list[dict]): Liste des véhicules civils en circulation.
        mode (str): Mode de fonctionnement actuel ('normal' ou 'urgence').
        horloge (QTimer): Boucle d'animation cadencée toutes les 30 ms.
    """

    def __init__(self):
        """Initialise la scène graphique, les feux, les véhicules et l'horloge d'animation."""
        super().__init__()
        self.setWindowTitle("ctOS // TRAFFIC CONTROL")
        self.resize(1240, 820)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #080D12; color: #D6E8F0; }
            QFrame#Header { background: #0D151D; border: 1px solid #1E3B4A; border-radius: 8px; }
            QFrame#Panel { background: #0D151D; border: 1px solid #1E3B4A; border-radius: 8px; }
            QFrame#Metric { background: #101D27; border: 1px solid #1D3948; border-radius: 6px; }
            QLabel { color: #C7DCE6; }
            QLabel#Brand { color: #EAF8FF; font-size: 21px; font-weight: 800; letter-spacing: 2px; }
            QLabel#Eyebrow { color: #49D9F5; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
            QLabel#Muted { color: #7795A5; font-size: 11px; }
            QLabel#MetricValue { color: #55DDF4; font-size: 22px; font-weight: 800; }
            QLabel#SectionTitle { color: #66DDF4; font-size: 11px; font-weight: 800; letter-spacing: 1px; }
            QLabel#StatusValue { color: #62E6B5; font-weight: 700; }
            QGroupBox { border: 1px solid #1C3948; border-radius: 7px; margin-top: 12px; padding: 12px 9px 9px 9px; color: #54DDF5; font-weight: 700; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QComboBox { background: #101D27; color: #E5F6FC; border: 1px solid #2B5264; border-radius: 5px; padding: 7px; min-height: 20px; }
            QComboBox QAbstractItemView { background: #101D27; color: #E5F6FC; selection-background-color: #164D61; }
            QPushButton { background: #112A37; color: #DDF8FF; border: 1px solid #2D7187; border-radius: 5px; padding: 9px 10px; font-weight: 700; }
            QPushButton:hover { background: #164457; border-color: #50DFF5; }
            QPushButton#EmergencyButton { background: #3A151B; border: 1px solid #E5544B; color: #FFB7B2; }
            QPushButton#EmergencyButton:hover { background: #5A1A23; }
            QCheckBox { color: #C7DCE6; spacing: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QCheckBox::indicator:unchecked { background: #101D27; border: 1px solid #3A6172; border-radius: 3px; }
            QCheckBox::indicator:checked { background: #42D8F4; border: 1px solid #42D8F4; border-radius: 3px; }
            QProgressBar { background: #101D27; border: 1px solid #254657; border-radius: 4px; height: 8px; text-align: center; }
            QProgressBar::chunk { background: #42D8F4; border-radius: 3px; }
            QGraphicsView { border: 1px solid #1D3C4A; border-radius: 8px; background: #080D12; }
        """)

        self.scene = QGraphicsScene(0, 0, LARGEUR_SCENE, HAUTEUR_SCENE)
        self.scene.setBackgroundBrush(QBrush(COULEUR_FOND))
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.feux = {}
        self.ecrans_vms = []
        self.panneaux_vms = {}
        self.modes_panneaux = {direction: 0 for direction in ("nord", "sud", "est", "ouest")}
        self.voitures = []
        self.etat_lumiere = {"nord": "rouge", "sud": "rouge", "est": "rouge", "ouest": "rouge"}
        self.mode = "normal"
        self._libelle_feu = ""
        self.ambulance_direction = ""
        self._temps_ecoule = 0
        self._horloge_ms = 0
        self._derniere_seconde = -1

        # Initialisation des éléments graphiques de la scène
        self._dessiner_grille_fond()
        self._dessiner_batiments()
        self._dessiner_carrefour()
        self._dessiner_bandeau_info()

        self.item_ambulance = self._creer_ambulance_item()
        self.scene.addItem(self.item_ambulance)
        self._creer_voitures(dense=False)
        self._construire_fenetre()

        # Boucle d'animation principale (environ 33 images/seconde)
        self.horloge = QTimer(self)
        self.horloge.timeout.connect(self._tick)
        self.horloge.start(30)

    def _construire_fenetre(self):
        """Assemble l'en-tête, la vue tactique du carrefour et le panneau de contrôle latéral."""
        conteneur = QWidget()
        racine = QVBoxLayout(conteneur)
        racine.setContentsMargins(14, 14, 14, 14)
        racine.setSpacing(12)

        # Barre supérieure ctOS
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(14)

        brand_col = QVBoxLayout()
        brand = QLabel("ctOS")
        brand.setObjectName("Brand")
        subtitle = QLabel("URBAN TRAFFIC CONTROL SYSTEM")
        subtitle.setObjectName("Eyebrow")
        brand_col.addWidget(brand)
        brand_col.addWidget(subtitle)
        header_layout.addLayout(brand_col)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("color: #244756;")
        header_layout.addWidget(separator)

        self.label_header_status = QLabel("● SYSTÈME OPÉRATIONNEL")
        self.label_header_status.setStyleSheet("color: #62E6B5; font-size: 11px; font-weight: 800;")
        header_layout.addWidget(self.label_header_status)
        header_layout.addStretch(1)

        self.label_clock = QLabel("--:--:--")
        self.label_clock.setStyleSheet("color: #65DFF5; font-family: Consolas; font-size: 15px; font-weight: 700;")
        header_layout.addWidget(self.label_clock)
        racine.addWidget(header)

        # Zone principale : simulation + panneau latéral
        zone = QHBoxLayout()
        zone.setSpacing(12)

        zone_carte = QVBoxLayout()
        zone_carte.setSpacing(8)
        titre_carte = QLabel("01  /  VUE TACTIQUE DU CARREFOUR")
        titre_carte.setObjectName("SectionTitle")
        zone_carte.addWidget(titre_carte)

        self.view.setMinimumSize(600, 480)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        zone_carte.addWidget(self.view, 1)

        self.label_carte_footer = QLabel("FLUX EN DIRECT  •  CAPTEURS SYNCHRONISÉS")
        self.label_carte_footer.setObjectName("Muted")
        zone_carte.addWidget(self.label_carte_footer)
        zone.addLayout(zone_carte, 1)

        panneau = QFrame()
        panneau.setObjectName("Panel")
        panneau.setMinimumWidth(270)
        panneau.setMaximumWidth(330)
        panneau_layout = QVBoxLayout(panneau)
        panneau_layout.setContentsMargins(14, 14, 14, 14)
        panneau_layout.setSpacing(12)

        titre = QLabel("CENTRE DE CONTRÔLE")
        titre.setObjectName("SectionTitle")
        panneau_layout.addWidget(titre)

        # Cartes de métriques
        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.label_nb_vehicules = self._creer_metrique(metrics, "VÉHICULES", "0")
        self.label_mode = self._creer_metrique(metrics, "MODE", "NORMAL")
        panneau_layout.addLayout(metrics)

        # Statut des feux
        groupe_feux = QGroupBox("ÉTAT DES FEUX")
        feux_layout = QVBoxLayout(groupe_feux)
        feux_layout.setSpacing(8)
        self.labels_feux = {}
        for nom in ("nord", "sud", "est", "ouest"):
            ligne = QHBoxLayout()
            nom_label = QLabel(nom.upper())
            nom_label.setStyleSheet("font-size: 11px; font-weight: 700;")
            etat_label = QLabel("● ROUGE")
            etat_label.setStyleSheet("color: #E5544B; font-weight: 800; font-size: 11px;")
            ligne.addWidget(nom_label)
            ligne.addStretch(1)
            ligne.addWidget(etat_label)
            feux_layout.addLayout(ligne)
            self.labels_feux[nom] = etat_label
        panneau_layout.addWidget(groupe_feux)

        # Commandes opérationnelles d'urgence
        groupe_urgence = QGroupBox("GESTION D'URGENCE")
        urgence_layout = QVBoxLayout(groupe_urgence)
        urgence_layout.setSpacing(8)

        direction_label = QLabel("Origine de l'ambulance")
        direction_label.setObjectName("Muted")
        urgence_layout.addWidget(direction_label)

        self.combo_direction = QComboBox()
        self.combo_direction.addItems(["nord", "sud", "est", "ouest"])
        self.combo_direction.setToolTip("Choisir le côté par lequel arrive le véhicule de secours")
        urgence_layout.addWidget(self.combo_direction)

        manoeuvre_label = QLabel("Manœuvre prévue")
        manoeuvre_label.setObjectName("Muted")
        urgence_layout.addWidget(manoeuvre_label)

        self.combo_manoeuvre = QComboBox()
        self.combo_manoeuvre.addItems(["tout_droit", "gauche", "droite"])
        self.combo_manoeuvre.setToolTip("Choisir la trajectoire de l’ambulance dans le carrefour")
        urgence_layout.addWidget(self.combo_manoeuvre)

        self.check_trafic = QCheckBox("Activer le trafic dense")
        self.check_trafic.setToolTip("Afficher davantage de véhicules dans la simulation")
        self.check_trafic.stateChanged.connect(self._changer_trafic)
        urgence_layout.addWidget(self.check_trafic)

        bouton_declencher = QPushButton("⚠  DÉCLENCHER UNE URGENCE")
        bouton_declencher.setObjectName("EmergencyButton")
        bouton_declencher.setToolTip("Activer la priorité des feux et dégager le corridor de secours")
        bouton_declencher.setMinimumHeight(42)
        bouton_declencher.clicked.connect(self._declencher_urgence)
        urgence_layout.addWidget(bouton_declencher)
        panneau_layout.addWidget(groupe_urgence)

        # État de l'intervention
        groupe_systeme = QGroupBox("ÉTAT DU SYSTÈME")
        systeme_layout = QVBoxLayout(groupe_systeme)
        self.label_etat_intervention = QLabel("En attente d'une intervention")
        self.label_etat_intervention.setWordWrap(True)
        self.label_etat_intervention.setStyleSheet("color: #8BA9B8; font-size: 11px;")
        systeme_layout.addWidget(self.label_etat_intervention)

        self.barre_activite = QProgressBar()
        self.barre_activite.setRange(0, 100)
        self.barre_activite.setValue(0)
        self.barre_activite.setTextVisible(False)
        systeme_layout.addWidget(self.barre_activite)
        panneau_layout.addWidget(groupe_systeme)

        panneau_layout.addStretch(1)
        note = QLabel("ctOS // MODULE CARREFOUR v1.0")
        note.setObjectName("Muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panneau_layout.addWidget(note)
        zone.addWidget(panneau)
        racine.addLayout(zone, 1)

        bas = QLabel("RÉSEAU LOCAL  •  PRIORITÉ AUX VÉHICULES DE SECOURS  •  SIMULATION 2D")
        bas.setObjectName("Muted")
        bas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        racine.addWidget(bas)

        self.setCentralWidget(conteneur)
        self._actualiser_panneau()

    def _creer_metrique(self, disposition, titre, valeur):
        """Crée une carte d'indicateur chiffré dans le panneau latéral.

        Args:
            disposition (QLayout): Layout parent recevant la carte.
            titre (str): Libellé de la métrique (ex. 'VÉHICULES').
            valeur (str): Valeur initiale affichée.

        Returns:
            QLabel: Widget texte permettant de mettre à jour la valeur dynamiquement.
        """
        carte = QFrame()
        carte.setObjectName("Metric")
        carte_layout = QVBoxLayout(carte)
        carte_layout.setContentsMargins(10, 10, 10, 10)
        carte_layout.setSpacing(4)

        titre_label = QLabel(titre)
        titre_label.setObjectName("Muted")
        valeur_label = QLabel(valeur)
        valeur_label.setObjectName("MetricValue")

        carte_layout.addWidget(titre_label)
        carte_layout.addWidget(valeur_label)
        disposition.addWidget(carte)
        return valeur_label

    def _actualiser_panneau(self):
        """Synchronise les indicateurs du panneau latéral avec l'état courant du carrefour."""
        if not hasattr(self, "labels_feux"):
            return
        couleurs = {
            "rouge": "#E5544B",
            "orange": "#FFB300",
            "vert": "#48B868",
        }
        for nom, label in self.labels_feux.items():
            etat = self.etat_lumiere.get(nom, "rouge")
            label.setText(f"● {etat.upper()}")
            label.setStyleSheet(f"color: {couleurs.get(etat, '#E5544B')}; font-weight: 800; font-size: 11px;")

        self.label_nb_vehicules.setText(str(len(self.voitures)))
        urgence = self.mode == "urgence"
        self.label_mode.setText("URGENCE" if urgence else "NORMAL")
        self.label_mode.setStyleSheet(
            "color: #FF6B65; font-size: 17px; font-weight: 800;" if urgence
            else "color: #62E6B5; font-size: 22px; font-weight: 800;"
        )
        self.label_header_status.setText("● PRIORITÉ URGENCE ACTIVE" if urgence else "● SYSTÈME OPÉRATIONNEL")
        self.label_header_status.setStyleSheet(
            "color: #FF6B65; font-size: 11px; font-weight: 800;" if urgence
            else "color: #62E6B5; font-size: 11px; font-weight: 800;"
        )
        self.label_etat_intervention.setText(
            f"Priorité accordée depuis le {self.ambulance_direction.upper()} — corridor de secours activé."
            if urgence else "Aucune urgence active. Surveillance du trafic en cours."
        )
        self.barre_activite.setValue(70 if urgence else 0)

    def _changer_trafic(self, state):
        """Régénère le parc de véhicules selon l'état de la case 'Activer le trafic dense'.

        Args:
            state (int): État de la case à cocher Qt (0 = décoché, non nul = coché).
        """
        dense = bool(state)
        self._creer_voitures(dense)

    def _declencher_urgence(self):
        """Active le protocole d'onde verte, verrouille les autres axes au rouge et lance l'ambulance."""
        direction = self.combo_direction.currentText()
        manoeuvre = self.combo_manoeuvre.currentText()
        self.ambulance_direction = direction

        # Passe uniquement l'axe de l'ambulance au vert et bloque les axes transversaux au rouge
        for nom in ("nord", "sud", "est", "ouest"):
            self.etat_lumiere[nom] = "vert" if nom == direction else "rouge"

        self._appliquer_etats_lumiere()
        self.mode = "urgence"
        self._libelle_feu = f"PRIORITÉ ctOS : DÉGAGEMENT DES VOIES ({direction.upper()})"
        self._actualiser_panneaux_vms()
        self.texte_phase.setDefaultTextColor(QColor("#FF6B65"))
        self._actualiser_panneau()

        self.item_ambulance.setVisible(True)
        self.ambulance_a_tourne = False
        self.pivot_cible = None

        # Coordonnées d'entrée, orientation et vecteur vitesse selon la provenance
        departs = {
            "ouest": (-80, 300, 0, 2.5, 0),
            "est": (LARGEUR_SCENE + 80, 260, 180, -2.5, 0),
            "nord": (360, -80, 90, 0, 2.5),
            "sud": (400, HAUTEUR_SCENE + 80, 270, 0, -2.5),
        }
        # Points de pivot et nouveaux vecteurs vitesse en cas de virage à gauche ou à droite
        virages = {
            "ouest": {"gauche": (400, 270, 0, -2.5), "droite": (360, 90, 0, 2.5)},
            "est": {"gauche": (360, 90, 0, 2.5), "droite": (400, 270, 0, -2.5)},
            "nord": {"gauche": (300, 0, 2.5, 0), "droite": (260, 180, -2.5, 0)},
            "sud": {"gauche": (260, 180, -2.5, 0), "droite": (300, 0, 2.5, 0)},
        }
        x, y, rotation, self.ambulance_dx, self.ambulance_dy = departs[direction]
        self.item_ambulance.setPos(x, y)
        self.item_ambulance.setRotation(rotation)
        if manoeuvre in virages[direction]:
            (self.pivot_cible, self.nouvelle_rot,
             self.nouveau_dx, self.nouveau_dy) = virages[direction][manoeuvre]
        self.texte_phase.setPlainText(self._libelle_feu)

    def _terminer_urgence(self):
        """Restaure le cycle normal des feux une fois que l'ambulance a quitté le carrefour."""
        self.mode = "normal"
        self._actualiser_panneaux_vms()
        self.texte_phase.setDefaultTextColor(COULEUR_TEXTE)
        self._libelle_feu = "Cycle normal : reprise du trafic"
        self._actualiser_panneau()

    # --- MÉTHODES DE DESSIN ---
    def _ajouter_ligne(self, x1, y1, x2, y2, pen):
        """Ajoute un segment graphique à la scène 2D.

        Args:
            x1 (float): Abscisse de départ.
            y1 (float): Ordonnée de départ.
            x2 (float): Abscisse d'arrivée.
            y2 (float): Ordonnée d'arrivée.
            pen (QPen): Style de trait (couleur, épaisseur, pointillés).
        """
        ligne = QGraphicsLineItem(x1, y1, x2, y2)
        ligne.setPen(pen)
        self.scene.addItem(ligne)

    def _dessiner_grille_fond(self):
        """Dessine le quadrillage tactique en arrière-plan de la scène."""
        pen_grille = QPen(COULEUR_GRILLE, 1)
        for x in range(0, LARGEUR_SCENE + 1, 40):
            self._ajouter_ligne(x, 0, x, HAUTEUR_SCENE, pen_grille)
        for y in range(0, HAUTEUR_SCENE + 1, 40):
            self._ajouter_ligne(0, y, LARGEUR_SCENE, y, pen_grille)

    def _dessiner_batiments(self):
        """Dessine les quatre îlots urbains entourant l'intersection."""
        for x, y, largeur, hauteur in ((60, 70, 130, 100), (610, 60, 120, 110), (60, 410, 140, 90),
                                       (600, 400, 130, 100)):
            corps = QGraphicsRectItem(x, y, largeur, hauteur)
            corps.setBrush(QBrush(COULEUR_BATIMENT_FOND))
            corps.setPen(QPen(COULEUR_BATIMENT_TRAIT, 1.5))
            self.scene.addItem(corps)

    def _arrondir_coin(self, cx, cy, dx1, dy1, dx2, dy2, rayon=22):
        """Dessine un arrondi de trottoir à l'un des quatre angles du carrefour.

        Args:
            cx (float): Abscisse du sommet de l'angle droit.
            cy (float): Ordonnée du sommet de l'angle droit.
            dx1 (int): Direction horizontale du premier tangent (-1 ou 1).
            dy1 (int): Direction verticale du premier tangent (-1 ou 1).
            dx2 (int): Direction horizontale du second tangent (-1 ou 1).
            dy2 (int): Direction verticale du second tangent (-1 ou 1).
            rayon (int): Rayon de courbure en pixels.
        """
        p_coin = QPointF(cx, cy)
        p1 = QPointF(cx + dx1 * rayon, cy + dy1 * rayon)
        p2 = QPointF(cx + dx2 * rayon, cy + dy2 * rayon)

        masque = QPainterPath(p1)
        masque.quadTo(p_coin, p2)
        masque.lineTo(p_coin)
        masque.closeSubpath()

        item_masque = QGraphicsPathItem(masque)
        item_masque.setBrush(QBrush(COULEUR_FOND))
        item_masque.setPen(QPen(Qt.PenStyle.NoPen))
        self.scene.addItem(item_masque)

        bord = QPainterPath(p1)
        bord.quadTo(p_coin, p2)
        item_bord = QGraphicsPathItem(bord)
        item_bord.setPen(QPen(COULEUR_MARQUAGE, 1.5))
        self.scene.addItem(item_bord)

    def _dessiner_carrefour(self):
        """Construit les chaussées, marquages au sol, feux tricolores et panneaux VMS."""
        chemin_h = QPainterPath()
        chemin_h.addRect(QRectF(0, 240, LARGEUR_SCENE, 80))
        chemin_v = QPainterPath()
        chemin_v.addRect(QRectF(340, 0, 80, HAUTEUR_SCENE))

        # Fusion géométrique des deux voies perpendiculaires
        route = QGraphicsPathItem(chemin_h.united(chemin_v))
        route.setBrush(QBrush(COULEUR_ROUTE))
        route.setPen(QPen(COULEUR_MARQUAGE.darker(130), 1.5))
        self.scene.addItem(route)

        for cx, cy, dx1, dy1, dx2, dy2 in ((340, 240, -1, 0, 0, -1), (420, 240, 1, 0, 0, -1), (340, 320, -1, 0, 0, 1),
                                           (420, 320, 1, 0, 0, 1)):
            self._arrondir_coin(cx, cy, dx1, dy1, dx2, dy2)

        solide = QPen(COULEUR_MARQUAGE, 2, Qt.PenStyle.SolidLine)
        pointille = QPen(COULEUR_MARQUAGE, 1, Qt.PenStyle.DashLine)
        for x1, y1, x2, y2, pen in (
                (0, 280, 340, 280, solide), (420, 280, LARGEUR_SCENE, 280, solide),
                (0, 260, 340, 260, pointille), (420, 260, LARGEUR_SCENE, 260, pointille),
                (0, 300, 340, 300, pointille), (420, 300, LARGEUR_SCENE, 300, pointille),
                (380, 0, 380, 240, solide), (380, 320, 380, HAUTEUR_SCENE, solide),
                (360, 0, 360, 240, pointille), (360, 320, 360, HAUTEUR_SCENE, pointille),
                (400, 0, 400, 240, pointille), (400, 320, 400, HAUTEUR_SCENE, pointille),
        ):
            self._ajouter_ligne(x1, y1, x2, y2, pen)

        for nom, x, y in (("nord", 372, 155), ("sud", 372, 350), ("est", 450, 258), ("ouest", 294, 258)):
            self.feux[nom] = self._creer_feu(x, y)

        self._creer_panneaux_vms()

    def _creer_feu(self, x, y):
        """Dessine un feu tricolore (rouge, orange, vert) et son mini-afficheur VMS.

        Args:
            x (float): Abscisse du boîtier sur la scène.
            y (float): Ordonnée du boîtier sur la scène.

        Returns:
            dict: Dictionnaire associant chaque couleur à `(item_ampoule, QColor, effet_halo)`.
        """
        boitier = QGraphicsRectItem(x, y, 16, 44)
        boitier.setBrush(QBrush(QColor("#171C22")))
        boitier.setPen(QPen(COULEUR_MARQUAGE, 1.2))
        self.scene.addItem(boitier)

        ampoules = {}
        for i, (nom, couleur) in enumerate((("rouge", ROUGE), ("orange", ORANGE), ("vert", VERT))):
            ampoule = QGraphicsEllipseItem(x + 3, y + 3 + i * 14, 10, 10)
            ampoule.setBrush(QBrush(couleur.darker(300)))
            ampoule.setPen(QPen(Qt.PenStyle.NoPen))

            # Halo lumineux activé uniquement lorsque l'ampoule est allumée
            effet = QGraphicsDropShadowEffect()
            effet.setOffset(0, 0)
            effet.setBlurRadius(18)
            effet.setColor(couleur)
            effet.setEnabled(False)
            ampoule.setGraphicsEffect(effet)

            self.scene.addItem(ampoule)
            ampoules[nom] = (ampoule, couleur, effet)

        boitier_vms = QGraphicsRectItem(x - 6, y + 46, 28, 14)
        boitier_vms.setBrush(QBrush(QColor("#000000")))
        boitier_vms.setPen(QPen(COULEUR_MARQUAGE, 1))
        self.scene.addItem(boitier_vms)

        texte_vms = QGraphicsTextItem("30")
        texte_vms.setDefaultTextColor(QColor("#42D8F4"))
        texte_vms.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        texte_vms.setPos(x + 1, y + 44)
        texte_vms.setZValue(8)
        self.scene.addItem(texte_vms)
        self.ecrans_vms.append((texte_vms, next((nom for nom, fx, fy in (("nord", 372, 155), ("sud", 372, 350), ("est", 450, 258), ("ouest", 294, 258)) if fx == x and fy == y), "nord")))

        return ampoules

    def _creer_panneaux_vms(self):
        """Instancie et positionne les 4 panneaux VMS cliquables sur les accotements."""
        positions = {
            # Placés sur les accotements sans masquer les voies ni les véhicules
            "ouest": (178, 218),
            "nord": (430, 205),
            "sud": (286, 328),
            "est": (456, 328),
        }
        for direction, (x, y) in positions.items():
            panneau = PanneauInteractif(direction, self._cliquer_panneau)
            panneau.setPos(x, y)
            self.scene.addItem(panneau)
            self.panneaux_vms[direction] = panneau
        self._actualiser_panneaux_vms()

    def _cliquer_panneau(self, direction):
        """Fait défiler manuellement la consigne d'un panneau VMS (AUTO -> RALENTIR -> STOP).

        Args:
            direction (str): Direction du panneau cliqué.
        """
        if self.mode == "urgence":
            self.label_etat_intervention.setText(
                f"URGENCE ACTIVE — panneau {direction.upper()} verrouillé par le protocole prioritaire."
            )
            return
        self.modes_panneaux[direction] = (self.modes_panneaux[direction] + 1) % 3
        consignes = ("AUTO", "RALENTIR", "STOP")
        self.label_etat_intervention.setText(
            f"Panneau {direction.upper()} : consigne manuelle « {consignes[self.modes_panneaux[direction]]} ». "
            "Cliquez à nouveau pour changer de consigne."
        )
        self._actualiser_panneaux_vms()

    def _actualiser_panneaux_vms(self):
        """Met à jour le texte et les couleurs des panneaux VMS selon le mode et les feux."""
        urgence = self.mode == "urgence"
        clignote = urgence and (self._horloge_ms // 300) % 2 == 0
        for direction, panneau in self.panneaux_vms.items():
            if urgence:
                if direction == self.ambulance_direction:
                    message, couleur, bord, fond = "SECOURS > PRIORITÉ", QColor("#FFFFFF"), QColor("#FF4D4D"), QColor("#7D2024" if clignote else "#241014")
                else:
                    message, couleur, bord, fond = "STOP  •  SECOURS", QColor("#FFB3AD"), QColor("#FF4D4D"), QColor("#7D2024" if clignote else "#241014")
            else:
                mode = self.modes_panneaux[direction]
                if mode == 2 or self.etat_lumiere.get(direction) == "rouge":
                    message, couleur, bord, fond = "STOP  •  FEU ROUGE", QColor("#FF7770"), QColor("#E5544B"), QColor("#190D10")
                elif mode == 1 or self.etat_lumiere.get(direction) == "orange":
                    message, couleur, bord, fond = "RALENTIR  •  30", QColor("#FFCB66"), QColor("#FFB300"), QColor("#19150B")
                else:
                    message, couleur, bord, fond = "FLUX NORMAL  •  30", QColor("#7DE8FF"), QColor("#2D9DB8"), QColor("#09131A")
            panneau.texte.setPlainText(f"{direction.upper()}  /  {message}")
            panneau.texte.setDefaultTextColor(couleur)
            panneau.fond.setBrush(QBrush(fond))
            panneau.fond.setPen(QPen(bord, 1.5 if clignote else 1.0))
            panneau.liseret.setBrush(QBrush(bord))
            panneau.voyant.setBrush(QBrush(couleur))
            panneau.setToolTip(f"Panneau {direction.upper()} — cliquer pour modifier la consigne (hors urgence)")

    def _actualiser_ecrans_feux(self):
        """Met à jour les petits afficheurs numériques intégrés sous chaque feu tricolore."""
        clignote = (self._horloge_ms // 300) % 2 == 0
        for ecran, direction in self.ecrans_vms:
            if self.mode == "urgence":
                prioritaire = direction == self.ambulance_direction
                ecran.setPlainText("GO" if prioritaire else ("STOP" if clignote else "!"))
                ecran.setDefaultTextColor(QColor("#FFFFFF" if prioritaire else "#FF4D4D"))
            else:
                etat = self.etat_lumiere.get(direction, "rouge")
                ecran.setPlainText("30" if etat == "vert" else ("RAL" if etat == "orange" else "STOP"))
                ecran.setDefaultTextColor(QColor("#42D8F4" if etat == "vert" else ORANGE if etat == "orange" else ROUGE))

    def _dessiner_bandeau_info(self):
        """Dessine le bandeau supérieur incrusté en haut à gauche de la scène 2D."""
        fond = QGraphicsRectItem(10, 10, 420, 32)
        fond.setBrush(QBrush(QColor(5, 8, 12, 190)))
        fond.setPen(QPen(COULEUR_MARQUAGE.darker(150), 1))
        self.scene.addItem(fond)

        self.texte_phase = QGraphicsTextItem()
        self.texte_phase.setDefaultTextColor(COULEUR_TEXTE)
        self.texte_phase.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.texte_phase.setPos(20, 16)
        self.scene.addItem(self.texte_phase)

    # --- VÉHICULES ---
    def _creer_voiture_item(self, couleur):
        """Construit le groupe graphique vectoriel d'une voiture civile.

        Args:
            couleur (str): Code hexadécimal de la carrosserie.

        Returns:
            QGraphicsItemGroup: Objet graphique composite (carrosserie, 4 roues, pare-brise).
        """
        groupe = QGraphicsItemGroup()
        chemin = QPainterPath()
        chemin.addRoundedRect(QRectF(-12, -7, 24, 14), 4, 4)

        carrosserie = QGraphicsPathItem(chemin)
        carrosserie.setBrush(QBrush(QColor(couleur)))
        carrosserie.setPen(QPen(Qt.PenStyle.NoPen))
        groupe.addToGroup(carrosserie)

        for rx, ry in [(-7, -9), (1, -9), (-7, 5), (1, 5)]:
            roue = QGraphicsRectItem(rx, ry, 6, 4)
            roue.setBrush(QBrush(QColor("#10151A")))
            roue.setPen(QPen(Qt.PenStyle.NoPen))
            groupe.addToGroup(roue)

        vitre = QGraphicsRectItem(4, -5, 4, 10)
        vitre.setBrush(QBrush(QColor(255, 255, 255, 130)))
        vitre.setPen(QPen(Qt.PenStyle.NoPen))
        groupe.addToGroup(vitre)

        return groupe

    def _creer_ambulance_item(self):
        """Construit le groupe graphique de l'ambulance avec gyrophare cyan animé.

        Returns:
            QGraphicsItemGroup: Item graphique de l'ambulance, masqué par défaut.
        """
        groupe = QGraphicsItemGroup()
        chemin = QPainterPath()
        chemin.addRoundedRect(QRectF(-14, -8, 28, 16), 4, 4)

        carrosserie = QGraphicsPathItem(chemin)
        carrosserie.setBrush(QBrush(QColor("#ffffff")))
        carrosserie.setPen(QPen(QColor("#E5544B"), 2))
        groupe.addToGroup(carrosserie)

        for rx, ry in [(-9, -10), (3, -10), (-9, 6), (3, 6)]:
            roue = QGraphicsRectItem(rx, ry, 6, 4)
            roue.setBrush(QBrush(QColor("#10151A")))
            roue.setPen(QPen(Qt.PenStyle.NoPen))
            groupe.addToGroup(roue)

        self.gyrophare = QGraphicsEllipseItem(-4, -4, 8, 8)
        self.gyrophare.setBrush(QBrush(QColor("#00bfff")))
        self.gyrophare.setPen(QPen(Qt.PenStyle.NoPen))

        self.effet_gyro = QGraphicsDropShadowEffect()
        self.effet_gyro.setOffset(0, 0)
        self.effet_gyro.setBlurRadius(20)
        self.effet_gyro.setColor(QColor("#00bfff"))
        self.gyrophare.setGraphicsEffect(self.effet_gyro)

        groupe.addToGroup(self.gyrophare)
        groupe.setVisible(False)
        return groupe

    def _creer_voitures(self, dense=False):
        """Peuple la scène avec le trafic routier en mode fluide ou dense.

        Args:
            dense (bool): True pour générer 13 véhicules, False pour 5 véhicules.
        """
        for v in self.voitures:
            self.scene.removeItem(v["item"])
        self.voitures.clear()

        def ajouter(x, y, couleur, dx, dy, angle, intention):
            """Instancie un véhicule individuel et l'enregistre dans `self.voitures`."""
            groupe = self._creer_voiture_item(couleur)
            groupe.setPos(x, y)
            groupe.setRotation(angle)
            self.scene.addItem(groupe)
            self.voitures.append(
                {"item": groupe, "dx": dx, "dy": dy, "dx_initial": dx, "dy_initial": dy, "intention": intention,
                 "tourne": False, "ecarte": False})

        vehicules = [
            (-40, 310, "#4FA0E8", 1.8, 0, 0, "tout_droit"),
            (-150, 290, "#3388CC", 1.8, 0, 0, "gauche"),
            (LARGEUR_SCENE + 40, 250, "#9B8CF0", -1.8, 0, 180, "tout_droit"),
            (350, -40, "#5ED9B0", 0, 1.8, 90, "tout_droit"),
            (410, HAUTEUR_SCENE + 40, "#F0905A", 0, -1.8, 270, "tout_droit"),
        ] if not dense else [
            (-40, 310, "#4FA0E8", 1.8, 0, 0, "tout_droit"),
            (-150, 310, "#3388CC", 1.8, 0, 0, "tout_droit"),
            (-120, 290, "#4FA0E8", 1.8, 0, 0, "gauche"),
            (-260, 290, "#5ED9B0", 1.8, 0, 0, "gauche"),
            (LARGEUR_SCENE + 40, 250, "#9B8CF0", -1.8, 0, 180, "tout_droit"),
            (LARGEUR_SCENE + 120, 250, "#F0905A", -1.8, 0, 180, "tout_droit"),
            (LARGEUR_SCENE + 180, 270, "#9B8CF0", -1.8, 0, 180, "gauche"),
            (350, -40, "#5ED9B0", 0, 1.8, 90, "tout_droit"),
            (350, -140, "#4FA0E8", 0, 1.8, 90, "tout_droit"),
            (370, -90, "#5ED9B0", 0, 1.8, 90, "gauche"),
            (410, HAUTEUR_SCENE + 40, "#F0905A", 0, -1.8, 270, "tout_droit"),
            (410, HAUTEUR_SCENE + 160, "#9B8CF0", 0, -1.8, 270, "tout_droit"),
            (390, HAUTEUR_SCENE + 100, "#F0905A", 0, -1.8, 270, "gauche"),
        ]
        for parametres in vehicules:
            ajouter(*parametres)

    # --- LOGIQUE D'ANIMATION ---
    def _tick(self):
        """Exécute un pas de simulation (feux, véhicules, horloge, gyrophare et ambulance)."""
        self._temps_ecoule = (self._temps_ecoule + self.horloge.interval()) % DUREE_CYCLE
        self._horloge_ms += self.horloge.interval()

        self._mettre_a_jour_feux()
        self._mettre_a_jour_bandeau()
        self._avancer_voitures()

        if hasattr(self, "label_clock"):
            self.label_clock.setText(datetime.now().strftime("%H:%M:%S"))
            self._actualiser_panneau()

        self._actualiser_ecrans_feux()
        if self._horloge_ms % 300 < self.horloge.interval():
            self._actualiser_panneaux_vms()

        # Animation du gyrophare et déplacement prioritaire de l'ambulance
        if self.mode == "urgence" and self.item_ambulance.isVisible():
            if (self._horloge_ms // 150) % 2 == 0:
                self.gyrophare.setBrush(QBrush(QColor("#00bfff")))
                self.effet_gyro.setEnabled(True)
            else:
                self.gyrophare.setBrush(QBrush(QColor("#003366")))
                self.effet_gyro.setEnabled(False)

            x = self.item_ambulance.pos().x() + self.ambulance_dx
            y = self.item_ambulance.pos().y() + self.ambulance_dy

            # Exécute le virage au point pivot si une manœuvre gauche/droite est configurée
            if not self.ambulance_a_tourne and self.pivot_cible is not None:
                if self.ambulance_dy == 0:
                    if (self.ambulance_dx > 0 and x >= self.pivot_cible) or (
                            self.ambulance_dx < 0 and x <= self.pivot_cible):
                        x = self.pivot_cible
                        self.ambulance_dx, self.ambulance_dy = self.nouveau_dx, self.nouveau_dy
                        self.item_ambulance.setRotation(self.nouvelle_rot)
                        self.ambulance_a_tourne = True
                else:
                    if (self.ambulance_dy > 0 and y >= self.pivot_cible) or (
                            self.ambulance_dy < 0 and y <= self.pivot_cible):
                        y = self.pivot_cible
                        self.ambulance_dx, self.ambulance_dy = self.nouveau_dx, self.nouveau_dy
                        self.item_ambulance.setRotation(self.nouvelle_rot)
                        self.ambulance_a_tourne = True

            self.item_ambulance.setPos(x, y)

            # Fin de l'intervention lorsque l'ambulance sort de la zone visible
            if x > LARGEUR_SCENE + 100 or x < -100 or y > HAUTEUR_SCENE + 100 or y < -100:
                self.item_ambulance.setVisible(False)
                self._terminer_urgence()

    def _mettre_a_jour_feux(self):
        """Calcule l'état des feux tricolores en fonction du temps écoulé dans le cycle normal."""
        if self.mode != "normal":
            return
        t = self._temps_ecoule
        for duree, actif_h, actif_v, libelle in PHASES:
            if t < duree:
                self.etat_lumiere["est"] = actif_h
                self.etat_lumiere["ouest"] = actif_h
                self.etat_lumiere["nord"] = actif_v
                self.etat_lumiere["sud"] = actif_v
                self._appliquer_etats_lumiere()
                self._libelle_feu = libelle
                return
            t -= duree

    def _appliquer_etats_lumiere(self):
        """Allume ou assombrit les ampoules graphiques de chaque feu selon `self.etat_lumiere`."""
        for nom, ampoules in self.feux.items():
            couleur_active = self.etat_lumiere[nom]
            for nom_ampoule, (item, couleur, effet) in ampoules.items():
                actif = nom_ampoule == couleur_active
                item.setBrush(QBrush(couleur if actif else couleur.darker(300)))
                effet.setEnabled(actif)

    def _mettre_a_jour_bandeau(self):
        """Affiche le libellé de la phase courante dans le bandeau supérieur en mode normal."""
        if self.mode == "normal":
            self.texte_phase.setPlainText(self._libelle_feu)

    def _peut_avancer(self, voiture):
        """Vérifie si un véhicule peut avancer sans griller un feu ni entrer en collision.

        Args:
            voiture (dict): Dictionnaire décrivant le véhicule testé.

        Returns:
            bool: True si la voie est libre et autorisée, False si le véhicule doit s'arrêter.
        """
        item, dx, dy = voiture["item"], voiture["dx"], voiture["dy"]
        x, y = item.pos().x(), item.pos().y()
        nom_feu, calculer_distance = INFOS_SENS[(voiture["dx_initial"], voiture["dy_initial"])]

        # 1. Respect du feu rouge ou orange à l'approche de la ligne d'arrêt
        if 0 <= calculer_distance(x, y) <= ZONE_ARRET and self.etat_lumiere[nom_feu] != "vert":
            return False

        # 2. Anti-collision prédictif avec les autres véhicules proches
        for autre in self.voitures:
            if autre is voiture:
                continue
            ax, ay = autre["item"].pos().x(), autre["item"].pos().y()
            dist_actuelle = math.hypot(ax - x, ay - y)

            if dist_actuelle < 45:
                dist_future = math.hypot((ax + autre["dx"]) - (x + dx), (ay + autre["dy"]) - (y + dy))
                if dist_future < dist_actuelle:
                    # Cas A : Même voie (suivi de file) -> celui de derrière marque l'arrêt
                    if autre["dx_initial"] == voiture["dx_initial"] and autre["dy_initial"] == voiture["dy_initial"]:
                        if dx > 0 and ax > x:
                            return False
                        if dx < 0 and ax < x:
                            return False
                        if dy > 0 and ay > y:
                            return False
                        if dy < 0 and ay < y:
                            return False
                    # Cas B : Croisement -> priorité au véhicule le plus engagé au centre
                    else:
                        dist_centre_nous = math.hypot(380 - x, 280 - y)
                        dist_centre_autre = math.hypot(380 - ax, 280 - ay)
                        if dist_centre_autre < dist_centre_nous:
                            return False
                        elif dist_centre_autre == dist_centre_nous and id(autre) < id(voiture):
                            return False

        return True

    def _avancer_voitures(self):
        """Déplace chaque véhicule civil, gère l'écartement d'urgence et les virages à gauche."""
        marge = 80
        for voiture in self.voitures:
            item = voiture["item"]

            # En mode urgence, les véhicules sur l'axe de l'ambulance se décalent sur le bas-côté
            axes = {"ouest": ("dx_initial", 1), "est": ("dx_initial", -1),
                    "nord": ("dy_initial", 1), "sud": ("dy_initial", -1)}
            est_sur_chemin = False
            if self.mode == "urgence" and self.ambulance_direction in axes:
                cle, signe = axes[self.ambulance_direction]
                est_sur_chemin = voiture[cle] * signe > 0

            if est_sur_chemin != voiture["ecarte"]:
                sens = 1 if est_sur_chemin else -1
                if voiture["intention"] == "gauche":
                    sens *= -1
                dx0, dy0 = voiture["dx_initial"], voiture["dy_initial"]
                decalage_x = -12 * sens * (1 if dy0 > 0 else -1 if dy0 < 0 else 0)
                decalage_y = 12 * sens * (1 if dx0 > 0 else -1 if dx0 < 0 else 0)
                item.moveBy(decalage_x, decalage_y)
                voiture["ecarte"] = est_sur_chemin

            if not self._peut_avancer(voiture):
                continue

            dx, dy, x, y = voiture["dx"], voiture["dy"], item.pos().x(), item.pos().y()

            # Gestion des virages à gauche au centre de l'intersection
            if voiture["intention"] == "gauche" and not voiture["tourne"]:
                if dx > 0 and x >= 390:
                    voiture["dx"], voiture["dy"], voiture["tourne"], x = 0, -1.8, True, 390
                    item.setRotation(270)
                elif dx < 0 and x <= 370:
                    voiture["dx"], voiture["dy"], voiture["tourne"], x = 0, 1.8, True, 370
                    item.setRotation(90)
                elif dy > 0 and y >= 290:
                    voiture["dx"], voiture["dy"], voiture["tourne"], y = 1.8, 0, True, 290
                    item.setRotation(0)
                elif dy < 0 and y <= 270:
                    voiture["dx"], voiture["dy"], voiture["tourne"], y = -1.8, 0, True, 270
                    item.setRotation(180)

            x += voiture["dx"]
            y += voiture["dy"]

            # Réinjection cyclique du véhicule lorsqu'il sort de la scène
            if x > LARGEUR_SCENE + marge or x < -marge or y > HAUTEUR_SCENE + marge or y < -marge:
                voiture["dx"], voiture["dy"], voiture["tourne"] = voiture["dx_initial"], voiture["dy_initial"], False
                if voiture["dx_initial"] > 0:
                    x, y = -marge, (290 if voiture["intention"] == "gauche" else 310)
                    item.setRotation(0)
                elif voiture["dx_initial"] < 0:
                    x, y = LARGEUR_SCENE + marge, (270 if voiture["intention"] == "gauche" else 250)
                    item.setRotation(180)
                elif voiture["dy_initial"] > 0:
                    x, y = (370 if voiture["intention"] == "gauche" else 350), -marge
                    item.setRotation(90)
                elif voiture["dy_initial"] < 0:
                    x, y = (390 if voiture["intention"] == "gauche" else 410), HAUTEUR_SCENE + marge
                    item.setRotation(270)

            item.setPos(x, y)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = CtosMainWindow()
    fenetre.show()
    sys.exit(app.exec())
