"""
STRATÈJ — Interface v4 (ratios, classement pondérable, conjonctures en texte)
=================================================================
Fichiers requis dans le même dossier :
  stratej_moteur_v2.py, stratej_partie_v2.py, app_stratej_v4.py

Lancer avec :  streamlit run app_stratej_v4.py
"""

import os

import altair as alt
import pandas as pd
import streamlit as st

from stratej_moteur_v2 import (Parametres, Produit, Decisions,
                               DecisionsProduit, Simulation)
from stratej_partie_v2 import (Partie, sauvegarder_parties, charger_parties)

st.set_page_config(page_title="Stratèj", page_icon="📊", layout="wide")

# Identité visuelle : marine + or (mêmes couleurs que le document de projet)
st.markdown("""
<style>
[data-testid="stMetric"] {
    background: #F7F9FC;
    border: 1px solid #E3E8F0;
    border-left: 4px solid #1F3864;
    border-radius: 10px;
    padding: 12px 16px;
}
[data-testid="stMetricLabel"] p { color: #5A6B87; font-size: 0.85rem; }
button[data-baseweb="tab"] { font-weight: 600; }
.bandeau {
    background: linear-gradient(100deg, #1F3864 0%, #2E5FA3 100%);
    border-bottom: 3px solid #C9A227;
    border-radius: 12px;
    padding: 18px 26px;
    margin-bottom: 18px;
}
.bandeau h1 { color: #FFFFFF; font-size: 1.55rem; margin: 0; letter-spacing: .3px; }
.bandeau p  { color: #C9D6EA; margin: 4px 0 0 0; font-size: .95rem; }
</style>
""", unsafe_allow_html=True)


def entete(titre, sous_titre=""):
    st.markdown('<div class="bandeau"><h1>' + titre + '</h1>'
                + ('<p>' + sous_titre + '</p>' if sous_titre else '')
                + '</div>', unsafe_allow_html=True)


def rang_equipe(partie, nom):
    """Rang actuel de l'équipe et rang au trimestre précédent (ou None)."""
    if not partie.classements:
        return None, None
    def rang_dans(instantane):
        for i, l in enumerate(instantane["classement"], 1):
            if l["nom"] == nom:
                return i
        return None
    actuel = rang_dans(partie.classements[-1])
    precedent = rang_dans(partie.classements[-2]) if len(partie.classements) >= 2 else None
    return actuel, precedent


def ordinal(n):
    return "1er" if n == 1 else f"{n}e"


@st.dialog("Confirmation")
def dialogue_confirmation(nom, trimestre):
    st.success(f"Les décisions du trimestre {trimestre} ont bien été soumises "
               f"pour **{nom}**. ✅")
    st.write("Vous pouvez encore les modifier tant que l'animateur n'a pas "
             "lancé le calcul du trimestre.")
    if st.button("Compris"):
        st.rerun()


def barre_capacite(total_prod, capacite):
    pct = total_prod / capacite * 100 if capacite > 0 else 0
    couleur = "#C0392B" if total_prod > capacite else "#1F3864"
    largeur = min(pct, 100)
    st.markdown(
        f'<div style="margin:6px 0 4px 0;font-size:.9rem;color:#5A6B87;">'
        f'Capacité utilisée : {total_prod:,.0f} / {capacite:,.0f} u ({pct:.0f} %)</div>'
        f'<div style="background:#E3E8F0;border-radius:6px;height:14px;">'
        f'<div style="width:{largeur}%;background:{couleur};height:14px;'
        f'border-radius:6px;"></div></div>',
        unsafe_allow_html=True)


@st.cache_resource
def etat_partage():
    return {"parties": charger_parties()}


NIVEAUX_DEMANDE = {
    "Forte récession": 0.80, "Récession": 0.88, "Ralentissement": 0.95,
    "Stable": 1.00, "Croissance modérée": 1.05, "Expansion": 1.12,
    "Forte expansion": 1.20,
}
NIVEAUX_COUT = {
    "Baisse des coûts": 0.93, "Coûts stables": 1.00,
    "Hausse modérée des intrants": 1.08, "Forte hausse des intrants": 1.15,
    "Flambée des coûts": 1.25,
}
NOMS_CRITERES = {
    "rentabilite": "Rentabilité", "solvabilite": "Solvabilité",
    "gestion": "Gestion", "croissance": "Croissance", "part_marche": "Part de marché",
}

etat = etat_partage()

st.sidebar.title("📊 Stratèj")
st.sidebar.caption("Simulation d'entreprise — v4")
role = st.sidebar.radio("Je suis :", ["Équipe", "Animateur"], horizontal=True)
if st.sidebar.button("🔄 Actualiser la page"):
    st.rerun()


