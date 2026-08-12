"""
STRATÈJ — Moteur de simulation d'entreprise (version 3)
=======================================================
Nouveautés par rapport à la v2 :

  RESSOURCES HUMAINES
    Embauches et départs, salaire moyen, avances au personnel, avantages
    sociaux, formation. Un indice de moral (0-100) résulte du salaire relatif
    au marché, des avantages, de la formation et de la stabilité de l'emploi.
    Le moral agit sur la productivité, sur la qualité produite et sur le taux
    de départs. L'effectif limite la production réalisable.

  MARKETING PAR CANAUX
    Répartition libre du budget entre plusieurs canaux (réseaux sociaux,
    radio, télévision, affichage, terrain…), chacun ayant sa propre
    efficacité et son propre point de saturation. Commission versée aux
    vendeurs (en % du chiffre d'affaires) et partenariats optionnels.

  GÉOGRAPHIE
    Le marché est réparti entre départements. Chaque équipe décide où ouvrir
    des points de vente et où concentrer son marketing local : sans présence
    dans un département, on n'y vend presque rien.

  PRODUCTION
    Choix de la qualité des intrants pour chaque produit (économique,
    standard, premium), qui agit sur le coût unitaire et sur la qualité.

  FINANCE
    Créances clients et dettes fournisseurs, donc fonds de roulement réel,
    ratios de liquidité et véritable état des flux de trésorerie
    (exploitation / investissement / financement).

Monnaie : gourdes (HTG). Une ronde = un trimestre.
"""

import math
from dataclasses import dataclass, field
from copy import deepcopy


# ======================================================================
# PARAMÈTRES DE SCÉNARIO
# ======================================================================
@dataclass
class Intrant:
    """Option de qualité des matières premières."""
    nom: str = "Standard"
    facteur_cout: float = 1.00      # multiplicateur du coût unitaire
    effet_qualite: float = 0.00     # ajout (ou retrait) à la qualité perçue


@dataclass
class Canal:
    """Canal de communication, avec son efficacité et sa saturation."""
    nom: str = "Réseaux sociaux"
    efficacite: float = 1.30        # rendement relatif du canal
    budget_reference: float = 600_000   # budget donnant un effet « normal »
    saturation: float = 0.55        # exposant : plus il est bas, plus le canal
                                    # sature vite quand on y met beaucoup


@dataclass
class Departement:
    """Zone géographique du marché."""
    nom: str = "Ouest"
    poids: float = 0.40             # part de la demande nationale
    cout_pdv: float = 1_200_000     # coût d'ouverture d'un point de vente
    cout_exploitation_pdv: float = 180_000   # charge trimestrielle par point


@dataclass
class Partenariat:
    """Accord optionnel souscrit pour un trimestre."""
    nom: str = "Distributeur régional"
    cout: float = 800_000
    effet_presence: float = 0.25    # améliore la couverture géographique
    effet_qualite: float = 0.0      # améliore l'image / la qualité perçue
    effet_cout: float = 0.0         # réduit le coût unitaire (part)
    description: str = "Élargit la distribution là où vous êtes déjà présent."


@dataclass
class Produit:
    nom: str = "Produit A"
    demande_base: float = 130_000
    prix_reference: float = 250.0
    cout_variable_base: float = 90.0
    elasticite_marche: float = 0.6
    elasticite_prix: float = 3.0
    poids_qualite: float = 1.2
    poids_marketing: float = 0.8
    rd_reference: float = 1_000_000
    rendement_rd_qualite: float = 0.15
    depreciation_qualite: float = 0.05
    rendement_rd_procede: float = 0.06
    efficacite_max: float = 0.35
    heures_par_unite: float = 0.05   # charge de travail par unité produite


