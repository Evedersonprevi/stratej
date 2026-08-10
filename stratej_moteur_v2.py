"""
STRATÈJ — Moteur de simulation d'entreprise (version 1 — multi-produits)
=========================================================================
Nouveautés par rapport à la v0 :
  - PLUSIEURS PRODUITS : chaque produit a son propre marché (demande, prix de
    référence, élasticités) ; les équipes décident production, prix, marketing
    et R&D pour chacun. La capacité de production est partagée entre produits.
  - COÛT UNITAIRE DYNAMIQUE : coût de base x inflation x indice de coût du
    trimestre (conjoncture des intrants, écrit par l'animateur) x (1 - gain
    d'efficacité issu de la R&D procédé, plafonné). Visible par les équipes.
  - DEUX TYPES DE R&D par produit : R&D qualité (attractivité) et R&D procédé
    (réduction du coût unitaire, à rendements décroissants).
  - FORCE DE VENTE : budget de salaires des agents au niveau de l'entreprise ;
    mieux payer sa force de vente augmente l'attractivité de tous les produits
    (à rendements décroissants), le prix restant déterminant.
  - PARAMÈTRES ENTIÈREMENT CONFIGURABLES par l'animateur à la création
    (capacité initiale, encaisse, coûts fixes, taux, produits, etc.).

Règles conservées : reconduction si non-soumission, dette d'urgence,
redistribution de la demande insatisfaite, stock invendu conservé (avec coût
de stockage), bilan vérifié à chaque clôture.

Monnaie : gourdes (HTG). Une ronde = un trimestre.
"""

from dataclasses import dataclass, field
import math
from copy import deepcopy


# ----------------------------------------------------------------------
# Paramètres d'un produit (marché propre à chaque produit)
# ----------------------------------------------------------------------
@dataclass
class Produit:
    nom: str = "Produit A"
    demande_base: float = 130_000       # unités/trimestre au prix de référence
    prix_reference: float = 250.0       # HTG / unité
    cout_variable_base: float = 100.0   # HTG / unité (avant inflation/indice/efficacité)
    elasticite_marche: float = 0.6      # sensibilité de la demande totale au prix moyen
    elasticite_prix: float = 3.0        # sensibilité des parts de marché aux prix relatifs
    poids_qualite: float = 1.2
    poids_marketing: float = 0.8
    marketing_reference: float = 1_500_000
    rd_reference: float = 1_000_000
    rendement_rd_qualite: float = 0.15  # points de qualité par budget de référence
    depreciation_qualite: float = 0.05
    rendement_rd_procede: float = 0.06  # vitesse d'acquisition du gain d'efficacité
    efficacite_max: float = 0.35        # réduction maximale du coût unitaire (35 %)


# ----------------------------------------------------------------------
# Paramètres généraux du scénario
# ----------------------------------------------------------------------
@dataclass
class Parametres:
    nb_trimestres: int = 8
    produits: list = field(default_factory=lambda: [Produit()])
    conjoncture: list = field(default_factory=list)   # multiplicateurs de DEMANDE
    indice_cout: list = field(default_factory=list)   # multiplicateurs de COÛT des intrants
    croissance_trimestrielle: float = 0.01
    inflation_trimestrielle: float = 0.03
    # Coûts communs
    couts_fixes: float = 1_200_000
    cout_stockage_unitaire: float = 8.0
    # Capacité (partagée entre produits) et investissement
    capacite_initiale: float = 30_000
    cout_capacite: float = 400.0
    duree_amortissement: int = 20
    # Force de vente (salaires des agents)
    force_vente_reference: float = 800_000   # budget donnant un effet "normal"
    poids_force_vente: float = 0.6
    # Finance
    encaisse_initiale: float = 8_000_000
    taux_interet: float = 0.03
    taux_urgence: float = 0.08
    taux_impot: float = 0.30
    # Réalisme des prix et de l'écoulement
    tolerance_prix: float = 0.25    # écart toléré au-dessus du prix de référence (25 %)
    penalite_prix: float = 4.0      # sévérité de la pénalité au-delà de la tolérance
    taux_report: float = 0.60       # part de la demande insatisfaite qui se reporte
                                    # sur les concurrents (le reste renonce à l'achat)
    attrait_exterieur: float = 0.15 # attractivité de l'option « ne pas acheter » :
                                    # si les offres restantes sont peu attrayantes
                                    # (prix excessifs), les clients renoncent
    # Libellés lisibles des conjonctures (affichés aux joueurs)
    conjoncture_labels: list = field(default_factory=list)
    indice_cout_labels: list = field(default_factory=list)

    def conjoncture_t(self, t):
        return self.conjoncture[t] if t < len(self.conjoncture) else 1.0

    def indice_cout_t(self, t):
        return self.indice_cout[t] if t < len(self.indice_cout) else 1.0

    def label_conjoncture_t(self, t):
        if t < len(self.conjoncture_labels):
            return self.conjoncture_labels[t]
        v = self.conjoncture_t(t)
        if abs(v - 1.0) < 0.02:
            return "Stable"
        return "Expansion" if v > 1.0 else "Récession"

    def label_indice_cout_t(self, t):
        if t < len(self.indice_cout_labels):
            return self.indice_cout_labels[t]
        v = self.indice_cout_t(t)
        if abs(v - 1.0) < 0.02:
            return "Coûts stables"
        return "Hausse des coûts" if v > 1.0 else "Baisse des coûts"

    def couts_fixes_t(self, t):
        return self.couts_fixes * (1 + self.inflation_trimestrielle) ** t


