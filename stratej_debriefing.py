"""
STRATÈJ — Moteur de débriefing pédagogique
==========================================
Analyse les décisions et les résultats d'une équipe après chaque trimestre et
produit un débriefing personnalisé.

Architecture en deux temps (volontaire) :
  1. analyser(...)  -> liste de DIAGNOSTICS structurés (calcul pur, testable)
  2. rediger(...)   -> texte pédagogique à partir des diagnostics

Cette séparation permet de remplacer plus tard l'étape 2 par une rédaction
générée par IA (les diagnostics servent alors de matière première), sans
rien changer à l'étape 1.

Aucune dépendance externe : fonctionne hors ligne.
"""

from dataclasses import dataclass


# ----------------------------------------------------------------------
# Diagnostic élémentaire
# ----------------------------------------------------------------------
@dataclass
class Diagnostic:
    cle: str            # identifiant technique
    categorie: str      # Marché, Production, Coûts, Finance, Trajectoire
    ton: str            # "positif", "alerte", "neutre"
    titre: str          # résumé court
    constat: str        # ce qui s'est passé, chiffré
    lecture: str        # ce que ça signifie / la question à se poser


P, A, N = "positif", "alerte", "neutre"


def _pct(x):
    return f"{x*100:.1f} %"


def _n(x):
    return f"{x:,.0f}".replace(",", " ")