@dataclass
class Parametres:
    nb_trimestres: int = 8
    produits: list = field(default_factory=lambda: [Produit()])
    intrants: list = field(default_factory=lambda: [
        Intrant("Économique", 0.85, -0.08),
        Intrant("Standard", 1.00, 0.00),
        Intrant("Premium", 1.22, 0.12),
    ])
    canaux: list = field(default_factory=lambda: [
        Canal("Réseaux sociaux", 1.35, 500_000, 0.58),
        Canal("Radio", 0.85, 400_000, 0.50),
        Canal("Télévision", 1.05, 900_000, 0.45),
        Canal("Affichage et rue", 0.75, 350_000, 0.48),
        Canal("Marketing terrain", 1.10, 450_000, 0.52),
    ])
    departements: list = field(default_factory=lambda: [
        Departement("Ouest", 0.42, 1_400_000, 150_000),
        Departement("Nord", 0.16, 1_000_000, 110_000),
        Departement("Artibonite", 0.15, 1_000_000, 110_000),
        Departement("Sud", 0.13, 900_000, 95_000),
        Departement("Centre", 0.14, 900_000, 95_000),
    ])
    partenariats: list = field(default_factory=lambda: [
        Partenariat("Distributeur régional", 800_000, 0.30, 0.00, 0.00,
                    "Élargit la distribution dans vos départements actifs."),
        Partenariat("Coopérative de producteurs", 700_000, 0.00, 0.05, 0.06,
                    "Sécurise l'approvisionnement : coût réduit, qualité accrue."),
        Partenariat("Programme communautaire", 600_000, 0.10, 0.10, 0.00,
                    "Renforce l'image de marque et l'ancrage local."),
    ])
    conjoncture: list = field(default_factory=list)
    indice_cout: list = field(default_factory=list)
    conjoncture_labels: list = field(default_factory=list)
    indice_cout_labels: list = field(default_factory=list)
    croissance_trimestrielle: float = 0.01
    inflation_trimestrielle: float = 0.03

    # Coûts et capacité
    couts_fixes: float = 900_000
    cout_stockage_unitaire: float = 8.0
    capacite_initiale: float = 30_000
    cout_capacite: float = 400.0
    duree_amortissement: int = 30

    # Ressources humaines
    effectif_initial: int = 35
    salaire_marche: float = 20_000        # salaire trimestriel de référence
    heures_par_employe: float = 480.0     # capacité de travail par trimestre
    cout_embauche: float = 15_000         # recrutement et intégration
    cout_licenciement: float = 40_000     # indemnité de départ
    moral_initial: float = 60.0
    rendement_formation: float = 0.00004  # gain de compétence par HTG investi
    rendement_avantages: float = 0.00003  # effet des avantages sociaux sur le moral
    competence_max: float = 0.30          # gain de productivité maximal

    # Commercial
    poids_commission: float = 0.5         # sensibilité des ventes à la commission
    commission_reference: float = 0.04    # taux de commission « normal » (4 %)
    presence_minimale: float = 0.08       # part de marché captable sans présence

    # Marché
    tolerance_prix: float = 0.25
    penalite_prix: float = 4.0
    taux_report: float = 0.60
    attrait_exterieur: float = 0.15

    # Finance
    encaisse_initiale: float = 8_000_000
    taux_interet: float = 0.03
    taux_urgence: float = 0.08
    taux_impot: float = 0.30
    part_ventes_a_credit: float = 0.30    # encaissée le trimestre suivant
    part_achats_a_credit: float = 0.25    # payée le trimestre suivant

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

    def salaire_marche_t(self, t):
        return self.salaire_marche * (1 + self.inflation_trimestrielle) ** t

    def intrant(self, nom):
        for i in self.intrants:
            if i.nom == nom:
                return i
        return self.intrants[len(self.intrants) // 2]


# ======================================================================
# DÉCISIONS
# ======================================================================
@dataclass
class DecisionsProduit:
    production: float = 0.0
    prix: float = 250.0
    intrant: str = "Standard"
    rd_qualite: float = 0.0
    rd_procede: float = 0.0


@dataclass
class DecisionsRH:
    embauches: int = 0                 # positif = recrutement, négatif = départs
    salaire: float = 22_000            # salaire trimestriel moyen offert
    avantages_sociaux: float = 0.0     # budget total du trimestre
    formation: float = 0.0             # budget total du trimestre
    avances: float = 0.0               # avances consenties au personnel


@dataclass
class Decisions:
    produits: dict = field(default_factory=dict)      # nom -> DecisionsProduit
    marketing: dict = field(default_factory=dict)     # canal -> montant
    marketing_local: dict = field(default_factory=dict)   # département -> montant
    ouvertures_pdv: dict = field(default_factory=dict)    # département -> nombre
    partenariats: list = field(default_factory=list)  # noms retenus ce trimestre
    commission: float = 0.04                          # % du chiffre d'affaires
    rh: DecisionsRH = field(default_factory=DecisionsRH)
    invest_capacite: float = 0.0
    nouvel_emprunt: float = 0.0
    remboursement: float = 0.0


# ======================================================================
# ÉTAT DE L'ENTREPRISE
# ======================================================================
@dataclass
class EtatProduit:
    stock_unites: float = 0.0
    stock_valeur: float = 0.0
    qualite: float = 0.0
    efficacite: float = 0.0


@dataclass
class Entreprise:
    nom: str
    encaisse: float = 0.0
    creances: float = 0.0              # ventes à encaisser
    dettes_fournisseurs: float = 0.0   # achats à payer
    avances_personnel: float = 0.0     # avances consenties, remboursées ensuite
    capacite: float = 0.0
    immobilisations_brutes: float = 0.0
    amortissement_cumule: float = 0.0
    dette: float = 0.0
    dette_urgence: float = 0.0
    capitaux_propres: float = 0.0
    profit_cumule: float = 0.0
    # Ressources humaines
    effectif: int = 0
    moral: float = 60.0
    competence: float = 0.0
    # Réseau
    pdv: dict = field(default_factory=dict)        # département -> nombre de points
    etats_produits: dict = field(default_factory=dict)
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
    def actif_court_terme(self):
        return (self.encaisse + self.creances + self.stock_valeur_totale
                + self.avances_personnel)

    @property
    def passif_court_terme(self):
        return self.dettes_fournisseurs + self.dette_urgence

    @property
    def fonds_roulement(self):
        return self.actif_court_terme - self.passif_court_terme

    @property
    def actif_total(self):
        return self.actif_court_terme + self.immobilisations_nettes

    @property
    def nb_pdv(self):
        return sum(self.pdv.values())


# ======================================================================
# MÉCANIQUES : RH, MARKETING, GÉOGRAPHIE, COÛTS
# ======================================================================
def maj_ressources_humaines(par: Parametres, e: Entreprise, rh: DecisionsRH,
                            t: int) -> dict:
    """Applique les décisions RH : effectif, moral, compétence.
    Retourne le détail des coûts et indicateurs du trimestre."""
    salaire_marche = par.salaire_marche_t(t)

    # Mouvements d'effectif
    embauches = max(rh.embauches, 0)
    departs_voulus = max(-rh.embauches, 0)
    departs_voulus = min(departs_voulus, e.effectif)
    e.effectif = e.effectif + embauches - departs_voulus

    # Départs volontaires liés au moral (rotation du personnel)
    taux_rotation = max(0.0, (55.0 - e.moral) / 55.0) * 0.12
    departs_naturels = int(round(e.effectif * taux_rotation))
    e.effectif = max(0, e.effectif - departs_naturels)

    # Moral : salaire relatif, avantages, formation, stabilité de l'emploi
    ratio_salaire = rh.salaire / salaire_marche if salaire_marche > 0 else 1.0
    cible = 50.0 + 45.0 * math.tanh(2.2 * (ratio_salaire - 1.0))
    par_tete = (rh.avantages_sociaux / e.effectif) if e.effectif > 0 else 0.0
    cible += min(25.0, par_tete * par.rendement_avantages * 100)
    form_tete = (rh.formation / e.effectif) if e.effectif > 0 else 0.0
    cible += min(12.0, form_tete * par.rendement_formation * 100)
    if departs_voulus > 0:
        cible -= min(18.0, 45.0 * departs_voulus / max(e.effectif + departs_voulus, 1))
    if rh.avances > 0:
        cible += 3.0
    cible = max(5.0, min(100.0, cible))
    e.moral += (cible - e.moral) * 0.55        # ajustement progressif

    # Compétence : la formation s'accumule, avec une érosion lente
    e.competence = min(par.competence_max,
                       e.competence * 0.96
                       + par.rendement_formation * form_tete)

    # Productivité : moral et compétence
    facteur_moral = 0.70 + 0.60 * (e.moral / 100.0)
    productivite = facteur_moral * (1 + e.competence)
    heures_disponibles = e.effectif * par.heures_par_employe * productivite

    couts = {
        "salaires": e.effectif * rh.salaire,
        "avantages_sociaux": rh.avantages_sociaux,
        "formation": rh.formation,
        "recrutement": embauches * par.cout_embauche,
        "licenciement": departs_voulus * par.cout_licenciement,
    }
    return {
        "couts": couts, "total": sum(couts.values()),
        "embauches": embauches, "departs_voulus": departs_voulus,
        "departs_naturels": departs_naturels,
        "heures_disponibles": heures_disponibles,
        "productivite": productivite, "ratio_salaire": ratio_salaire,
    }


def effet_marketing(par: Parametres, budgets: dict) -> float:
    """Effet global du marketing : somme des canaux, chacun avec sa propre
    efficacité et sa propre saturation (rendements décroissants)."""
    effet = 0.0
    for canal in par.canaux:
        montant = max(budgets.get(canal.nom, 0.0), 0.0)
        if montant > 0:
            effet += canal.efficacite * (montant / canal.budget_reference) ** canal.saturation
    return effet


def couverture_departement(par: Parametres, e: Entreprise, dep: Departement,
                           marketing_local: dict, bonus_partenariat: float) -> float:
    """Présence commerciale de l'équipe dans un département (0 à ~1,5).
    Sans point de vente ni marketing local, la captation reste marginale."""
    points = e.pdv.get(dep.nom, 0)
    effet_pdv = 1 - math.exp(-0.8 * points)
    budget = max(marketing_local.get(dep.nom, 0.0), 0.0)
    effet_local = (budget / 400_000) ** 0.5 * 0.35 if budget > 0 else 0.0
    return (par.presence_minimale + effet_pdv + effet_local) * (1 + bonus_partenariat)


def cout_unitaire(par: Parametres, prod: Produit, ep: EtatProduit,
                  nom_intrant: str, t: int, remise_partenariat: float = 0.0) -> float:
    """Coût de base x inflation x indice des intrants x qualité d'intrant
    x (1 - efficacité acquise) x (1 - remise de partenariat)."""
    intrant = par.intrant(nom_intrant)
    return (prod.cout_variable_base
            * (1 + par.inflation_trimestrielle) ** t
            * par.indice_cout_t(t)
            * intrant.facteur_cout
            * (1 - ep.efficacite)
            * (1 - remise_partenariat))


# ======================================================================
# MARCHÉ
# ======================================================================
def demande_totale_produit(par: Parametres, prod: Produit, t: int,
                           prix_moyen: float) -> float:
    base = prod.demande_base * (1 + par.croissance_trimestrielle) ** t
    effet_prix = (prod.prix_reference / max(prix_moyen, 1.0)) ** prod.elasticite_marche
    return base * par.conjoncture_t(t) * effet_prix


def attractivite(par: Parametres, prod: Produit, dp: DecisionsProduit,
                 ep: EtatProduit, effet_mkt: float, commission: float,
                 qualite_bonus: float, moral: float) -> float:
    """Attractivité nationale d'une offre, avant pondération géographique."""
    a_prix = (prod.prix_reference / max(dp.prix, 1.0)) ** prod.elasticite_prix
    qualite = (max(ep.qualite, 0.0) + par.intrant(dp.intrant).effet_qualite
               + qualite_bonus + 0.15 * (moral - 60.0) / 100.0)
    a_qualite = (1 + max(qualite, 0.0)) ** prod.poids_qualite
    a_marketing = (1 + effet_mkt) ** prod.poids_marketing
    a_commission = (1 + commission / par.commission_reference) ** par.poids_commission
    penalite = 1.0
    ratio = dp.prix / max(prod.prix_reference, 1.0)
    if ratio > 1.0 + par.tolerance_prix:
        penalite = math.exp(-par.penalite_prix * (ratio - 1.0 - par.tolerance_prix))
    return a_prix * a_qualite * a_marketing * a_commission * penalite


def repartir_demande(demande: float, attraits: list, offres: list,
                     taux_report: float = 1.0,
                     attrait_exterieur: float = 0.0) -> list:
    """Répartition avec option extérieure (le client peut renoncer) et
    report partiel de la demande non servie."""
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


# ======================================================================
# VALIDATION DES DÉCISIONS
# ======================================================================
def valider(par: Parametres, e: Entreprise, d: Decisions, t: int) -> tuple:
    d = deepcopy(d)
    notes = []
    noms_intrants = [i.nom for i in par.intrants]

    # --- Décisions produit ---
    for p in par.produits:
        if p.nom not in d.produits:
            d.produits[p.nom] = DecisionsProduit(prix=p.prix_reference)
        dp = d.produits[p.nom]
        if dp.prix <= 0:
            dp.prix = p.prix_reference
            notes.append(f"{p.nom} : prix invalide, ramené au prix de référence.")
        if dp.intrant not in noms_intrants:
            dp.intrant = "Standard" if "Standard" in noms_intrants else noms_intrants[0]
        dp.production = max(dp.production, 0.0)
        dp.rd_qualite = max(dp.rd_qualite, 0.0)
        dp.rd_procede = max(dp.rd_procede, 0.0)

    # --- Bornes générales ---
    d.commission = min(max(d.commission, 0.0), 0.25)
    d.invest_capacite = max(d.invest_capacite, 0.0)
    d.nouvel_emprunt = max(d.nouvel_emprunt, 0.0)
    d.remboursement = min(max(d.remboursement, 0.0), e.dette)
    d.rh.salaire = max(d.rh.salaire, 0.0)
    d.rh.avantages_sociaux = max(d.rh.avantages_sociaux, 0.0)
    d.rh.formation = max(d.rh.formation, 0.0)
    d.rh.avances = max(d.rh.avances, 0.0)
    d.rh.embauches = int(d.rh.embauches)
    if d.rh.embauches < -e.effectif:
        d.rh.embauches = -e.effectif
        notes.append("Départs plafonnés à l'effectif actuel.")
    d.marketing = {k: max(v, 0.0) for k, v in d.marketing.items()}
    d.marketing_local = {k: max(v, 0.0) for k, v in d.marketing_local.items()}
    d.ouvertures_pdv = {k: max(int(v), 0) for k, v in d.ouvertures_pdv.items()}
    noms_part = [pa.nom for pa in par.partenariats]
    d.partenariats = [x for x in d.partenariats if x in noms_part]

    # --- Capacité de production (machines) ---
    prod_totale = sum(d.produits[p.nom].production for p in par.produits)
    if prod_totale > e.capacite and prod_totale > 0:
        ratio = e.capacite / prod_totale
        for p in par.produits:
            d.produits[p.nom].production *= ratio
        notes.append(f"Production plafonnée à la capacité installée "
                     f"({e.capacite:,.0f} u), répartie au prorata.")
        prod_totale = e.capacite

    return d, notes


def plafonner_par_effectif(par: Parametres, d: Decisions, heures_disponibles: float,
                           notes: list):
    """La main-d'œuvre disponible limite la production réalisable."""
    heures_requises = sum(d.produits[p.nom].production * p.heures_par_unite
                          for p in par.produits)
    if heures_requises > heures_disponibles and heures_requises > 0:
        ratio = heures_disponibles / heures_requises
        for p in par.produits:
            d.produits[p.nom].production *= ratio
        notes.append("Production limitée par la main-d'œuvre disponible "
                     f"({ratio*100:.0f} % du plan réalisé) : effectif, moral ou "
                     "compétence insuffisants.")
    return notes


def cout_engage(par: Parametres, e: Entreprise, d: Decisions, t: int,
                rh_info: dict) -> float:
    """Dépenses engagées ce trimestre (utilisé par l'interface pour empêcher
    de dépenser plus que les ressources disponibles)."""
    remise = sum(par_.effet_cout for par_ in par.partenariats
                 if par_.nom in d.partenariats)
    cout_prod = 0.0
    for p in par.produits:
        dp = d.produits.get(p.nom)
        if dp:
            cu = cout_unitaire(par, p, e.etats_produits[p.nom], dp.intrant, t, remise)
            cout_prod += dp.production * cu
    pdv_ouverts = sum(dep.cout_pdv * d.ouvertures_pdv.get(dep.nom, 0)
                      for dep in par.departements)
    return (cout_prod * (1 - par.part_achats_a_credit)
            + e.dettes_fournisseurs
            + sum(d.marketing.values()) + sum(d.marketing_local.values())
            + sum(dp.rd_qualite + dp.rd_procede for dp in d.produits.values())
            + rh_info["total"] + d.rh.avances
            + sum(pa.cout for pa in par.partenariats if pa.nom in d.partenariats)
            + pdv_ouverts + d.invest_capacite + d.remboursement)


# ======================================================================
# SIMULATION
# ======================================================================
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
            e.effectif = parametres.effectif_initial
            e.moral = parametres.moral_initial
            e.etats_produits = {p.nom: EtatProduit() for p in parametres.produits}
            e.pdv = {dep.nom: (1 if dep is parametres.departements[0] else 0)
                     for dep in parametres.departements}
            e.capitaux_propres = e.encaisse + e.immobilisations_brutes
            e.dernieres_decisions = Decisions(
                produits={p.nom: DecisionsProduit(prix=p.prix_reference)
                          for p in parametres.produits},
                rh=DecisionsRH(salaire=parametres.salaire_marche))
            self.equipes.append(e)

    # ------------------------------------------------------------------
    def couts_unitaires_courants(self, e: Entreprise, intrants: dict = None) -> dict:
        """Coût unitaire de chaque produit, pour la qualité d'intrant choisie."""
        intrants = intrants or {}
        return {p.nom: cout_unitaire(self.par, p, e.etats_produits[p.nom],
                                     intrants.get(p.nom, "Standard"), self.t)
                for p in self.par.produits}

    # ------------------------------------------------------------------
    def jouer_ronde(self, decisions_par_equipe: dict) -> dict:
        par, t = self.par, self.t
        n = len(self.equipes)

        # 1) Collecte, validation, RH, contrainte de main-d'œuvre
        decisions, ajustements, infos_rh = [], [], []
        for e in self.equipes:
            brutes = decisions_par_equipe.get(e.nom)
            if brutes is None:
                brutes = deepcopy(e.dernieres_decisions)
                notes0 = ["Aucune soumission : décisions précédentes reconduites."]
            else:
                notes0 = []
            d, notes = valider(par, e, brutes, t)
            info_rh = maj_ressources_humaines(par, e, d.rh, t)
            notes = plafonner_par_effectif(par, d, info_rh["heures_disponibles"], notes)
            decisions.append(d)
            infos_rh.append(info_rh)
            ajustements.append(notes0 + notes)

        # 2) Ouverture des points de vente (effectifs immédiatement)
        for i, e in enumerate(self.equipes):
            for dep in par.departements:
                e.pdv[dep.nom] = e.pdv.get(dep.nom, 0) + decisions[i].ouvertures_pdv.get(dep.nom, 0)

        # 3) Effets transverses : marketing, partenariats
        effets_mkt, bonus_presence, bonus_qualite, remises = [], [], [], []
        for i in range(n):
            d = decisions[i]
            effets_mkt.append(effet_marketing(par, d.marketing))
            choisis = [pa for pa in par.partenariats if pa.nom in d.partenariats]
            bonus_presence.append(sum(pa.effet_presence for pa in choisis))
            bonus_qualite.append(sum(pa.effet_qualite for pa in choisis))
            remises.append(sum(pa.effet_cout for pa in choisis))

        # 4) Marché : par produit ET par département
        marches, ventes_par_produit = {}, {}
        for p in par.produits:
            prix_moyen = sum(decisions[i].produits[p.nom].prix for i in range(n)) / n
            D_total = demande_totale_produit(par, p, t, prix_moyen)
            attraits_nat = [attractivite(par, p, decisions[i].produits[p.nom],
                                         self.equipes[i].etats_produits[p.nom],
                                         effets_mkt[i], decisions[i].commission,
                                         bonus_qualite[i], self.equipes[i].moral)
                            for i in range(n)]
            offres = [self.equipes[i].etats_produits[p.nom].stock_unites
                      + decisions[i].produits[p.nom].production for i in range(n)]
            ventes = [0.0] * n
            detail_dep = {}
            for dep in par.departements:
                D_dep = D_total * dep.poids
                couvertures = [couverture_departement(
                    par, self.equipes[i], dep, decisions[i].marketing_local,
                    bonus_presence[i]) for i in range(n)]
                attraits_dep = [attraits_nat[i] * couvertures[i] for i in range(n)]
                offre_dispo = [max(offres[i] - ventes[i], 0.0) for i in range(n)]
                v_dep = repartir_demande(D_dep, attraits_dep, offre_dispo,
                                         par.taux_report, par.attrait_exterieur)
                for i in range(n):
                    ventes[i] += v_dep[i]
                detail_dep[dep.nom] = {
                    "demande": D_dep,
                    "ventes": {self.equipes[i].nom: v_dep[i] for i in range(n)},
                }
            marches[p.nom] = {"demande": D_total, "prix_moyen": prix_moyen,
                              "offres": offres, "departements": detail_dep}
            ventes_par_produit[p.nom] = ventes

        # 5) Clôture financière
        resultats = []
        demande_marche = sum(m["demande"] for m in marches.values())
        for i, e in enumerate(self.equipes):
            ventes_i = {p.nom: ventes_par_produit[p.nom][i] for p in par.produits}
            resultats.append(self._cloture(e, decisions[i], ventes_i, t,
                                           infos_rh[i], remises[i]))
            e.dernieres_decisions = deepcopy(decisions[i])
            vt = sum(ventes_i.values())
            e.parts_historiques.append(vt / demande_marche if demande_marche > 0 else 0.0)

        # 6) Bulletin de marché
        bulletin = {
            "trimestre": t + 1,
            "conjoncture": par.conjoncture_t(t),
            "indice_cout": par.indice_cout_t(t),
            "conjoncture_label": par.label_conjoncture_t(t),
            "indice_cout_label": par.label_indice_cout_t(t),
            "produits": {}, "departements": {},
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
        for dep in par.departements:
            total_dep = sum(marches[p.nom]["departements"][dep.nom]["demande"]
                            for p in par.produits)
            bulletin["departements"][dep.nom] = {
                "demande": total_dep,
                "equipes": [{
                    "nom": self.equipes[i].nom,
                    "points_de_vente": self.equipes[i].pdv.get(dep.nom, 0),
                    "ventes": sum(marches[p.nom]["departements"][dep.nom]["ventes"][self.equipes[i].nom]
                                  for p in par.produits),
                } for i in range(n)],
            }
        self.bulletins.append(bulletin)

        for i, e in enumerate(self.equipes):
            resultats[i]["ajustements"] = ajustements[i]
            e.rapports.append(resultats[i])

        self.t += 1
        return {"bulletin": bulletin,
                "rapports": {e.nom: e.rapports[-1] for e in self.equipes}}

    # ------------------------------------------------------------------
    def _cloture(self, e: Entreprise, d: Decisions, ventes: dict, t: int,
                 rh_info: dict, remise: float) -> dict:
        par = self.par
        rev_prec = e.rapports[-1]["etat_resultats"]["revenus"] if e.rapports else None

        detail_produits = {}
        revenus = cmv = cout_production = rd_total = 0.0

        for p in par.produits:
            dp, ep = d.produits[p.nom], e.etats_produits[p.nom]
            cu = cout_unitaire(par, p, ep, dp.intrant, t, remise)
            cp = dp.production * cu
            ep.stock_unites += dp.production
            ep.stock_valeur += cp
            cum = ep.stock_valeur / ep.stock_unites if ep.stock_unites > 0 else 0.0
            v = ventes[p.nom]
            c = v * cum
            ep.stock_unites -= v
            ep.stock_valeur -= c
            if ep.stock_unites < 1e-6:
                ep.stock_unites, ep.stock_valeur = 0.0, 0.0

            ep.qualite = (ep.qualite * (1 - p.depreciation_qualite)
                          + p.rendement_rd_qualite * (dp.rd_qualite / p.rd_reference))
            marge_restante = (p.efficacite_max - ep.efficacite) / p.efficacite_max
            ep.efficacite = min(p.efficacite_max,
                                ep.efficacite + p.rendement_rd_procede
                                * (dp.rd_procede / p.rd_reference)
                                * max(marge_restante, 0.0))

            revenus += v * dp.prix
            cmv += c
            cout_production += cp
            rd_total += dp.rd_qualite + dp.rd_procede
            detail_produits[p.nom] = {
                "ventes": v, "prix": dp.prix, "revenus": v * dp.prix, "cmv": c,
                "marge_brute": v * dp.prix - c, "cout_unitaire": cu,
                "intrant": dp.intrant, "stock_unites": ep.stock_unites,
                "qualite": ep.qualite, "efficacite": ep.efficacite,
            }

        # --- Charges du trimestre ---
        marketing = sum(d.marketing.values()) + sum(d.marketing_local.values())
        commissions = revenus * d.commission
        cout_partenariats = sum(pa.cout for pa in par.partenariats
                                if pa.nom in d.partenariats)
        cout_pdv_exploit = sum(dep.cout_exploitation_pdv * e.pdv.get(dep.nom, 0)
                               for dep in par.departements)
        capex_pdv = sum(dep.cout_pdv * d.ouvertures_pdv.get(dep.nom, 0)
                        for dep in par.departements)
        couts_fixes = par.couts_fixes_t(t) + cout_pdv_exploit
        stockage = e.stock_unites_total * par.cout_stockage_unitaire
        amortissement = min(e.immobilisations_brutes / par.duree_amortissement,
                            e.immobilisations_nettes)
        interets = e.dette * par.taux_interet + e.dette_urgence * par.taux_urgence
        charges_rh = rh_info["total"]

        ebt = (revenus - cmv - couts_fixes - marketing - rd_total - commissions
               - charges_rh - cout_partenariats - stockage - amortissement - interets)
        impot = max(ebt, 0.0) * par.taux_impot
        benefice_net = ebt - impot

        # --- Flux de trésorerie (méthode directe) ---
        creances_ouverture = e.creances
        dettes_ouverture = e.dettes_fournisseurs
        encaissements = revenus * (1 - par.part_ventes_a_credit) + creances_ouverture
        e.creances = revenus * par.part_ventes_a_credit
        paiements_fournisseurs = (cout_production * (1 - par.part_achats_a_credit)
                                  + dettes_ouverture)
        e.dettes_fournisseurs = cout_production * par.part_achats_a_credit

        # Avances au personnel : sorties ce trimestre, remboursées au suivant
        avances_remboursees = e.avances_personnel
        nouvelles_avances = d.rh.avances
        e.avances_personnel = nouvelles_avances

        autres_decaissements = (couts_fixes + marketing + rd_total + commissions
                                + charges_rh + cout_partenariats + stockage
                                + interets + impot)
        flux_exploitation = (encaissements + avances_remboursees
                             - paiements_fournisseurs - autres_decaissements
                             - nouvelles_avances)
        flux_investissement = -(d.invest_capacite + capex_pdv)
        flux_financement = d.nouvel_emprunt - d.remboursement

        e.encaisse += flux_exploitation + flux_investissement + flux_financement
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

        e.immobilisations_brutes += d.invest_capacite + capex_pdv
        e.amortissement_cumule += amortissement
        e.capacite += d.invest_capacite / par.cout_capacite
        e.capitaux_propres += benefice_net
        e.profit_cumule += benefice_net

        # --- Ratios ---
        actif = e.actif_total
        act = e.actif_court_terme
        pct = e.passif_court_terme
        ratios = {
            "marge_nette": benefice_net / revenus if revenus > 0 else 0.0,
            "roe": benefice_net / e.capitaux_propres if e.capitaux_propres > 0 else 0.0,
            "roa": benefice_net / actif if actif > 0 else 0.0,
            "rotation_actif": revenus / actif if actif > 0 else 0.0,
            "rotation_stocks": (cmv / e.stock_valeur_totale
                                if e.stock_valeur_totale > 1e-6 else None),
            "liquidite_generale": act / pct if pct > 1e-6 else None,
            "liquidite_reduite": ((act - e.stock_valeur_totale) / pct
                                  if pct > 1e-6 else None),
            "liquidite_immediate": e.encaisse / pct if pct > 1e-6 else None,
            "fonds_roulement": e.fonds_roulement,
            "fonds_roulement_sur_revenus": (e.fonds_roulement / revenus
                                            if revenus > 0 else None),
            "delai_recouvrement_jours": (e.creances / revenus * 90
                                         if revenus > 0 else None),
            "delai_paiement_jours": (e.dettes_fournisseurs / cout_production * 90
                                     if cout_production > 0 else None),
            "dette_actif": (e.dette + e.dette_urgence) / actif if actif > 0 else 0.0,
            "couverture_interets": ((ebt + interets) / interets
                                    if interets > 1e-6 else None),
            "croissance_revenus": (revenus / rev_prec - 1.0
                                   if rev_prec and rev_prec > 0 else None),
        }

        ecart = e.actif_total - (e.dettes_fournisseurs + e.dette + e.dette_urgence
                                 + e.capitaux_propres)
        assert abs(ecart) < 1.0, f"Bilan déséquilibré ({e.nom}) : écart {ecart:,.2f}"

        return {
            "trimestre": t + 1, "decisions": deepcopy(d), "produits": detail_produits,
            "etat_resultats": {
                "revenus": revenus, "cmv": cmv, "couts_fixes": couts_fixes,
                "marketing": marketing, "rd": rd_total, "commissions": commissions,
                "charges_rh": charges_rh, "partenariats": cout_partenariats,
                "stockage": stockage, "amortissement": amortissement,
                "interets": interets, "benefice_avant_impot": ebt, "impot": impot,
                "benefice_net": benefice_net,
            },
            "flux_tresorerie": {
                "encaissements_clients": encaissements,
                "paiements_fournisseurs": -paiements_fournisseurs,
                "autres_decaissements": -autres_decaissements,
                "avances_personnel": avances_remboursees - nouvelles_avances,
                "flux_exploitation": flux_exploitation,
                "flux_investissement": flux_investissement,
                "flux_financement": flux_financement,
                "variation_encaisse": (flux_exploitation + flux_investissement
                                       + flux_financement),
                "decouvert_urgence": urgence_tiree,
                "encaisse_cloture": e.encaisse,
            },
            "bilan": {
                "encaisse": e.encaisse, "creances": e.creances,
                "stocks": e.stock_valeur_totale,
                "avances_personnel": e.avances_personnel,
                "actif_court_terme": e.actif_court_terme,
                "immobilisations_nettes": e.immobilisations_nettes,
                "actif_total": e.actif_total,
                "dettes_fournisseurs": e.dettes_fournisseurs,
                "dette": e.dette, "dette_urgence": e.dette_urgence,
                "passif_court_terme": e.passif_court_terme,
                "fonds_roulement": e.fonds_roulement,
                "capitaux_propres": e.capitaux_propres,
            },
            "rh": {
                "effectif": e.effectif, "moral": e.moral,
                "competence": e.competence, "salaire": d.rh.salaire,
                "ratio_salaire": rh_info["ratio_salaire"],
                "productivite": rh_info["productivite"],
                "embauches": rh_info["embauches"],
                "departs_voulus": rh_info["departs_voulus"],
                "departs_naturels": rh_info["departs_naturels"],
                "detail_couts": rh_info["couts"],
            },
            "reseau": {"pdv": dict(e.pdv), "total_pdv": e.nb_pdv,
                       "ouvertures": dict(d.ouvertures_pdv),
                       "partenariats": list(d.partenariats)},
            "ratios": ratios,
            "indicateurs": {
                "stock_unites": e.stock_unites_total, "capacite": e.capacite,
                "dette_urgence_tiree": urgence_tiree,
                "profit_cumule": e.profit_cumule,
            },
        }

    # ------------------------------------------------------------------
    POIDS_DEFAUT = {"rentabilite": 25, "solvabilite": 15, "liquidite": 10,
                    "gestion": 15, "croissance": 15, "part_marche": 20}

    def criteres(self) -> list:
        lignes = []
        for e in self.equipes:
            revs = [r["etat_resultats"]["revenus"] for r in e.rapports]
            rot = [r["ratios"]["rotation_actif"] for r in e.rapports if r.get("ratios")]
            liq = [r["ratios"]["liquidite_generale"] for r in e.rapports
                   if r.get("ratios") and r["ratios"]["liquidite_generale"] is not None]
            croissance = (revs[-1] / revs[0] - 1.0
                          if len(revs) >= 2 and revs[0] > 0 else 0.0)
            lignes.append({
                "nom": e.nom,
                "rentabilite": e.profit_cumule,
                "solvabilite": (e.capitaux_propres / e.actif_total
                                if e.actif_total > 0 else 0.0),
                "liquidite": min(sum(liq) / len(liq), 4.0) if liq else 2.0,
                "gestion": sum(rot) / len(rot) if rot else 0.0,
                "croissance": croissance,
                "part_marche": (sum(e.parts_historiques)
                                / max(len(e.parts_historiques), 1)),
            })
        return lignes

    def classement(self, poids: dict = None) -> list:
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