# ----------------------------------------------------------------------
# Décisions
# ----------------------------------------------------------------------
@dataclass
class DecisionsProduit:
    production: float = 0.0
    prix: float = 250.0
    marketing: float = 0.0
    rd_qualite: float = 0.0
    rd_procede: float = 0.0


@dataclass
class Decisions:
    produits: dict = field(default_factory=dict)   # nom_produit -> DecisionsProduit
    force_vente: float = 0.0                        # salaires des agents (trimestre)
    invest_capacite: float = 0.0
    nouvel_emprunt: float = 0.0
    remboursement: float = 0.0


# ----------------------------------------------------------------------
# État par produit d'une entreprise
# ----------------------------------------------------------------------
@dataclass
class EtatProduit:
    stock_unites: float = 0.0
    stock_valeur: float = 0.0
    qualite: float = 0.0
    efficacite: float = 0.0     # réduction acquise du coût unitaire (0 à efficacite_max)


@dataclass
class Entreprise:
    nom: str
    encaisse: float = 0.0
    capacite: float = 0.0
    immobilisations_brutes: float = 0.0
    amortissement_cumule: float = 0.0
    dette: float = 0.0
    dette_urgence: float = 0.0
    capitaux_propres: float = 0.0
    profit_cumule: float = 0.0
    etats_produits: dict = field(default_factory=dict)   # nom_produit -> EtatProduit
    parts_historiques: list = field(default_factory=list)
    dernieres_decisions: Decisions = field(default_factory=Decisions)
    rapports: list = field(default_factory=list)

    @property
    def immobilisations_nettes(self):
        return self.immobilisations_brutes - self.amortissement_cumule

    @property
    def stock_valeur_totale(self):
        return sum(ep.stock_valeur for ep in self.etats_produits.values())

    @property
    def stock_unites_total(self):
        return sum(ep.stock_unites for ep in self.etats_produits.values())

    @property
    def actif_total(self):
        return self.encaisse + self.stock_valeur_totale + self.immobilisations_nettes


# ----------------------------------------------------------------------
# Coût unitaire courant d'un produit pour une équipe
# ----------------------------------------------------------------------
def cout_unitaire(par: Parametres, prod: Produit, ep: EtatProduit, t: int) -> float:
    """Coût de base x inflation x indice de coût du trimestre x (1 - efficacité)."""
    return (prod.cout_variable_base
            * (1 + par.inflation_trimestrielle) ** t
            * par.indice_cout_t(t)
            * (1 - ep.efficacite))


# ----------------------------------------------------------------------
# Moteur de marché (par produit)
# ----------------------------------------------------------------------
def demande_totale_produit(par: Parametres, prod: Produit, t: int, prix_moyen: float) -> float:
    base = prod.demande_base * (1 + par.croissance_trimestrielle) ** t
    effet_prix = (prod.prix_reference / max(prix_moyen, 1.0)) ** prod.elasticite_marche
    return base * par.conjoncture_t(t) * effet_prix


