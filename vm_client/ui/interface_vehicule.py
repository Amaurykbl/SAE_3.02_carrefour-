"""Interface graphique du terminal embarqué du véhicule d'urgence avec carte Leaflet."""

import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView


# ==========================================
# 2. LA CARTE WEB (LEAFLET)
# ==========================================
class CarteReelle(QWebEngineView):
    """Widget QWebEngineView affichant une carte OpenStreetMap/Leaflet interactive."""

    def __init__(self, lat_depart, lon_depart, lat_arrivee, lon_arrivee):
        """Charge la page HTML Leaflet centrée entre le départ et le lieu d'incident.

        Args:
            lat_depart (float): Latitude initiale du véhicule de secours.
            lon_depart (float): Longitude initiale du véhicule de secours.
            lat_arrivee (float): Latitude du carrefour cible.
            lon_arrivee (float): Longitude du carrefour cible.
        """
        super().__init__()
        # Autorise le HTML local injecté via setHtml() à charger Leaflet et les tuiles OSM distantes
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        centre_lat = (lat_depart + lat_arrivee) / 2
        centre_lon = (lon_depart + lon_arrivee) / 2

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>
                body {{ margin: 0; padding: 0; }}
                /* Filtre CSS inversant les tuiles claires pour obtenir un rendu sombre type ctOS */
                #map {{ height: 100vh; width: 100vw; filter: invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%); }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map = L.map('map').setView([{centre_lat}, {centre_lon}], 14);
                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19 }}).addTo(map);

                // Tracé pointillé cyan représentant l'itinéraire d'intervention
                L.polyline([[{lat_depart}, {lon_depart}], [{lat_arrivee}, {lon_arrivee}]], 
                    {{color: '#00bfff', dashArray: '10', weight: 3}}).addTo(map);

                // Marqueur rouge sur le point d'incident
                L.circleMarker([{lat_arrivee}, {lon_arrivee}], 
                    {{radius: 10, color: '#E5544B', fillColor: '#E5544B', fillOpacity: 0.8}}).addTo(map);

                // Marqueur mobile représentant l'ambulance
                var vehicule = L.circleMarker([{lat_depart}, {lon_depart}], 
                    {{radius: 8, color: '#00bfff', fillColor: '#ffffff', fillOpacity: 1, weight: 3}}).addTo(map);

                function deplacerVehicule(lat, lon) {{
                    vehicule.setLatLng([lat, lon]);
                }}
            </script>
        </body>
        </html>
        """
        self.setHtml(html_content)

    def mettre_a_jour_position(self, lat, lon):
        """Appelle la fonction JavaScript Leaflet pour déplacer le marqueur véhicule.

        Args:
            lat (float): Nouvelle latitude du véhicule.
            lon (float): Nouvelle longitude du véhicule.
        """
        self.page().runJavaScript(f"deplacerVehicule({lat}, {lon});")


# ==========================================
# 3. L'INTERFACE DU VÉHICULE
# ==========================================
class InterfaceVehicule(QWidget):
    """Fenêtre du terminal embarqué affichant les consignes d'intervention et le GPS.

    Attributes:
        incident_type (str): Nature de l'intervention affichée à l'écran.
        lieu (str): Destination de l'intervention.
        gps (CarteReelle): Composant cartographique Leaflet.
        timer_mouvement (QTimer): Minuteur cadencant le déplacement du véhicule.
    """

    def __init__(self, incident_type="Accident de la route", lieu="Carrefour Rte de Bâle"):
        """Initialise les coordonnées GPS, l'interface graphique et le timer d'animation.

        Args:
            incident_type (str): Libellé de l'incident.
            lieu (str): Lieu de l'incident.
        """
        super().__init__()
        self.setWindowTitle("ctOS - Terminal Embarqué (Véhicule d'Urgence)")
        self.setGeometry(200, 150, 1000, 600)

        self.incident_type = incident_type
        self.lieu = lieu

        # Coordonnées GPS de départ et d'arrivée (secteur Mulhouse)
        self.lat_vehicule_depart, self.lon_vehicule_depart = 47.7495, 7.3353
        self.lat_incident, self.lon_incident = 47.7300, 7.3100

        self.lat_actuelle = self.lat_vehicule_depart
        self.lon_actuelle = self.lon_vehicule_depart

        self.interface()

        # Timer cadencé toutes les 100 ms pour l'interpolation fluide du déplacement
        self.timer_mouvement = QTimer()
        self.timer_mouvement.timeout.connect(self.calculer_prochaine_position)
        self.progression = 0.0

    def interface(self):
        """Construit la mise en page du terminal embarqué (panneau d'infos + carte GPS)."""
        titre = QLabel("TERMINAL EMBARQUÉ - UNITÉ D'INTERVENTION")
        titre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titre.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #ffffff; background-color: #00bfff; padding: 10px; border-radius: 5px; margin-bottom: 20px;")

        panneau_infos = QFrame()
        panneau_infos.setObjectName("panneau")
        layout_infos = QVBoxLayout()

        alerte = QLabel("🚨 NOUVELLE INTERVENTION")
        alerte.setStyleSheet("color: #E5544B; font-size: 20px; font-weight: bold;")

        info_incident = QLabel(f"<b>Type :</b> {self.incident_type}<br><b>Cible :</b> {self.lieu}")
        info_incident.setStyleSheet("font-size: 16px; color: #ffffff;")

        titre_ctos = QLabel("\nASSISTANCE ctOS ACTIVÉE :")
        titre_ctos.setStyleSheet("color: #00bfff; font-size: 14px; font-weight: bold;")

        self.texte_explicatif = QLabel(
            "⏳ Connexion au serveur CTOS en cours...\n"
            "Veuillez patienter."
        )
        self.texte_explicatif.setStyleSheet("color: #FFB300; font-size: 14px; line-height: 1.5; font-weight: bold;")

        layout_infos.addWidget(alerte)
        layout_infos.addWidget(info_incident)
        layout_infos.addWidget(titre_ctos)
        layout_infos.addWidget(self.texte_explicatif)
        layout_infos.addStretch()
        panneau_infos.setLayout(layout_infos)

        panneau_gps = QFrame()
        panneau_gps.setObjectName("panneau")
        layout_gps = QVBoxLayout()

        titre_gps = QLabel("GPS - SUIVI EN TEMPS RÉEL")
        titre_gps.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")

        self.gps = CarteReelle(self.lat_vehicule_depart, self.lon_vehicule_depart, self.lat_incident, self.lon_incident)

        layout_gps.addWidget(titre_gps)
        layout_gps.addWidget(self.gps)
        panneau_gps.setLayout(layout_gps)

        self.btn_statut = QPushButton("EN ATTENTE D'ORDRES")
        self.btn_statut.setEnabled(False)

        contenu_central = QHBoxLayout()
        contenu_central.addWidget(panneau_infos, 1)
        contenu_central.addWidget(panneau_gps, 2)

        layout_principal = QVBoxLayout()
        layout_principal.setContentsMargins(30, 25, 30, 30)
        layout_principal.addWidget(titre)
        layout_principal.addLayout(contenu_central)
        layout_principal.addSpacing(20)
        layout_principal.addWidget(self.btn_statut)
        self.setLayout(layout_principal)

        self.setStyleSheet("""
            QWidget { background-color: #080c10; font-family: Arial; }
            QFrame#panneau { background-color: #10161c; border: 1px solid #26323c; border-radius: 10px; padding: 20px; }
            QPushButton { background-color: #00bfff; border: none; border-radius: 6px; padding: 15px; color: #080c10; font-size: 16px; font-weight: bold; }
            QPushButton:disabled { background-color: #26323c; color: #68737d; }
        """)

    def demarrer_trajet(self):
        """Active les visuels d'urgence et démarre le minuteur de déplacement sur la carte."""
        self.btn_statut.setText("VÉHICULE EN ROUTE - PRIORITÉ ABSOLUE")
        self.btn_statut.setStyleSheet("background-color: #E5544B; color: white;")

        self.texte_explicatif.setText(
            "✓ Véhicule en approche.\n"
            "✓ Protocole 'Onde Verte' engagé.\n"
            "⚠️ Attention : Blocage des axes\n   transversaux en cours."
        )
        self.texte_explicatif.setStyleSheet("color: #E5544B; font-size: 14px; font-weight: bold;")

        # Lance le mouvement de la carte (toutes les 100 ms)
        self.timer_mouvement.start(100)

    def calculer_prochaine_position(self):
        """Calcule la position intermédiaire suivante et met à jour le marqueur GPS."""
        self.progression += 0.005

        # Le véhicule est arrivé à destination
        if self.progression >= 0.98:
            self.timer_mouvement.stop()
            self.btn_statut.setText("CARREFOUR ATTEINT - BASCULEMENT CAMÉRA")
            self.texte_explicatif.setText("✓ Objectif atteint.\n✓ Prise de contrôle du carrefour.")

            # --- ORDRE RÉSEAU ---
            # Informe le serveur de l'arrivée au carrefour
            self.thread_reseau.envoyer_message("ARRIVE_CARREFOUR")
            return

        self.lat_actuelle = self.lat_vehicule_depart + (self.lat_incident - self.lat_vehicule_depart) * self.progression
        self.lon_actuelle = self.lon_vehicule_depart + (self.lon_incident - self.lon_vehicule_depart) * self.progression
        self.gps.mettre_a_jour_position(self.lat_actuelle, self.lon_actuelle)


# Alias de compatibilité avec les anciens imports du projet
interfaceVehicule = InterfaceVehicule

if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = InterfaceVehicule()
    fenetre.show()
    sys.exit(app.exec())