# ----------------------------------------------------------------------
# Éléments réutilisables
# ----------------------------------------------------------------------
def afficher_bulletin(bulletin):
    st.subheader(f"Bulletin de marché — trimestre {bulletin['trimestre']}")
    c1, c2 = st.columns(2)
    c1.metric("Conjoncture de la demande",
              bulletin.get("conjoncture_label", f"{bulletin['conjoncture']:.2f}"))
    c2.metric("Coût des intrants",
              bulletin.get("indice_cout_label", f"{bulletin['indice_cout']:.2f}"))
    for nom_p, m in bulletin["produits"].items():
        st.markdown(f"**{nom_p}** — demande totale {m['demande_totale']:,.0f} u · "
                    f"prix moyen {m['prix_moyen']:,.0f} HTG")
        st.dataframe(pd.DataFrame([{
            "Équipe": eq["nom"],
            "Prix affiché (HTG)": round(eq["prix"]),
            "Part de marché (%)": round(eq["part_marche"] * 100, 1),
            "Rupture de stock": "Oui" if eq["rupture_stock"] else "",
        } for eq in m["equipes"]]), hide_index=True, use_container_width=True)


def afficher_etats_financiers(rapport):
    er, bi = rapport["etat_resultats"], rapport["bilan"]
    ca, cb = st.columns(2)
    with ca:
        st.markdown("**État des résultats (HTG)**")
        st.dataframe(pd.DataFrame({
            "Poste": ["Revenus", "CMV", "Coûts fixes", "Marketing", "R&D",
                      "Force de vente", "Stockage", "Amortissement", "Intérêts",
                      "Bénéfice avant impôt", "Impôt", "Bénéfice net"],
            "Montant": [round(er["revenus"]), -round(er["cmv"]), -round(er["couts_fixes"]),
                        -round(er["marketing"]), -round(er["rd"]),
                        -round(er["force_vente"]), -round(er["stockage"]),
                        -round(er["amortissement"]), -round(er["interets"]),
                        round(er["benefice_avant_impot"]), -round(er["impot"]),
                        round(er["benefice_net"])],
        }), hide_index=True, use_container_width=True)
    with cb:
        st.markdown("**Bilan (HTG)**")
        st.dataframe(pd.DataFrame({
            "Poste": ["Encaisse", "Stocks", "Immobilisations nettes", "ACTIF TOTAL",
                      "Dette", "Dette d'urgence", "Capitaux propres"],
            "Montant": [round(bi["encaisse"]), round(bi["stocks"]),
                        round(bi["immobilisations_nettes"]), round(bi["actif_total"]),
                        round(bi["dette"]), round(bi["dette_urgence"]),
                        round(bi["capitaux_propres"])],
        }), hide_index=True, use_container_width=True)


def afficher_detail_produits(rapport):
    st.markdown("**Détail par produit**")
    st.dataframe(pd.DataFrame([{
        "Produit": nom_p,
        "Ventes (u)": round(dp["ventes"]),
        "Prix (HTG)": round(dp["prix"]),
        "Coût unitaire (HTG)": round(dp["cout_unitaire"], 1),
        "Revenus (HTG)": round(dp["revenus"]),
        "Marge brute (HTG)": round(dp["marge_brute"]),
        "Stock restant (u)": round(dp["stock_unites"]),
        "Qualité": round(dp["qualite"], 2),
        "Efficacité (%)": round(dp["efficacite"] * 100, 1),
    } for nom_p, dp in rapport["produits"].items()]),
        hide_index=True, use_container_width=True)


def fmt_ratio(v, pct=False):
    if v is None:
        return "—"
    return f"{v*100:.1f} %" if pct else f"{v:.2f}"


def afficher_ratios(rapport):
    ra = rapport.get("ratios")
    if not ra:
        return
    st.markdown("**Ratios financiers du trimestre**")
    st.dataframe(pd.DataFrame([
        {"Catégorie": "Rentabilité", "Ratio": "Marge nette",
         "Valeur": fmt_ratio(ra["marge_nette"], pct=True)},
        {"Catégorie": "Rentabilité", "Ratio": "Rendement des capitaux propres (ROE)",
         "Valeur": fmt_ratio(ra["roe"], pct=True)},
        {"Catégorie": "Rentabilité", "Ratio": "Rendement de l'actif (ROA)",
         "Valeur": fmt_ratio(ra["roa"], pct=True)},
        {"Catégorie": "Gestion", "Ratio": "Rotation de l'actif",
         "Valeur": fmt_ratio(ra["rotation_actif"])},
        {"Catégorie": "Gestion", "Ratio": "Rotation des stocks",
         "Valeur": fmt_ratio(ra["rotation_stocks"])},
        {"Catégorie": "Solvabilité", "Ratio": "Dette / Actif",
         "Valeur": fmt_ratio(ra["dette_actif"], pct=True)},
        {"Catégorie": "Solvabilité", "Ratio": "Couverture des intérêts",
         "Valeur": fmt_ratio(ra["couverture_interets"])},
        {"Catégorie": "Croissance", "Ratio": "Croissance des revenus (vs T-1)",
         "Valeur": fmt_ratio(ra["croissance_revenus"], pct=True)},
    ]), hide_index=True, use_container_width=True)