# ----------------------------------------------------------------------
# 1) ANALYSE — produit les diagnostics structurés
# ----------------------------------------------------------------------
def analyser(partie, nom_equipe: str, index_trimestre: int = -1) -> dict:
    """Analyse un trimestre pour une équipe.
    Retourne {'equipe', 'trimestre', 'diagnostics': [Diagnostic], 'faits': {...}}"""
    sim = partie.sim
    e = next(x for x in sim.equipes if x.nom == nom_equipe)
    if not e.rapports:
        return {"equipe": nom_equipe, "trimestre": 0, "diagnostics": [], "faits": {}}

    idx = index_trimestre if index_trimestre >= 0 else len(e.rapports) + index_trimestre
    idx = max(0, min(idx, len(e.rapports) - 1))
    rap = e.rapports[idx]
    prec = e.rapports[idx - 1] if idx > 0 else None
    bulletin = partie.historique[idx]["bulletin"]
    er, ratios, ind = rap["etat_resultats"], rap.get("ratios", {}), rap["indicateurs"]

    diagnostics = []
    faits = {"trimestre": rap["trimestre"],
             "conjoncture": bulletin.get("conjoncture_label", ""),
             "intrants": bulletin.get("indice_cout_label", "")}

    # --- Contraintes appliquées par le moteur (à signaler en premier) ---
    for note in rap.get("ajustements", []):
        diagnostics.append(Diagnostic(
            "ajustement", "Décisions", A, "Vos décisions ont été ajustées",
            note,
            "Une décision hors contrainte est corrigée automatiquement : "
            "vérifiez capacité, trésorerie et dette avant de soumettre."))

    # --- MARCHÉ : positionnement prix, part, écoulement ---------------
    for nom_p, dp in rap["produits"].items():
        info_marche = bulletin["produits"].get(nom_p, {})
        prix_moyen = info_marche.get("prix_moyen", dp["prix"])
        ecart = dp["prix"] / prix_moyen - 1 if prix_moyen else 0
        part = next((q["part_marche"] for q in info_marche.get("equipes", [])
                     if q["nom"] == nom_equipe), 0.0)
        produit_dispo = dp["ventes"] + dp["stock_unites"]
        taux_ecoulement = dp["ventes"] / produit_dispo if produit_dispo > 0 else 0

        if ecart > 0.15:
            diagnostics.append(Diagnostic(
                f"prix_haut_{nom_p}", "Marché", A,
                f"{nom_p} : prix nettement au-dessus du marché",
                f"Votre prix de {_n(dp['prix'])} HTG dépassait de {_pct(ecart)} "
                f"le prix moyen ({_n(prix_moyen)} HTG). Part de marché obtenue : "
                f"{_pct(part)}, taux d'écoulement {_pct(taux_ecoulement)}.",
                "Un prix élevé n'est tenable que s'il s'appuie sur une qualité "
                "perçue supérieure. Comparez votre indice qualité à celui "
                "qu'implique votre positionnement."))
        elif ecart < -0.12:
            diagnostics.append(Diagnostic(
                f"prix_bas_{nom_p}", "Marché", N,
                f"{nom_p} : stratégie de prix agressive",
                f"Votre prix de {_n(dp['prix'])} HTG était {_pct(abs(ecart))} "
                f"sous le marché. Part de marché : {_pct(part)}, marge brute "
                f"{_n(dp['marge_brute'])} HTG.",
                "Le volume gagné compense-t-il la marge sacrifiée ? Comparez "
                "votre marge brute totale à celle du trimestre précédent."))

        if dp["cout_unitaire"] > 0 and dp["prix"] < dp["cout_unitaire"] * 1.05:
            diagnostics.append(Diagnostic(
                f"prix_sous_cout_{nom_p}", "Marché", A,
                f"{nom_p} : prix trop proche du coût de revient",
                f"Prix {_n(dp['prix'])} HTG contre un coût unitaire de "
                f"{_n(dp['cout_unitaire'])} HTG.",
                "À ce niveau, chaque unité vendue ne couvre pas les charges "
                "fixes. Calculez votre point mort avant de fixer le prix."))

        if taux_ecoulement < 0.7 and produit_dispo > 0:
            diagnostics.append(Diagnostic(
                f"invendus_{nom_p}", "Production", A,
                f"{nom_p} : invendus importants",
                f"{_n(dp['stock_unites'])} unités restent en stock "
                f"({_pct(1 - taux_ecoulement)} de ce que vous aviez à vendre).",
                "Produire n'est pas vendre. Ajustez la production à la demande "
                "que votre positionnement peut réellement capter — le stock "
                "immobilise de la trésorerie et coûte en entreposage."))
        elif taux_ecoulement > 0.99 and part > 0:
            diagnostics.append(Diagnostic(
                f"rupture_{nom_p}", "Production", N,
                f"{nom_p} : tout votre stock a été écoulé",
                f"Vous avez vendu {_n(dp['ventes'])} unités, sans reliquat.",
                "Une rupture peut signifier une demande non servie, captée par "
                "vos concurrents. Envisagez plus de production ou de capacité."))

    # --- COÛTS et R&D --------------------------------------------------
    for nom_p, dp in rap["produits"].items():
        if dp["efficacite"] > 0.02:
            diagnostics.append(Diagnostic(
                f"efficacite_{nom_p}", "Coûts", P,
                f"{nom_p} : votre R&D procédé porte ses fruits",
                f"Efficacité acquise {_pct(dp['efficacite'])} : votre coût "
                f"unitaire est de {_n(dp['cout_unitaire'])} HTG.",
                "Cet avantage est cumulatif et vous protège lors des hausses "
                "de coûts des intrants."))
        elif prec and dp["cout_unitaire"] > prec["produits"][nom_p]["cout_unitaire"] * 1.05:
            diagnostics.append(Diagnostic(
                f"cout_hausse_{nom_p}", "Coûts", A,
                f"{nom_p} : votre coût unitaire augmente",
                f"De {_n(prec['produits'][nom_p]['cout_unitaire'])} à "
                f"{_n(dp['cout_unitaire'])} HTG en un trimestre "
                f"(contexte : {faits['intrants'].lower()}).",
                "Sans investissement en R&D procédé, vous subissez pleinement "
                "l'inflation et les chocs sur les intrants, contrairement aux "
                "concurrents qui investissent."))

    # --- FINANCE : rentabilité, structure, trésorerie -------------------
    if er["benefice_net"] < 0:
        diagnostics.append(Diagnostic(
            "perte", "Finance", A, "Trimestre déficitaire",
            f"Perte nette de {_n(abs(er['benefice_net']))} HTG pour "
            f"{_n(er['revenus'])} HTG de revenus. Charges de structure : "
            f"{_n(er['couts_fixes'] + er['amortissement'])} HTG.",
            "Identifiez la cause : volume insuffisant, marge trop faible, ou "
            "budgets discrétionnaires trop élevés pour votre niveau d'activité."))
    elif ratios.get("marge_nette", 0) > 0.10:
        diagnostics.append(Diagnostic(
            "marge_solide", "Finance", P, "Rentabilité solide",
            f"Marge nette de {_pct(ratios['marge_nette'])} et rendement des "
            f"capitaux propres de {_pct(ratios.get('roe', 0))}.",
            "Votre modèle dégage de la valeur : la question devient celle du "
            "réinvestissement (capacité, R&D) pour installer l'avantage."))

    if ind.get("dette_urgence_tiree", 0) > 0:
        diagnostics.append(Diagnostic(
            "decouvert", "Finance", A, "Recours au découvert d'urgence",
            f"{_n(ind['dette_urgence_tiree'])} HTG de découvert automatique, "
            f"à un taux nettement supérieur à celui d'un emprunt planifié.",
            "La trésorerie s'est épuisée en cours de trimestre. Un emprunt "
            "anticipé coûte moins cher qu'un découvert subi : planifiez vos "
            "besoins de financement avant de dépenser."))

    if ratios.get("dette_actif", 0) > 0.55:
        diagnostics.append(Diagnostic(
            "levier", "Finance", A, "Endettement élevé",
            f"Dette / actif à {_pct(ratios['dette_actif'])}"
            + (f", couverture des intérêts de {ratios['couverture_interets']:.1f}"
               if ratios.get("couverture_interets") else "") + ".",
            "Le levier amplifie les gains mais aussi les pertes. En cas de "
            "ralentissement annoncé, une structure trop endettée devient "
            "fragile."))

    if ratios.get("rotation_stocks") is not None and ratios["rotation_stocks"] < 1.0:
        diagnostics.append(Diagnostic(
            "rotation_faible", "Finance", A, "Rotation des stocks faible",
            f"Rotation de {ratios['rotation_stocks']:.2f} : vos stocks "
            f"s'écoulent lentement.",
            "Du capital dort en marchandises. C'est de la trésorerie qui "
            "n'est pas disponible pour la R&D ou la capacité."))

    # --- TRAJECTOIRE : rang et croissance ------------------------------
    if partie.classements:
        def rang_dans(instantane):
            for i, l in enumerate(instantane["classement"], 1):
                if l["nom"] == nom_equipe:
                    return i
            return None
        rang = rang_dans(partie.classements[idx]) if idx < len(partie.classements) else None
        rang_prec = rang_dans(partie.classements[idx - 1]) if idx > 0 else None
        total = len(sim.equipes)
        faits["rang"] = rang
        if rang and rang_prec and rang != rang_prec:
            gain = rang_prec - rang
            diagnostics.append(Diagnostic(
                "trajectoire", "Trajectoire", P if gain > 0 else A,
                "Vous progressez au classement" if gain > 0
                else "Vous reculez au classement",
                f"De la {rang_prec}e à la {rang}e place sur {total} "
                f"({gain:+d}).",
                "Le score combine rentabilité, solvabilité, gestion, croissance "
                "et part de marché : identifiez le critère qui a bougé."))
        elif rang:
            diagnostics.append(Diagnostic(
                "trajectoire", "Trajectoire", N, "Position stable",
                f"Vous occupez la {rang}e place sur {total}.",
                "Pour progresser, ciblez le critère du score où votre écart "
                "avec les meneurs est le plus grand."))

    if ratios.get("croissance_revenus") is not None:
        cr = ratios["croissance_revenus"]
        if cr < -0.15:
            diagnostics.append(Diagnostic(
                "revenus_baisse", "Trajectoire", A, "Vos revenus reculent",
                f"Baisse de {_pct(abs(cr))} par rapport au trimestre précédent "
                f"(contexte : {faits['conjoncture'].lower()}).",
                "Distinguez ce qui vient du marché de ce qui vient de vos "
                "décisions : le marché a-t-il reculé autant que vous ?"))
        elif cr > 0.15:
            diagnostics.append(Diagnostic(
                "revenus_hausse", "Trajectoire", P, "Croissance des revenus",
                f"Hausse de {_pct(cr)} par rapport au trimestre précédent.",
                "Vérifiez que cette croissance est rentable : un chiffre "
                "d'affaires qui monte avec une marge qui fond est un piège."))

    return {"equipe": nom_equipe, "trimestre": rap["trimestre"],
            "diagnostics": diagnostics, "faits": faits}