def attractivite(par: Parametres, prod: Produit, dp: DecisionsProduit,
                 ep: EtatProduit, force_vente: float) -> float:
    a_prix = (prod.prix_reference / max(dp.prix, 1.0)) ** prod.elasticite_prix
    a_qualite = (1 + max(ep.qualite, 0.0)) ** prod.poids_qualite
    effet_mkt = (max(dp.marketing, 0.0) / prod.marketing_reference) ** 0.5
    a_marketing = (1 + effet_mkt) ** prod.poids_marketing
    effet_fv = (max(force_vente, 0.0) / par.force_vente_reference) ** 0.5
    a_force_vente = (1 + effet_fv) ** par.poids_force_vente
    # Pénalité de prix excessif : au-delà de (1 + tolérance) x prix de référence,
    # les clients désertent rapidement, même en pénurie chez les concurrents.
    penalite = 1.0
    ratio = dp.prix / max(prod.prix_reference, 1.0)
    if ratio > 1.0 + par.tolerance_prix:
        penalite = math.exp(-par.penalite_prix * (ratio - 1.0 - par.tolerance_prix))
    return a_prix * a_qualite * a_marketing * a_force_vente * penalite


def repartir_demande(demande: float, attraits: list, offres: list,
                     taux_report: float = 1.0,
                     attrait_exterieur: float = 0.0) -> list:
    """La demande non servie par une équipe en rupture est PARTIELLEMENT
    redistribuée (taux_report) aux équipes qui ont encore de l'offre :
    une partie des clients renonce simplement à l'achat."""
    n = len(attraits)
    ventes = [0.0] * n
    offre_restante = list(offres)
    demande_restante = demande
    for _ in range(12):
        actifs = [i for i in range(n) if offre_restante[i] > 1e-9]
        if not actifs or demande_restante <= 1e-6:
            break
        total_attr = sum(attraits[i] for i in actifs) + attrait_exterieur
        if total_attr <= 0:
            break
        # Une partie des clients choisit l'option extérieure (ne pas acheter)
        perdu = demande_restante * attrait_exterieur / total_attr
        servi = 0.0
        for i in actifs:
            alloc = demande_restante * attraits[i] / total_attr
            vendu = min(alloc, offre_restante[i])
            ventes[i] += vendu
            offre_restante[i] -= vendu
            servi += vendu
        demande_restante = max(demande_restante - servi - perdu, 0.0) * taux_report
        if servi <= 1e-9:
            break
    return ventes


# ----------------------------------------------------------------------
# Validation des décisions
# ----------------------------------------------------------------------
def valider(par: Parametres, e: Entreprise, d: Decisions) -> tuple:
    d = deepcopy(d)
    notes = []
    noms_produits = [p.nom for p in par.produits]
    # Décisions produit manquantes -> zéro production, prix de référence
    for p in par.produits:
        if p.nom not in d.produits:
            d.produits[p.nom] = DecisionsProduit(prix=p.prix_reference)
    # Nettoyage produit par produit
    for p in par.produits:
        dp = d.produits[p.nom]
        if dp.prix <= 0:
            dp.prix = p.prix_reference
            notes.append(f"{p.nom} : prix invalide, ramené au prix de référence.")
        dp.production = max(dp.production, 0.0)
        dp.marketing = max(dp.marketing, 0.0)
        dp.rd_qualite = max(dp.rd_qualite, 0.0)
        dp.rd_procede = max(dp.rd_procede, 0.0)
    # Capacité partagée : production totale plafonnée au prorata
    prod_totale = sum(d.produits[nm].production for nm in noms_produits)
    if prod_totale > e.capacite and prod_totale > 0:
        ratio = e.capacite / prod_totale
        for nm in noms_produits:
            d.produits[nm].production *= ratio
        notes.append(f"Production totale plafonnée à la capacité ({e.capacite:,.0f} u), "
                     "répartie au prorata.")
    # Autres bornes
    d.force_vente = max(d.force_vente, 0.0)
    d.invest_capacite = max(d.invest_capacite, 0.0)
    d.nouvel_emprunt = max(d.nouvel_emprunt, 0.0)
    d.remboursement = min(max(d.remboursement, 0.0), e.dette)
    # Dépenses discrétionnaires plafonnées aux liquidités prévisibles
    dispo = e.encaisse + d.nouvel_emprunt
    discretionnaire = (d.force_vente + d.invest_capacite
                       + sum(dp.marketing + dp.rd_qualite + dp.rd_procede
                             for dp in d.produits.values()))
    if discretionnaire > dispo and discretionnaire > 0:
        ratio = max(dispo, 0.0) / discretionnaire
        d.force_vente *= ratio
        d.invest_capacite *= ratio
        for dp in d.produits.values():
            dp.marketing *= ratio
            dp.rd_qualite *= ratio
            dp.rd_procede *= ratio
        notes.append("Budgets (marketing, R&D, force de vente, investissement) "
                     "réduits aux liquidités disponibles.")
    return d, notes


