"""
Stratèj — État partagé d'une partie (soumissions, codes d'accès, persistance).
Module séparé pour une sérialisation fiable sur disque.
"""
import os
import pickle
import random
import string
from copy import deepcopy

from stratej_moteur_v2 import Simulation

FICHIER_PARTIE = "stratej_partie_v2.pkl"


class Partie:
    def __init__(self, noms, parametres, code_animateur, poids_classement=None):
        self.sim = Simulation(parametres, noms)
        self.code_animateur = code_animateur.strip().upper()
        self.codes = {n: self._code() for n in noms}
        self.soumissions = {}          # nom -> Decisions du trimestre en cours
        self.historique = []           # résultats de chaque ronde
        self.poids_classement = dict(poids_classement or Simulation.POIDS_DEFAUT)
        self.classements = []          # instantané du classement après chaque ronde

    @staticmethod
    def _code():
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))

    @property
    def terminee(self):
        return self.sim.t >= self.sim.par.nb_trimestres

    def soumettre(self, nom, decisions):
        self.soumissions[nom] = deepcopy(decisions)

    def lancer_trimestre(self):
        resultat = self.sim.jouer_ronde(self.soumissions)
        cl = self.sim.classement(self.poids_classement)
        resultat["classement"] = cl
        self.classements.append({"trimestre": self.sim.t, "classement": cl})
        self.historique.append(resultat)
        self.soumissions = {}
        return resultat


def sauvegarder(partie):
    with open(FICHIER_PARTIE, "wb") as f:
        pickle.dump(partie, f)


def charger():
    if os.path.exists(FICHIER_PARTIE):
        try:
            with open(FICHIER_PARTIE, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
    return None


# ----------------------------------------------------------------------
# Gestion de PLUSIEURS parties simultanées (un animateur, plusieurs groupes)
# ----------------------------------------------------------------------
FICHIER_PARTIES = "stratej_parties.pkl"


# Registre unique en mémoire : vit dans CE module, donc les objets et la
# classe Partie proviennent toujours de la même instance de module (sinon
# pickle refuse de sérialiser : « it's not the same object as ... »).
_REGISTRE = None


def registre() -> dict:
    """Dictionnaire {nom de partie: Partie} partagé par toutes les sessions."""
    global _REGISTRE
    if _REGISTRE is None:
        _REGISTRE = charger_parties()
    return _REGISTRE


def sauvegarder_parties(parties: dict = None):
    """Sauvegarde best-effort : en cas d'échec (disque en lecture seule sur
    certains hébergements, conflit de rechargement de module), la partie reste
    intacte en mémoire et l'application continue de fonctionner."""
    parties = registre() if parties is None else parties
    try:
        with open(FICHIER_PARTIES, "wb") as f:
            pickle.dump(parties, f)
        return True
    except Exception:
        return False


def charger_parties() -> dict:
    if os.path.exists(FICHIER_PARTIES):
        try:
            with open(FICHIER_PARTIES, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}
    # Migration : si une ancienne sauvegarde mono-partie existe, on la reprend
    ancienne = charger()
    return {"Partie 1": ancienne} if ancienne is not None else {}