# ----------------------------------------------------------------------
# 2) RÉDACTION — transforme les diagnostics en texte pédagogique
# ----------------------------------------------------------------------
ICONES = {"positif": "✅", "alerte": "⚠️", "neutre": "•"}


def rediger(analyse: dict, pour_professeur: bool = False) -> str:
    """Débriefing en Markdown. La version professeur ajoute une synthèse
    des points à travailler, utile pour animer le retour en classe."""
    d = analyse["diagnostics"]
    faits = analyse["faits"]
    if not d:
        return ("Aucun élément marquant à signaler pour ce trimestre : "
                "vos décisions sont restées dans les équilibres attendus.")

    lignes = [f"**{analyse['equipe']} — débriefing du trimestre "
              f"{analyse['trimestre']}**",
              f"*Contexte : {faits.get('conjoncture', '—')} · "
              f"{faits.get('intrants', '—')}*", ""]

    alertes = [x for x in d if x.ton == "alerte"]
    reussites = [x for x in d if x.ton == "positif"]
    if reussites and not alertes:
        lignes.append("Trimestre maîtrisé : aucun signal d'alerte majeur.")
    elif alertes:
        lignes.append(f"{len(alertes)} point"
                      f"{'s' if len(alertes) > 1 else ''} de vigilance "
                      f"ce trimestre" +
                      (f", et {len(reussites)} réussite"
                       f"{'s' if len(reussites) > 1 else ''} à consolider."
                       if reussites else "."))
    lignes.append("")

    for categorie in ["Décisions", "Marché", "Production", "Coûts", "Finance",
                      "Trajectoire"]:
        bloc = [x for x in d if x.categorie == categorie]
        if not bloc:
            continue
        lignes.append(f"**{categorie}**")
        for x in bloc:
            lignes.append(f"{ICONES[x.ton]} *{x.titre}.* {x.constat} {x.lecture}")
        lignes.append("")

    if pour_professeur:
        cles = [x.titre for x in alertes]
        lignes.append("---")
        lignes.append("**Pour l'animation en classe**")
        if cles:
            lignes.append("Points à faire verbaliser par l'équipe : "
                          + " ; ".join(cles[:4]) + ".")
        lignes.append("Question de relance suggérée : « Quelle décision de ce "
                      "trimestre referiez-vous différemment, et sur quel "
                      "indicateur vous appuyez-vous pour le dire ? »")

    return "\n".join(lignes)


def debriefing(partie, nom_equipe: str, index_trimestre: int = -1,
               pour_professeur: bool = False) -> str:
    """Raccourci : analyse puis rédaction."""
    return rediger(analyser(partie, nom_equipe, index_trimestre),
                   pour_professeur=pour_professeur)
