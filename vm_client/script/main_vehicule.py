"""Contrôleur de l'interface embarquée du véhicule d'urgence sur la VM client."""

from ui.interface_vehicule import InterfaceVehicule


class MainVehicule(InterfaceVehicule):
    """Spécialisation réseau de InterfaceVehicule connectée au client TCP ctOS.

    Attributes:
        reseau (ClientReseau): Instance réseau utilisée pour signaler l'arrivée au carrefour.
    """

    def __init__(self, reseau, incident=None):
        """Initialise la fenêtre véhicule avec les détails de l'incident validé.

        Args:
            reseau (ClientReseau): Thread réseau actif vers le serveur ctOS.
            incident (dict | None): Dictionnaire contenant 'type_incident' et 'lieu'.
        """
        incident = incident or {}
        super().__init__(
            incident_type=incident.get("type_incident", "Intervention d'urgence"),
            lieu=incident.get("lieu", "Carrefour Rte de Bâle")
        )
        self.reseau = reseau
        self.btn_statut.setText("VÉHICULE PRÊT")
        self.texte_explicatif.setText("Ordre reçu du centre de contrôle. Départ en cours.")

    def calculer_prochaine_position(self):
        """Interpole la position GPS du véhicule et notifie le serveur à l'arrivée."""
        self.progression += 0.005
        # Lorsque le véhicule atteint 98 % du trajet, déclenche l'événement ARRIVE_CARREFOUR
        if self.progression >= 0.98:
            self.timer_mouvement.stop()
            self.btn_statut.setText("CARREFOUR ATTEINT")
            self.texte_explicatif.setText("✓ Arrivée au carrefour. Transmission au centre de contrôle.")
            self.reseau.send({"action": "ARRIVE_CARREFOUR"})
            self.hide()
            return
        # Interpolation linéaire entre les coordonnées GPS de départ et d'arrivée
        self.lat_actuelle = self.lat_vehicule_depart + (self.lat_incident - self.lat_vehicule_depart) * self.progression
        self.lon_actuelle = self.lon_vehicule_depart + (self.lon_incident - self.lon_vehicule_depart) * self.progression
        self.gps.mettre_a_jour_position(self.lat_actuelle, self.lon_actuelle)