# ----------------------------------------------------------------------
# Simulation
# ----------------------------------------------------------------------
class Simulation:
    def __init__(self, parametres: Parametres, noms_equipes: list):
        self.par = parametres
        self.t = 0
        self.bulletins = []
        self.equipes = []
        for nom in noms_equipes:
            e = Entreprise(nom=nom)
            e.encaisse = parametres.encaisse_initiale
            e.capacite = parametres.capacite_initiale
            e.immobilisations_brutes = parametres.capacite_initiale * parametres.cout_capacite
            e.capitaux_propres = e.encaisse + e.immobilisations_brutes
            e.etats_produits = {p.nom: EtatProduit() for p in parametres.produits}
            e.dernieres_decisions = Decisions(
                produits={p.nom: DecisionsProduit(prix=p.prix_reference)
                          for p in parametres.produits})
            self.equipes.append(e)

    # ------------------------------------------------------------------
    def couts_unitaires_courants(self, e: Entreprise) -> dict:
        """Coût unitaire de production de chaque produit pour cette équipe,
        au trimestre courant (affiché aux équipes avant leurs décisions)."""
        return {p.nom: cout_unitaire(self.par, p, e.etats_produits[p.nom], self.t)
                for p in self.par.produits}

    # ------------------------------------------------------------------
    def jouer_ronde(self, decisions_par_equipe: dict) -> dict:
        par, t = self.par, self.t
        n = len(self.equipes)

        # 1) Collecte + validation (reconduction si non-soumission)
        decisions, ajustements = [], []
        for e in self.equipes:
            d_brutes = decisions_par_equipe.get(e.nom)
            if d_brutes is None:
                d_brutes = deepcopy(e.dernieres_decisions)
                notes0 = ["Aucune soumission : décisions précédentes reconduites."]
            else:
                notes0 = []
            d, notes = valider(par, e, d_brutes)
            decisions.append(d)
            ajustements.append(notes0 + notes)

        # 2) Marché produit par produit
        marches = {}
        ventes_par_produit = {}
        for p in par.produits:
            prix_moyen = sum(decisions[i].produits[p.nom].prix for i in range(n)) / n
            D = demande_totale_produit(par, p, t, prix_moyen)
            attraits = [attractivite(par, p, decisions[i].produits[p.nom],
                                     self.equipes[i].etats_produits[p.nom],
                                     decisions[i].force_vente) for i in range(n)]
            offres = [self.equipes[i].etats_produits[p.nom].stock_unites
                      + decisions[i].produits[p.nom].production for i in range(n)]
            ventes = repartir_demande(D, attraits, offres, par.taux_report,
                                      par.attrait_exterieur)
            marches[p.nom] = {"demande": D, "prix_moyen": prix_moyen, "offres": offres}
            ventes_par_produit[p.nom] = ventes

        # 3) Clôture financière de chaque équipe
        resultats = []
        demande_totale_marche = sum(m["demande"] for m in marches.values())
        for i, e in enumerate(self.equipes):
            ventes_i = {p.nom: ventes_par_produit[p.nom][i] for p in par.produits}
            resultats.append(self._cloture_trimestre(e, decisions[i], ventes_i, t))
            e.dernieres_decisions = deepcopy(decisions[i])
            ventes_tot = sum(ventes_i.values())
            e.parts_historiques.append(
                ventes_tot / demande_totale_marche if demande_totale_marche > 0 else 0.0)

        # 4) Bulletin de marché (public, partiel) — par produit
        bulletin = {
            "trimestre": t + 1,
            "conjoncture": par.conjoncture_t(t),
            "indice_cout": par.indice_cout_t(t),
            "conjoncture_label": par.label_conjoncture_t(t),
            "indice_cout_label": par.label_indice_cout_t(t),
            "produits": {},
        }
        for p in par.produits:
            bulletin["produits"][p.nom] = {
                "demande_totale": marches[p.nom]["demande"],
                "prix_moyen": marches[p.nom]["prix_moyen"],
                "equipes": [{
                    "nom": self.equipes[i].nom,
                    "prix": decisions[i].produits[p.nom].prix,
                    "part_marche": (ventes_par_produit[p.nom][i] / marches[p.nom]["demande"]
                                    if marches[p.nom]["demande"] > 0 else 0.0),
                    "rupture_stock": (marches[p.nom]["offres"][i]
                                      - ventes_par_produit[p.nom][i]) < 1e-6,
                } for i in range(n)],
            }
        self.bulletins.append(bulletin)

        for i, e in enumerate(self.equipes):
            resultats[i]["ajustements"] = ajustements[i]
            e.rapports.append(resultats[i])

        self.t += 1
        return {"bulletin": bulletin, "rapports": {e.nom: e.rapports[-1] for e in self.equipes}}

    # ------------------------------------------------------------------
    def _cloture_trimestre(self, e: Entreprise, d: Decisions, ventes: dict, t: int) -> dict:
        par = self.par
        rev_prec = e.rapports[-1]["etat_resultats"]["revenus"] if e.rapports else None
        detail_produits = {}
        revenus_tot = cmv_tot = cout_production_tot = 0.0
        marketing_tot = rd_tot = 0.0

        for p in par.produits:
            dp = d.produits[p.nom]
            ep = e.etats_produits[p.nom]
            cu = cout_unitaire(par, p, ep, t)
            cout_production = dp.production * cu
            ep.stock_unites += dp.production
            ep.stock_valeur += cout_production
            cum = ep.stock_valeur / ep.stock_unites if ep.stock_unites > 0 else 0.0
            v = ventes[p.nom]
            cmv = v * cum
            ep.stock_unites -= v
            ep.stock_valeur -= cmv
            if ep.stock_unites < 1e-6:
                ep.stock_unites, ep.stock_valeur = 0.0, 0.0
            revenus = v * dp.prix

            # Effets de la R&D (pour les trimestres suivants)
            ep.qualite = (ep.qualite * (1 - p.depreciation_qualite)
                          + p.rendement_rd_qualite * (dp.rd_qualite / p.rd_reference))
            marge_restante = (p.efficacite_max - ep.efficacite) / p.efficacite_max
            ep.efficacite = min(
                p.efficacite_max,
                ep.efficacite + p.rendement_rd_procede
                * (dp.rd_procede / p.rd_reference) * max(marge_restante, 0.0))

            revenus_tot += revenus
            cmv_tot += cmv
            cout_production_tot += cout_production
            marketing_tot += dp.marketing
            rd_tot += dp.rd_qualite + dp.rd_procede
            detail_produits[p.nom] = {
                "ventes": v, "prix": dp.prix, "revenus": revenus, "cmv": cmv,
                "marge_brute": revenus - cmv, "cout_unitaire": cu,
                "stock_unites": ep.stock_unites, "qualite": ep.qualite,
                "efficacite": ep.efficacite,
            }

        couts_fixes = par.couts_fixes_t(t)
        stockage = e.stock_unites_total * par.cout_stockage_unitaire
        amortissement = min(e.immobilisations_brutes / par.duree_amortissement,
                            e.immobilisations_nettes)
        interets = e.dette * par.taux_interet + e.dette_urgence * par.taux_urgence

        ebt = (revenus_tot - cmv_tot - couts_fixes - marketing_tot - rd_tot
               - d.force_vente - stockage - amortissement - interets)
        impot = max(ebt, 0.0) * par.taux_impot
        benefice_net = ebt - impot

        e.encaisse += (revenus_tot - cout_production_tot - couts_fixes - marketing_tot
                       - rd_tot - d.force_vente - stockage - interets - impot
                       - d.invest_capacite + d.nouvel_emprunt - d.remboursement)
        e.dette += d.nouvel_emprunt - d.remboursement

        urgence_tiree = 0.0
        if e.encaisse < 0:
            urgence_tiree = -e.encaisse
            e.dette_urgence += urgence_tiree
            e.encaisse = 0.0
        elif e.dette_urgence > 0 and e.encaisse > 0:
            r = min(e.encaisse, e.dette_urgence)
            e.dette_urgence -= r
            e.encaisse -= r

        e.immobilisations_brutes += d.invest_capacite
        e.amortissement_cumule += amortissement
        e.capacite += d.invest_capacite / par.cout_capacite

        e.capitaux_propres += benefice_net
        e.profit_cumule += benefice_net

        # Ratios financiers du trimestre
        actif = e.actif_total
        ratios = {
            "marge_nette": benefice_net / revenus_tot if revenus_tot > 0 else 0.0,
            "roe": benefice_net / e.capitaux_propres if e.capitaux_propres > 0 else 0.0,
            "roa": benefice_net / actif if actif > 0 else 0.0,
            "rotation_actif": revenus_tot / actif if actif > 0 else 0.0,
            "rotation_stocks": (cmv_tot / e.stock_valeur_totale
                                if e.stock_valeur_totale > 1e-6 else None),
            "dette_actif": (e.dette + e.dette_urgence) / actif if actif > 0 else 0.0,
            "couverture_interets": ((ebt + interets) / interets
                                    if interets > 1e-6 else None),
            "croissance_revenus": (revenus_tot / rev_prec - 1.0
                                   if rev_prec and rev_prec > 0 else None),
        }

        ecart = e.actif_total - (e.dette + e.dette_urgence + e.capitaux_propres)
        assert abs(ecart) < 1.0, f"Bilan déséquilibré ({e.nom}) : écart {ecart:,.2f}"

        return {
            "trimestre": t + 1,
            "decisions": deepcopy(d),
            "produits": detail_produits,
            "etat_resultats": {
                "revenus": revenus_tot, "cmv": cmv_tot, "couts_fixes": couts_fixes,
                "marketing": marketing_tot, "rd": rd_tot, "force_vente": d.force_vente,
                "stockage": stockage, "amortissement": amortissement,
                "interets": interets, "benefice_avant_impot": ebt, "impot": impot,
                "benefice_net": benefice_net,
            },
            "bilan": {
                "encaisse": e.encaisse, "stocks": e.stock_valeur_totale,
                "immobilisations_nettes": e.immobilisations_nettes,
                "actif_total": e.actif_total,
                "dette": e.dette, "dette_urgence": e.dette_urgence,
                "capitaux_propres": e.capitaux_propres,
            },
            "ratios": ratios,
            "indicateurs": {
                "stock_unites": e.stock_unites_total, "capacite": e.capacite,
                "dette_urgence_tiree": urgence_tiree, "profit_cumule": e.profit_cumule,
            },
        }

    # ------------------------------------------------------------------
    POIDS_DEFAUT = {"rentabilite": 30, "solvabilite": 20, "gestion": 15,
                    "croissance": 15, "part_marche": 20}

    def criteres(self) -> list:
        """Valeurs brutes des critères de classement pour chaque équipe."""
        lignes = []
        for e in self.equipes:
            revs = [r["etat_resultats"]["revenus"] for r in e.rapports]
            rotations = [r["ratios"]["rotation_actif"] for r in e.rapports
                         if r.get("ratios")]
            croissance = (revs[-1] / revs[0] - 1.0
                          if len(revs) >= 2 and revs[0] > 0 else 0.0)
            lignes.append({
                "nom": e.nom,
                "rentabilite": e.profit_cumule,
                "solvabilite": (e.capitaux_propres / e.actif_total
                                if e.actif_total > 0 else 0.0),
                "gestion": sum(rotations) / len(rotations) if rotations else 0.0,
                "croissance": croissance,
                "part_marche": (sum(e.parts_historiques)
                                / max(len(e.parts_historiques), 1)),
            })
        return lignes

    def classement(self, poids: dict = None) -> list:
        """Score composite : chaque critère est normalisé entre 0 et 1 puis
        pondéré selon les poids choisis par l'animateur (objectif du cours)."""
        poids = {**self.POIDS_DEFAUT, **(poids or {})}
        total = sum(poids.values()) or 1
        crit = self.criteres()

        def normaliser(vals):
            lo, hi = min(vals), max(vals)
            if hi - lo < 1e-12:
                return [1.0] * len(vals)
            return [(v - lo) / (hi - lo) for v in vals]

        normes = {k: normaliser([c[k] for c in crit]) for k in self.POIDS_DEFAUT}
        lignes = []
        for i, c in enumerate(crit):
            score = sum(poids[k] * normes[k][i] for k in self.POIDS_DEFAUT) / total * 100
            lignes.append({**c, "score": score})
        return sorted(lignes, key=lambda x: -x["score"])