def afficher_classement(lignes):
    st.dataframe(pd.DataFrame([{
        "Rang": i + 1, "Équipe": l["nom"], "Score": round(l["score"], 1),
        "Rentabilité (profit cumulé, HTG)": round(l["rentabilite"]),
        "Solvabilité (CP/Actif)": f"{l['solvabilite']*100:.1f} %",
        "Gestion (rotation actif)": f"{l['gestion']:.2f}",
        "Croissance revenus": f"{l['croissance']*100:.1f} %",
        "Part de marché moy.": f"{l['part_marche']*100:.1f} %",
    } for i, l in enumerate(lignes)]), hide_index=True, use_container_width=True)


def graphique_parts(sim):
    if not sim.equipes or not sim.equipes[0].parts_historiques:
        return
    df = pd.DataFrame({e.nom: [p * 100 for p in e.parts_historiques] for e in sim.equipes})
    df.index = [f"T{i+1}" for i in range(len(df))]
    st.caption("Parts de marché globales (%) — information publique")
    st.line_chart(df)


def formulaire_decisions(partie, e, cle):
    """Formulaire complet d'une équipe : une section par produit + entreprise."""
    sim = partie.sim
    par = sim.par
    couts = sim.couts_unitaires_courants(e)
    base = partie.soumissions.get(e.nom) or e.dernieres_decisions

    d = Decisions()
    total_prod = 0.0
    for p in par.produits:
        ep = e.etats_produits[p.nom]
        bp = base.produits.get(p.nom, DecisionsProduit(prix=p.prix_reference))
        with st.expander(f"📦 {p.nom}", expanded=True):
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Coût unitaire actuel", f"{couts[p.nom]:,.1f} HTG")
            i2.metric("Stock disponible", f"{ep.stock_unites:,.0f} u")
            i3.metric("Indice qualité", f"{ep.qualite:.2f}")
            i4.metric("Efficacité acquise", f"{ep.efficacite*100:.1f} %")
            c1, c2 = st.columns(2)
            with c1:
                prod = st.number_input(f"Production (u) — {p.nom}", 0.0,
                                       value=float(bp.production), step=1_000.0,
                                       key=f"pr{cle}{p.nom}")
                prix = st.number_input(f"Prix de vente (HTG) — {p.nom}", 1.0,
                                       value=float(bp.prix), step=5.0,
                                       key=f"px{cle}{p.nom}")
                mkt = st.number_input(f"Marketing (HTG) — {p.nom}", 0.0,
                                      value=float(bp.marketing), step=100_000.0,
                                      key=f"mk{cle}{p.nom}")
            with c2:
                rdq = st.number_input(f"R&D qualité (HTG) — {p.nom}", 0.0,
                                      value=float(bp.rd_qualite), step=100_000.0,
                                      key=f"rq{cle}{p.nom}",
                                      help="Améliore l'attractivité du produit.")
                rdp = st.number_input(f"R&D procédé (HTG) — {p.nom}", 0.0,
                                      value=float(bp.rd_procede), step=100_000.0,
                                      key=f"rp{cle}{p.nom}",
                                      help="Réduit durablement le coût unitaire "
                                           f"(plafond {p.efficacite_max*100:.0f} %).")
            d.produits[p.nom] = DecisionsProduit(production=prod, prix=prix,
                                                 marketing=mkt, rd_qualite=rdq,
                                                 rd_procede=rdp)
            total_prod += prod

    barre_capacite(total_prod, e.capacite)
    if total_prod > e.capacite:
        st.warning("Production totale supérieure à la capacité : elle sera "
                   "plafonnée et répartie au prorata entre les produits.")

    with st.expander("🏢 Décisions d'entreprise", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            d.force_vente = st.number_input(
                "Salaires de la force de vente (HTG)", 0.0,
                value=float(base.force_vente), step=100_000.0, key=f"fv{cle}",
                help="Une force de vente mieux payée vend plus facilement "
                     "(tous produits), à rendements décroissants.")
            d.invest_capacite = st.number_input(
                "Investissement en capacité (HTG)", 0.0,
                value=float(base.invest_capacite), step=500_000.0, key=f"ic{cle}",
                help=f"{par.cout_capacite:,.0f} HTG par unité de capacité ; "
                     "disponible au trimestre suivant.")
        with c2:
            d.nouvel_emprunt = st.number_input(
                "Nouvel emprunt (HTG)", 0.0, value=float(base.nouvel_emprunt),
                step=500_000.0, key=f"ne{cle}")
            if e.dette > 0:
                d.remboursement = st.number_input(
                    "Remboursement de dette (HTG)", 0.0,
                    max_value=float(e.dette),
                    value=float(min(base.remboursement, e.dette)),
                    step=500_000.0, key=f"rb{cle}",
                    help=f"Dette en cours : {e.dette:,.0f} HTG.")
            else:
                d.remboursement = 0.0
                st.caption("💳 Aucune dette en cours : rien à rembourser.")

    # ------ Budget de trésorerie : on ne dépense pas ce qu'on n'a pas ------
    cout_prod_prevu = sum(d.produits[p.nom].production * couts[p.nom]
                          for p in par.produits)
    depenses = (cout_prod_prevu + d.force_vente + d.invest_capacite
                + d.remboursement
                + sum(dp.marketing + dp.rd_qualite + dp.rd_procede
                      for dp in d.produits.values()))
    dispo = e.encaisse + d.nouvel_emprunt
    st.markdown("**Budget de trésorerie du trimestre**")
    b1, b2, b3 = st.columns(3)
    b1.metric("Ressources disponibles", f"{dispo:,.0f} HTG",
              help="Encaisse + nouvel emprunt. Les revenus des ventes ne sont "
                   "pas garantis : on ne budgète pas un argent qu'on n'a pas "
                   "encore encaissé.")
    b2.metric("Dépenses engagées", f"{depenses:,.0f} HTG",
              help="Coût de production prévu + marketing + R&D + force de "
                   "vente + investissement + remboursement.")
    b3.metric("Marge de manœuvre", f"{dispo - depenses:,.0f} HTG")
    budget_ok = depenses <= dispo + 1e-6
    if not budget_ok:
        st.error("🚫 Vos dépenses dépassent vos ressources. Sans nouvel "
                 "emprunt ni levée de fonds, l'entreprise ne peut compter que "
                 "sur ses ressources internes : réduisez production, budgets "
                 "ou investissement — ou financez-vous.")
    return d, budget_ok


# ======================================================================
# PORTAIL ANIMATEUR
# ======================================================================
if role == "Animateur":
    parties = etat["parties"]
    if not parties or st.session_state.get("mode_creation"):
        entete("Stratèj", "Créer une nouvelle partie")
        if parties and st.button("← Retour aux parties existantes"):
            st.session_state.mode_creation = False
            st.rerun()
        nom_partie_new = st.text_input(
            "Nom de la partie", f"Groupe {len(parties) + 1}",
            help="Chaque partie est indépendante : un même animateur peut en "
                 "mener plusieurs en parallèle (un par groupe d'étudiants).")
        c1, c2, c3 = st.columns(3)
        noms_txt = c1.text_area("Équipes (une par ligne)",
                                "Équipe 1\nÉquipe 2\nÉquipe 3\nÉquipe 4", height=120)
        nb = c2.number_input("Nombre de trimestres", 4, 16, 8)
        code = c3.text_input("Code d'accès animateur", "PROF")

        st.subheader("Produits du scénario")
        st.caption("Ajoute, retire ou modifie les produits directement dans le tableau.")
        df_produits = st.data_editor(pd.DataFrame([
            {"Nom": "Jus naturel", "Demande de base (u/trim.)": 90_000,
             "Prix de référence (HTG)": 250, "Coût variable initial (HTG)": 100},
            {"Nom": "Confiture", "Demande de base (u/trim.)": 45_000,
             "Prix de référence (HTG)": 400, "Coût variable initial (HTG)": 180},
        ]), num_rows="dynamic", use_container_width=True)

        st.subheader("Environnement économique")
        st.caption("Choisis, pour chaque trimestre, la conjoncture de la demande et "
                   "l'évolution du coût des intrants — les joueurs verront ces libellés.")
        defaut_demande = ["Stable", "Croissance modérée", "Récession", "Stable",
                          "Expansion", "Forte récession", "Ralentissement",
                          "Croissance modérée"]
        defaut_cout = ["Coûts stables", "Coûts stables", "Forte hausse des intrants",
                       "Hausse modérée des intrants", "Coûts stables",
                       "Hausse modérée des intrants", "Coûts stables", "Coûts stables"]
        nb_i = int(nb)
        df_env = st.data_editor(pd.DataFrame({
            "Trimestre": [f"T{i+1}" for i in range(nb_i)],
            "Conjoncture de la demande": [defaut_demande[i % len(defaut_demande)]
                                          for i in range(nb_i)],
            "Coût des intrants": [defaut_cout[i % len(defaut_cout)]
                                  for i in range(nb_i)],
        }), column_config={
            "Trimestre": st.column_config.TextColumn(disabled=True),
            "Conjoncture de la demande": st.column_config.SelectboxColumn(
                options=list(NIVEAUX_DEMANDE.keys()), required=True),
            "Coût des intrants": st.column_config.SelectboxColumn(
                options=list(NIVEAUX_COUT.keys()), required=True),
        }, hide_index=True, use_container_width=True)

        st.subheader("Pondération du classement")
        st.caption("Ajuste l'importance de chaque critère selon l'objectif du cours "
                   "(les poids sont normalisés automatiquement).")
        pc1, pc2, pc3, pc4, pc5 = st.columns(5)
        poids = {
            "rentabilite": pc1.number_input("Rentabilité", 0, 100, 30, 5),
            "solvabilite": pc2.number_input("Solvabilité", 0, 100, 20, 5),
            "gestion": pc3.number_input("Gestion", 0, 100, 15, 5),
            "croissance": pc4.number_input("Croissance", 0, 100, 15, 5),
            "part_marche": pc5.number_input("Part de marché", 0, 100, 20, 5),
        }

        with st.expander("⚙️ Paramètres avancés"):
            c1, c2, c3 = st.columns(3)
            with c1:
                capa = st.number_input("Capacité de production initiale (u/trim.)",
                                       1_000.0, value=35_000.0, step=1_000.0)
                cout_capa = st.number_input("Coût d'une unité de capacité (HTG)",
                                            1.0, value=400.0, step=50.0)
                encaisse = st.number_input("Encaisse initiale (HTG)", 0.0,
                                           value=8_000_000.0, step=500_000.0)
            with c2:
                fixes = st.number_input("Coûts fixes trimestriels (HTG)", 0.0,
                                        value=1_200_000.0, step=100_000.0)
                inflation = st.number_input("Inflation trimestrielle", 0.0, 0.2,
                                            0.03, 0.005, format="%.3f")
                croissance = st.number_input("Croissance du marché / trimestre",
                                             -0.1, 0.2, 0.01, 0.005, format="%.3f")
            with c3:
                fv_ref = st.number_input("Force de vente de référence (HTG)", 1.0,
                                         value=800_000.0, step=100_000.0)
                taux = st.number_input("Taux d'intérêt trimestriel", 0.0, 0.3,
                                       0.03, 0.005, format="%.3f")
                impot = st.number_input("Taux d'imposition", 0.0, 0.6, 0.30, 0.05,
                                        format="%.2f")

        if st.button("Créer la partie", type="primary"):
            noms = [n.strip() for n in noms_txt.splitlines() if n.strip()]
            produits = []
            for _, ligne in df_produits.iterrows():
                if str(ligne["Nom"]).strip():
                    produits.append(Produit(
                        nom=str(ligne["Nom"]).strip(),
                        demande_base=float(ligne["Demande de base (u/trim.)"]),
                        prix_reference=float(ligne["Prix de référence (HTG)"]),
                        cout_variable_base=float(ligne["Coût variable initial (HTG)"]),
                    ))
            labels_demande = list(df_env["Conjoncture de la demande"])
            labels_cout = list(df_env["Coût des intrants"])
            par = Parametres(
                nb_trimestres=int(nb), produits=produits or [Produit()],
                conjoncture=[NIVEAUX_DEMANDE.get(l, 1.0) for l in labels_demande],
                indice_cout=[NIVEAUX_COUT.get(l, 1.0) for l in labels_cout],
                conjoncture_labels=labels_demande, indice_cout_labels=labels_cout,
                capacite_initiale=capa, cout_capacite=cout_capa,
                encaisse_initiale=encaisse, couts_fixes=fixes,
                inflation_trimestrielle=inflation, croissance_trimestrielle=croissance,
                force_vente_reference=fv_ref, taux_interet=taux, taux_impot=impot,
            )
            if not nom_partie_new.strip():
                st.error("Donne un nom à la partie.")
            elif nom_partie_new.strip() in parties:
                st.error("Une partie porte déjà ce nom — choisis-en un autre.")
            else:
                parties[nom_partie_new.strip()] = Partie(
                    noms, par, code, poids_classement=poids)
                sauvegarder_parties(parties)
                st.session_state.mode_creation = False
                st.rerun()
        st.stop()

    nom_partie = st.sidebar.selectbox("🗂️ Partie active", sorted(parties))
    if st.sidebar.button("➕ Nouvelle partie"):
        st.session_state.mode_creation = True
        st.rerun()
    partie = parties[nom_partie]

    autorisees = st.session_state.setdefault("anim_auth", set())
    if nom_partie not in autorisees:
        entete("Stratèj — Animateur", f"Partie « {nom_partie} » — accès protégé")
        code_saisi = st.text_input("Code d'accès animateur", type="password")
        if st.button("Entrer"):
            if code_saisi.strip().upper() == partie.code_animateur:
                autorisees.add(nom_partie)
                st.rerun()
            else:
                st.error("Code incorrect.")
        st.stop()

    sim = partie.sim
    entete("Stratèj — Animateur",
           f"Partie « {nom_partie} » — pilotage, résultats et classement")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trimestre", f"{min(sim.t + 1, sim.par.nb_trimestres)} / {sim.par.nb_trimestres}")
    c2.metric("Soumissions", f"{len(partie.soumissions)} / {len(sim.equipes)}")
    c3.metric("Produits", len(sim.par.produits))
    c4.metric("Statut", "Terminée" if partie.terminee else "En cours")

    onglets = st.tabs(["🎮 Ronde en cours", "📈 Résultats", "🏆 Classement",
                       "🔑 Codes d'accès", "⚙️ Administration"])

    with onglets[0]:
        if partie.terminee:
            st.success("La partie est terminée. Consultez le classement final.")
        else:
            st.write(f"Trimestre {sim.t + 1} — demande : "
                     f"**{sim.par.label_conjoncture_t(sim.t)}** · intrants : "
                     f"**{sim.par.label_indice_cout_t(sim.t)}**")
            st.dataframe(pd.DataFrame([{
                "Équipe": e.nom,
                "Soumission": "✅ Reçue" if e.nom in partie.soumissions else "⏳ En attente",
            } for e in sim.equipes]), hide_index=True, use_container_width=True)
            manquantes = [e.nom for e in sim.equipes if e.nom not in partie.soumissions]
            if manquantes:
                st.warning("Sans soumission (reconduction automatique au lancement) : "
                           + ", ".join(manquantes))
            if st.button("🚀 Lancer le calcul du trimestre", type="primary"):
                partie.lancer_trimestre()
                sauvegarder_parties(parties)
                st.rerun()

    with onglets[1]:
        if not partie.historique:
            st.info("Aucun trimestre joué pour l'instant.")
        else:
            choix_t = st.selectbox("Trimestre", list(range(len(partie.historique), 0, -1)))
            res = partie.historique[choix_t - 1]
            afficher_bulletin(res["bulletin"])
            st.subheader("Résultats consolidés des équipes")
            st.dataframe(pd.DataFrame([{
                "Équipe": nom,
                "Revenus (HTG)": round(r["etat_resultats"]["revenus"]),
                "Bénéfice net (HTG)": round(r["etat_resultats"]["benefice_net"]),
                "Encaisse (HTG)": round(r["bilan"]["encaisse"]),
                "Dette totale (HTG)": round(r["bilan"]["dette"] + r["bilan"]["dette_urgence"]),
                "Stock (u)": round(r["indicateurs"]["stock_unites"]),
                "Notes": " · ".join(r["ajustements"]),
            } for nom, r in res["rapports"].items()]),
                hide_index=True, use_container_width=True)
            graphique_parts(sim)
            st.caption("Profit cumulé (HTG)")
            df_profit = pd.DataFrame({e.nom: [r["indicateurs"]["profit_cumule"]
                                              for r in e.rapports] for e in sim.equipes})
            df_profit.index = [f"T{i+1}" for i in range(len(df_profit))]
            st.line_chart(df_profit)
            st.subheader("Détail par équipe")
            for onglet_e, e in zip(st.tabs([e.nom for e in sim.equipes]), sim.equipes):
                with onglet_e:
                    rap = e.rapports[choix_t - 1]
                    afficher_detail_produits(rap)
                    afficher_etats_financiers(rap)
                    afficher_ratios(rap)

    with onglets[2]:
        if partie.historique:
            total_p = sum(partie.poids_classement.values()) or 1
            st.caption("Pondération actuelle : " + " · ".join(
                f"{NOMS_CRITERES[k]} {v/total_p*100:.0f} %"
                for k, v in partie.poids_classement.items()))
            afficher_classement(sim.classement(partie.poids_classement))

            st.subheader("Historique du classement")
            if partie.classements:
                lignes_scores = {}
                lignes_rangs = {}
                for instantane in partie.classements:
                    for rang, l in enumerate(instantane["classement"], 1):
                        lignes_scores.setdefault(l["nom"], []).append(round(l["score"], 1))
                        lignes_rangs.setdefault(l["nom"], []).append(rang)
                index_t = [f"T{c['trimestre']}" for c in partie.classements]
                df_scores = pd.DataFrame(lignes_scores, index=index_t)
                st.caption("Évolution des scores")
                st.line_chart(df_scores)
                with st.expander("Rang de chaque équipe, trimestre par trimestre"):
                    st.dataframe(pd.DataFrame(lignes_rangs, index=index_t).T,
                                 use_container_width=True)
        else:
            st.info("Le classement apparaîtra après le premier trimestre.")

    with onglets[3]:
        st.write("À distribuer aux équipes (chaque équipe garde son code confidentiel) :")
        st.dataframe(pd.DataFrame([{"Équipe": n, "Code d'accès": c}
                                   for n, c in partie.codes.items()]),
                     hide_index=True, use_container_width=True)

    with onglets[4]:
        st.subheader("Pondération du classement")
        st.caption("Modifiable en cours de partie ; s'applique au classement courant "
                   "et aux prochains instantanés.")
        pc1, pc2, pc3, pc4, pc5 = st.columns(5)
        colonnes_p = [pc1, pc2, pc3, pc4, pc5]
        nouveaux_poids = {}
        for col, (cle, libelle) in zip(colonnes_p, NOMS_CRITERES.items()):
            nouveaux_poids[cle] = col.number_input(
                libelle, 0, 100, int(partie.poids_classement.get(cle, 20)), 5,
                key=f"poids_{cle}")
        if st.button("Enregistrer la pondération"):
            partie.poids_classement = nouveaux_poids
            sauvegarder_parties(parties)
            st.success("Pondération mise à jour.")

        st.divider()
        st.error("Zone sensible")
        if st.button(f"🗑️ Supprimer la partie « {nom_partie} » (irréversible)"):
            del parties[nom_partie]
            sauvegarder_parties(parties)
            st.rerun()

# ======================================================================
# PORTAIL ÉQUIPE
# ======================================================================
else:
    entete("Stratèj — Portail d'équipe",
           "Décisions trimestrielles et résultats de votre entreprise")
    parties = etat["parties"]
    if not parties:
        st.info("Aucune partie en cours. L'animateur doit d'abord créer une partie.")
        st.stop()

    ctx = st.session_state.get("equipe_ctx")
    valide = (ctx is not None and ctx[0] in parties
              and any(x.nom == ctx[1] for x in parties[ctx[0]].sim.equipes))
    if not valide:
        c0, c1, c2 = st.columns(3)
        nom_partie = c0.selectbox("Partie", sorted(parties))
        partie = parties[nom_partie]
        nom = c1.selectbox("Mon équipe", [x.nom for x in partie.sim.equipes])
        code = c2.text_input("Code d'accès", type="password")
        if st.button("Se connecter", type="primary"):
            if code.strip().upper() == partie.codes.get(nom, "").upper():
                st.session_state.equipe_ctx = (nom_partie, nom)
                st.rerun()
            else:
                st.error("Code incorrect — demandez votre code à l'animateur.")
        st.stop()

    nom_partie, nom = ctx
    partie = parties[nom_partie]
    sim = partie.sim
    e = next(x for x in sim.equipes if x.nom == nom)
    st.sidebar.success(f"Connecté : {nom} · {nom_partie}")
    if st.sidebar.button("Se déconnecter"):
        del st.session_state.equipe_ctx
        st.rerun()

    st.subheader(f"{nom} — trimestre "
                 f"{min(sim.t + 1, sim.par.nb_trimestres)} / {sim.par.nb_trimestres}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Encaisse", f"{e.encaisse:,.0f} HTG")
    c2.metric("Capacité", f"{e.capacite:,.0f} u")
    c3.metric("Stock total", f"{e.stock_unites_total:,.0f} u")
    c4.metric("Dette totale", f"{e.dette + e.dette_urgence:,.0f} HTG")
    rang, rang_prec = rang_equipe(partie, nom)
    if rang is None:
        c5.metric("Classement", "—",
                  help="Votre rang apparaîtra après le premier trimestre.")
    else:
        variation = None
        if rang_prec is not None and rang_prec != rang:
            gain = rang_prec - rang
            variation = f"{gain:+d} place" + ("s" if abs(gain) > 1 else "")
        c5.metric("Classement", f"{ordinal(rang)} / {len(sim.equipes)}",
                  delta=variation,
                  help="Score composite selon la pondération fixée par l'animateur.")

    onglets = st.tabs(["📝 Mes décisions", "📊 Mes résultats", "🌍 Le marché"])

    with onglets[0]:
        if partie.terminee:
            st.success("La partie est terminée.")
        else:
            st.write(f"Conjoncture annoncée — demande : "
                     f"**{sim.par.label_conjoncture_t(sim.t)}** · intrants : "
                     f"**{sim.par.label_indice_cout_t(sim.t)}**")
            cf = sim.par.couts_fixes_t(sim.t)
            amort = min(e.immobilisations_brutes / sim.par.duree_amortissement,
                        e.immobilisations_nettes)
            ints = (e.dette * sim.par.taux_interet
                    + e.dette_urgence * sim.par.taux_urgence)
            st.info(f"💡 **Charges de structure ce trimestre** — coûts fixes : "
                    f"{cf:,.0f} HTG · amortissement : {amort:,.0f} HTG · "
                    f"intérêts prévus : {ints:,.0f} HTG. Ajoutez vos budgets "
                    f"discrétionnaires pour calculer votre seuil de rentabilité.")
            if nom in partie.soumissions:
                st.success("✅ Décisions soumises pour ce trimestre — modifiables tant "
                           "que l'animateur n'a pas lancé le calcul.")
            d, budget_ok = formulaire_decisions(partie, e, f"{nom}{sim.t}")
            if st.button("📨 Soumettre mes décisions", type="primary",
                         disabled=not budget_ok):
                partie.soumettre(nom, d)
                sauvegarder_parties(etat["parties"])
                dialogue_confirmation(nom, sim.t + 1)

    with onglets[1]:
        if not e.rapports:
            st.info("Vos premiers résultats apparaîtront après le calcul du trimestre 1.")
        else:
            rap = e.rapports[-1]
            if rap["ajustements"]:
                st.warning(" · ".join(rap["ajustements"]))
            r1, r2, r3 = st.columns(3)
            r1.metric("Revenus du trimestre", f"{rap['etat_resultats']['revenus']:,.0f} HTG")
            r2.metric("Bénéfice net", f"{rap['etat_resultats']['benefice_net']:,.0f} HTG")
            r3.metric("Profit cumulé", f"{rap['indicateurs']['profit_cumule']:,.0f} HTG")
            afficher_detail_produits(rap)
            afficher_etats_financiers(rap)
            afficher_ratios(rap)
            st.markdown("**Ma trajectoire financière**")
            donnees = pd.DataFrame({
                "Trimestre": [f"T{i+1}" for i in range(len(e.rapports))],
                "Revenus": [round(r["etat_resultats"]["revenus"])
                            for r in e.rapports],
                "Bénéfice net": [round(r["etat_resultats"]["benefice_net"])
                                 for r in e.rapports],
            })
            infobulle = [alt.Tooltip("Trimestre:N"),
                         alt.Tooltip("Revenus:Q", format=","),
                         alt.Tooltip("Bénéfice net:Q", format=",")]
            base_g = alt.Chart(donnees).encode(
                x=alt.X("Trimestre:N", sort=None,
                        axis=alt.Axis(labelAngle=0, title=None)))
            barres = base_g.mark_bar(size=26, cornerRadiusTopLeft=4,
                                     cornerRadiusTopRight=4, color="#2E5FA3",
                                     opacity=0.85).encode(
                y=alt.Y("Revenus:Q",
                        axis=alt.Axis(title="Revenus (HTG)", format="~s")),
                tooltip=infobulle)
            ligne = base_g.mark_line(color="#C9A227", strokeWidth=3,
                                     point=alt.OverlayMarkDef(
                                         size=80, filled=True,
                                         color="#C9A227")).encode(
                y=alt.Y("Bénéfice net:Q",
                        axis=alt.Axis(title="Bénéfice net (HTG)", format="~s")),
                tooltip=infobulle)
            st.altair_chart(
                alt.layer(barres, ligne).resolve_scale(y="independent")
                .properties(height=320), use_container_width=True)

    with onglets[2]:
        if not partie.historique:
            st.info("Le bulletin de marché apparaîtra après le premier trimestre.")
        else:
            afficher_bulletin(partie.historique[-1]["bulletin"])
            graphique_parts(sim)
