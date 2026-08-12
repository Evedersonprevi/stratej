"""
STRATÈJ — Interface v5
======================
Fichiers requis dans le même dossier :
  stratej_moteur_v3.py, stratej_partie_v3.py, stratej_debriefing_v2.py,
  app_stratej_v5.py

Lancer avec :  streamlit run app_stratej_v5.py
"""

import altair as alt
import pandas as pd
import streamlit as st

from stratej_moteur_v3 import (Parametres, Produit, Decisions, DecisionsProduit,
                               DecisionsRH, cout_engage, maj_ressources_humaines,
                               cout_unitaire)
from stratej_partie_v3 import Partie, sauvegarder_parties, registre
from stratej_debriefing_v2 import debriefing

st.set_page_config(page_title="Stratèj", page_icon="📊", layout="wide")

st.markdown("""
<style>
[data-testid="stMetric"] {
    background: #F7F9FC; border: 1px solid #E3E8F0;
    border-left: 4px solid #1F3864; border-radius: 10px; padding: 12px 16px;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div { color: #1E2430 !important; }
[data-testid="stMetricLabel"] p { color: #5A6B87 !important; font-size: 0.85rem; }
button[data-baseweb="tab"] { font-weight: 600; }
.bandeau {
    background: linear-gradient(100deg, #1F3864 0%, #2E5FA3 100%);
    border-bottom: 3px solid #C9A227; border-radius: 12px;
    padding: 18px 26px; margin-bottom: 18px;
}
.marque { margin-bottom: 8px; line-height: 0; }
.bandeau h1 { color: #FFFFFF; font-size: 1.15rem; font-weight: 600; margin: 0;
              letter-spacing: .3px; opacity: .95; }
.bandeau p  { color: #C9D6EA; margin: 4px 0 0 0; font-size: .95rem; }
</style>
""", unsafe_allow_html=True)

LOGO_SVG = """
<svg viewBox="0 0 620 250" height="54" xmlns="http://www.w3.org/2000/svg">
  <text x="0" y="190" font-family="Helvetica, Arial, sans-serif" font-size="145"
        font-weight="700" fill="#FFFFFF" letter-spacing="-1">Stratèj</text>
  <path d="M 4 226 C 140 226 220 218 320 196 S 480 140 570 112"
        stroke="#C9A227" stroke-width="9" fill="none" stroke-linecap="round"/>
  <circle cx="570" cy="112" r="13" fill="#C9A227"/>
</svg>
"""

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
    "liquidite": "Liquidité", "gestion": "Gestion",
    "croissance": "Croissance", "part_marche": "Part de marché",
}


def entete(titre, sous_titre=""):
    st.markdown('<div class="bandeau"><div class="marque">' + LOGO_SVG + '</div>'
                '<h1>' + titre + '</h1>'
                + ('<p>' + sous_titre + '</p>' if sous_titre else '')
                + '</div>', unsafe_allow_html=True)


def etat_partage():
    return {"parties": registre()}


def fmt(v, pct=False, dec=2):
    if v is None:
        return "—"
    return f"{v*100:.1f} %" if pct else f"{v:.{dec}f}"


def htg(v):
    return f"{v:,.0f} HTG".replace(",", " ")


# ======================================================================
# AFFICHAGES PARTAGÉS
# ======================================================================
def afficher_bulletin(bulletin):
    st.subheader(f"Bulletin de marché — trimestre {bulletin['trimestre']}")
    c1, c2 = st.columns(2)
    c1.metric("Conjoncture de la demande", bulletin.get("conjoncture_label", "—"))
    c2.metric("Coût des intrants", bulletin.get("indice_cout_label", "—"))
    for nom_p, m in bulletin["produits"].items():
        st.markdown(f"**{nom_p}** — demande totale {m['demande_totale']:,.0f} u · "
                    f"prix moyen {m['prix_moyen']:,.0f} HTG")
        st.dataframe(pd.DataFrame([{
            "Équipe": e["nom"], "Prix affiché (HTG)": round(e["prix"]),
            "Part de marché (%)": round(e["part_marche"] * 100, 1),
            "Rupture de stock": "Oui" if e["rupture_stock"] else "",
        } for e in m["equipes"]]), hide_index=True, use_container_width=True)
    if bulletin.get("departements"):
        with st.expander("🗺️ Répartition géographique du marché"):
            for nom_d, d in bulletin["departements"].items():
                st.markdown(f"**{nom_d}** — demande {d['demande']:,.0f} u")
                st.dataframe(pd.DataFrame([{
                    "Équipe": e["nom"], "Points de vente": e["points_de_vente"],
                    "Ventes (u)": round(e["ventes"]),
                } for e in d["equipes"]]), hide_index=True, use_container_width=True)


def afficher_etats_financiers(rapport):
    er, bi = rapport["etat_resultats"], rapport["bilan"]
    ca, cb = st.columns(2)
    with ca:
        st.markdown("**État des résultats (HTG)**")
        st.dataframe(pd.DataFrame({
            "Poste": ["Revenus", "Coût des marchandises vendues", "Coûts fixes",
                      "Marketing", "Commissions", "Charges de personnel",
                      "Recherche et développement", "Partenariats", "Stockage",
                      "Amortissement", "Intérêts", "Bénéfice avant impôt",
                      "Impôt", "Bénéfice net"],
            "Montant": [round(er["revenus"]), -round(er["cmv"]),
                        -round(er["couts_fixes"]), -round(er["marketing"]),
                        -round(er["commissions"]), -round(er["charges_rh"]),
                        -round(er["rd"]), -round(er["partenariats"]),
                        -round(er["stockage"]), -round(er["amortissement"]),
                        -round(er["interets"]), round(er["benefice_avant_impot"]),
                        -round(er["impot"]), round(er["benefice_net"])],
        }), hide_index=True, use_container_width=True)
    with cb:
        st.markdown("**Bilan (HTG)**")
        st.dataframe(pd.DataFrame({
            "Poste": ["Encaisse", "Créances clients", "Stocks",
                      "Avances au personnel", "Actif à court terme",
                      "Immobilisations nettes", "ACTIF TOTAL",
                      "Dettes fournisseurs", "Découvert d'urgence",
                      "Passif à court terme", "Dette à long terme",
                      "FONDS DE ROULEMENT", "Capitaux propres"],
            "Montant": [round(bi["encaisse"]), round(bi["creances"]),
                        round(bi["stocks"]), round(bi["avances_personnel"]),
                        round(bi["actif_court_terme"]),
                        round(bi["immobilisations_nettes"]),
                        round(bi["actif_total"]), round(bi["dettes_fournisseurs"]),
                        round(bi["dette_urgence"]), round(bi["passif_court_terme"]),
                        round(bi["dette"]), round(bi["fonds_roulement"]),
                        round(bi["capitaux_propres"])],
        }), hide_index=True, use_container_width=True)


def afficher_flux_tresorerie(rapport):
    ft = rapport["flux_tresorerie"]
    st.markdown("**État des flux de trésorerie (HTG)**")
    st.dataframe(pd.DataFrame({
        "Poste": ["Encaissements clients", "Paiements aux fournisseurs",
                  "Autres décaissements d'exploitation", "Avances au personnel",
                  "FLUX D'EXPLOITATION", "FLUX D'INVESTISSEMENT",
                  "FLUX DE FINANCEMENT", "VARIATION DE L'ENCAISSE",
                  "Découvert d'urgence mobilisé", "Encaisse de clôture"],
        "Montant": [round(ft["encaissements_clients"]),
                    round(ft["paiements_fournisseurs"]),
                    round(ft["autres_decaissements"]),
                    round(ft["avances_personnel"]),
                    round(ft["flux_exploitation"]),
                    round(ft["flux_investissement"]),
                    round(ft["flux_financement"]),
                    round(ft["variation_encaisse"]),
                    round(ft["decouvert_urgence"]),
                    round(ft["encaisse_cloture"])],
    }), hide_index=True, use_container_width=True)


def afficher_ratios(rapport):
    ra = rapport.get("ratios")
    if not ra:
        return
    st.markdown("**Ratios financiers du trimestre**")
    lignes = [
        ("Rentabilité", "Marge nette", fmt(ra["marge_nette"], pct=True)),
        ("Rentabilité", "Rendement des capitaux propres (ROE)", fmt(ra["roe"], pct=True)),
        ("Rentabilité", "Rendement de l'actif (ROA)", fmt(ra["roa"], pct=True)),
        ("Liquidité", "Liquidité générale (actif CT / passif CT)", fmt(ra["liquidite_generale"])),
        ("Liquidité", "Liquidité réduite (hors stocks)", fmt(ra["liquidite_reduite"])),
        ("Liquidité", "Liquidité immédiate (encaisse / passif CT)", fmt(ra["liquidite_immediate"])),
        ("Fonds de roulement", "Fonds de roulement", htg(ra["fonds_roulement"])),
        ("Fonds de roulement", "En % des revenus du trimestre",
         fmt(ra["fonds_roulement_sur_revenus"], pct=True)),
        ("Fonds de roulement", "Délai de recouvrement",
         "—" if ra["delai_recouvrement_jours"] is None
         else f"{ra['delai_recouvrement_jours']:.0f} jours"),
        ("Fonds de roulement", "Délai de paiement fournisseurs",
         "—" if ra["delai_paiement_jours"] is None
         else f"{ra['delai_paiement_jours']:.0f} jours"),
        ("Gestion", "Rotation de l'actif", fmt(ra["rotation_actif"])),
        ("Gestion", "Rotation des stocks", fmt(ra["rotation_stocks"])),
        ("Solvabilité", "Dette / Actif", fmt(ra["dette_actif"], pct=True)),
        ("Solvabilité", "Couverture des intérêts", fmt(ra["couverture_interets"])),
        ("Croissance", "Croissance des revenus (vs T-1)",
         fmt(ra["croissance_revenus"], pct=True)),
    ]
    st.dataframe(pd.DataFrame(lignes, columns=["Catégorie", "Ratio", "Valeur"]),
                 hide_index=True, use_container_width=True)


def afficher_detail_produits(rapport):
    st.markdown("**Détail par produit**")
    st.dataframe(pd.DataFrame([{
        "Produit": nom, "Intrant": dp["intrant"], "Ventes (u)": round(dp["ventes"]),
        "Prix (HTG)": round(dp["prix"]), "Coût unitaire (HTG)": round(dp["cout_unitaire"], 1),
        "Revenus (HTG)": round(dp["revenus"]), "Marge brute (HTG)": round(dp["marge_brute"]),
        "Stock restant (u)": round(dp["stock_unites"]),
        "Qualité": round(dp["qualite"], 2),
        "Efficacité (%)": round(dp["efficacite"] * 100, 1),
    } for nom, dp in rapport["produits"].items()]),
        hide_index=True, use_container_width=True)


def afficher_rh(rapport):
    rh = rapport.get("rh")
    if not rh:
        return
    st.markdown("**Ressources humaines**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Effectif", rh["effectif"])
    c2.metric("Moral", f"{rh['moral']:.0f} / 100")
    c3.metric("Productivité", f"{rh['productivite']:.2f}")
    c4.metric("Compétence acquise", f"{rh['competence']*100:.1f} %")
    st.dataframe(pd.DataFrame([{
        "Poste": k.replace("_", " ").capitalize(), "Montant (HTG)": round(v)
    } for k, v in rh["detail_couts"].items()]),
        hide_index=True, use_container_width=True)
    mouvements = []
    if rh["embauches"]:
        mouvements.append(f"{rh['embauches']} embauche(s)")
    if rh["departs_voulus"]:
        mouvements.append(f"{rh['departs_voulus']} départ(s) décidé(s)")
    if rh["departs_naturels"]:
        mouvements.append(f"{rh['departs_naturels']} départ(s) volontaire(s)")
    if mouvements:
        st.caption("Mouvements du trimestre : " + " · ".join(mouvements))


def graphique_parts(sim):
    if not sim.equipes or not sim.equipes[0].parts_historiques:
        return
    df = pd.DataFrame({e.nom: [p * 100 for p in e.parts_historiques] for e in sim.equipes})
    df.index = [f"T{i+1}" for i in range(len(df))]
    st.caption("Parts de marché globales (%) — information publique")
    st.line_chart(df)


# ======================================================================
# FORMULAIRE DE DÉCISIONS
# ======================================================================
def formulaire_decisions(partie, e, cle):
    sim, par = partie.sim, partie.sim.par
    base = partie.soumissions.get(e.nom) or e.dernieres_decisions
    d = Decisions()
    noms_intrants = [i.nom for i in par.intrants]

    # ---------------- PRODUITS ----------------
    st.markdown("#### 📦 Production et produits")
    total_prod, heures_requises = 0.0, 0.0
    for p in par.produits:
        ep = e.etats_produits[p.nom]
        bp = base.produits.get(p.nom, DecisionsProduit(prix=p.prix_reference))
        with st.expander(f"{p.nom}", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                intrant = st.selectbox(
                    f"Qualité des intrants — {p.nom}", noms_intrants,
                    index=noms_intrants.index(bp.intrant) if bp.intrant in noms_intrants else 1,
                    key=f"in{cle}{p.nom}",
                    help="Un intrant économique réduit le coût unitaire mais dégrade "
                         "la qualité perçue ; un intrant premium fait l'inverse.")
                prod = st.number_input(f"Production (u) — {p.nom}", 0.0,
                                       value=float(bp.production), step=1_000.0,
                                       key=f"pr{cle}{p.nom}")
                prix = st.number_input(f"Prix de vente (HTG) — {p.nom}", 1.0,
                                       value=float(bp.prix), step=5.0,
                                       key=f"px{cle}{p.nom}")
            with c2:
                rdq = st.number_input(f"R&D qualité (HTG) — {p.nom}", 0.0,
                                      value=float(bp.rd_qualite), step=100_000.0,
                                      key=f"rq{cle}{p.nom}",
                                      help="Améliore l'attractivité du produit.")
                rdp = st.number_input(f"R&D procédé (HTG) — {p.nom}", 0.0,
                                      value=float(bp.rd_procede), step=100_000.0,
                                      key=f"rp{cle}{p.nom}",
                                      help="Réduit durablement le coût unitaire.")
            cu = cout_unitaire(par, p, ep, intrant, sim.t)
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Coût unitaire", f"{cu:,.1f} HTG")
            i2.metric("Stock disponible", f"{ep.stock_unites:,.0f} u")
            i3.metric("Indice qualité", f"{ep.qualite:.2f}")
            i4.metric("Efficacité acquise", f"{ep.efficacite*100:.1f} %")
            d.produits[p.nom] = DecisionsProduit(production=prod, prix=prix,
                                                 intrant=intrant, rd_qualite=rdq,
                                                 rd_procede=rdp)
            total_prod += prod
            heures_requises += prod * p.heures_par_unite

    pct = total_prod / e.capacite * 100 if e.capacite > 0 else 0
    couleur = "#C0392B" if total_prod > e.capacite else "#1F3864"
    st.markdown(
        f'<div style="margin:6px 0 4px 0;font-size:.9rem;color:#5A6B87;">'
        f'Capacité machine utilisée : {total_prod:,.0f} / {e.capacite:,.0f} u '
        f'({pct:.0f} %)</div>'
        f'<div style="background:#E3E8F0;border-radius:6px;height:14px;">'
        f'<div style="width:{min(pct,100)}%;background:{couleur};height:14px;'
        f'border-radius:6px;"></div></div>', unsafe_allow_html=True)
    if total_prod > e.capacite:
        st.warning("Production supérieure à la capacité installée : elle sera "
                   "plafonnée et répartie au prorata.")

    # ---------------- RESSOURCES HUMAINES ----------------
    st.markdown("#### 👥 Ressources humaines")
    brh = base.rh
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            emb = st.number_input("Embauches (négatif = départs)", -200, 500,
                                  int(brh.embauches), 1, key=f"emb{cle}",
                                  help=f"Recrutement : {par.cout_embauche:,.0f} HTG "
                                       f"par personne. Licenciement : "
                                       f"{par.cout_licenciement:,.0f} HTG.")
            salaire = st.number_input("Salaire trimestriel moyen (HTG)", 0.0,
                                      value=float(brh.salaire), step=1_000.0,
                                      key=f"sal{cle}",
                                      help=f"Salaire du marché ce trimestre : "
                                           f"{par.salaire_marche_t(sim.t):,.0f} HTG.")
        with c2:
            avantages = st.number_input("Avantages sociaux (HTG)", 0.0,
                                        value=float(brh.avantages_sociaux),
                                        step=100_000.0, key=f"avs{cle}",
                                        help="Santé, transport, cantine… : agit "
                                             "directement sur le moral.")
            formation = st.number_input("Formation du personnel (HTG)", 0.0,
                                        value=float(brh.formation), step=100_000.0,
                                        key=f"for{cle}",
                                        help="Augmente durablement la compétence, "
                                             "donc la productivité.")
        with c3:
            avances = st.number_input("Avances au personnel (HTG)", 0.0,
                                      value=float(brh.avances), step=100_000.0,
                                      key=f"avc{cle}",
                                      help="Sortie de trésorerie ce trimestre, "
                                           "remboursée au suivant. Soutient le moral.")
        d.rh = DecisionsRH(embauches=emb, salaire=salaire,
                           avantages_sociaux=avantages, formation=formation,
                           avances=avances)
        ratio = salaire / par.salaire_marche_t(sim.t) if par.salaire_marche_t(sim.t) else 1
        m1, m2, m3 = st.columns(3)
        m1.metric("Effectif après mouvements", max(e.effectif + emb, 0))
        m2.metric("Salaire vs marché", f"{(ratio-1)*100:+.0f} %")
        m3.metric("Moral actuel", f"{e.moral:.0f} / 100")
        heures_dispo = (max(e.effectif + emb, 0) * par.heures_par_employe
                        * (0.70 + 0.60 * e.moral / 100) * (1 + e.competence))
        if heures_requises > heures_dispo and heures_requises > 0:
            st.warning(f"Main-d'œuvre insuffisante : environ "
                       f"{heures_dispo/heures_requises*100:.0f} % du plan de "
                       f"production sera réalisé. Embauchez, formez ou "
                       f"améliorez le moral.")

    # ---------------- MARKETING ----------------
    st.markdown("#### 📣 Marketing et force de vente")
    with st.container(border=True):
        st.caption("Répartissez votre budget entre les canaux : chacun a son "
                   "efficacité propre et sature au-delà d'un certain montant.")
        cols = st.columns(len(par.canaux))
        for col, canal in zip(cols, par.canaux):
            with col:
                d.marketing[canal.nom] = st.number_input(
                    canal.nom, 0.0, value=float(base.marketing.get(canal.nom, 0.0)),
                    step=100_000.0, key=f"mk{cle}{canal.nom}",
                    help=f"Efficacité relative {canal.efficacite:.2f} · "
                         f"budget de référence {canal.budget_reference:,.0f} HTG")
        d.commission = st.slider(
            "Commission versée aux vendeurs (% du chiffre d'affaires)",
            0.0, 20.0, float(base.commission * 100), 0.5, key=f"com{cle}",
            help="Une commission attractive stimule les ventes, mais elle se "
                 "prélève sur chaque gourde encaissée.") / 100
        total_mkt = sum(d.marketing.values())
        if total_mkt > 0:
            st.caption(f"Budget national total : {htg(total_mkt)}")

    # ---------------- GÉOGRAPHIE ----------------
    st.markdown("#### 🗺️ Déploiement géographique")
    with st.container(border=True):
        st.caption("Sans point de vente ni marketing local dans un département, "
                   "vous n'y captez presque rien.")
        for dep in par.departements:
            c1, c2, c3, c4 = st.columns([2, 1, 1.4, 1.4])
            c1.markdown(f"**{dep.nom}**  \n<span style='color:#5A6B87;font-size:.85rem'>"
                        f"{dep.poids*100:.0f} % du marché national</span>",
                        unsafe_allow_html=True)
            c2.metric("Points", e.pdv.get(dep.nom, 0))
            d.ouvertures_pdv[dep.nom] = c3.number_input(
                f"Ouvertures — {dep.nom}", 0, 10,
                int(base.ouvertures_pdv.get(dep.nom, 0)), 1, key=f"pdv{cle}{dep.nom}",
                help=f"Ouverture : {dep.cout_pdv:,.0f} HTG · exploitation : "
                     f"{dep.cout_exploitation_pdv:,.0f} HTG/trimestre")
            d.marketing_local[dep.nom] = c4.number_input(
                f"Marketing local — {dep.nom}", 0.0,
                value=float(base.marketing_local.get(dep.nom, 0.0)), step=50_000.0,
                key=f"mkl{cle}{dep.nom}")

    # ---------------- PARTENARIATS ----------------
    if par.partenariats:
        st.markdown("#### 🤝 Partenariats")
        with st.container(border=True):
            for pa in par.partenariats:
                if st.checkbox(f"{pa.nom} — {htg(pa.cout)} · {pa.description}",
                               value=pa.nom in base.partenariats,
                               key=f"pa{cle}{pa.nom}"):
                    d.partenariats.append(pa.nom)

    # ---------------- FINANCEMENT ----------------
    st.markdown("#### 🏦 Investissement et financement")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        d.invest_capacite = c1.number_input(
            "Investissement en capacité (HTG)", 0.0,
            value=float(base.invest_capacite), step=500_000.0, key=f"ic{cle}",
            help=f"{par.cout_capacite:,.0f} HTG par unité de capacité, "
                 "disponible au trimestre suivant.")
        d.nouvel_emprunt = c2.number_input("Nouvel emprunt (HTG)", 0.0,
                                           value=float(base.nouvel_emprunt),
                                           step=500_000.0, key=f"ne{cle}")
        if e.dette > 0:
            d.remboursement = c3.number_input(
                "Remboursement de dette (HTG)", 0.0, max_value=float(e.dette),
                value=float(min(base.remboursement, e.dette)), step=500_000.0,
                key=f"rb{cle}", help=f"Dette en cours : {htg(e.dette)}")
        else:
            d.remboursement = 0.0
            c3.caption("💳 Aucune dette en cours : rien à rembourser.")

    # ---------------- BUDGET DE TRÉSORERIE ----------------
    from copy import deepcopy
    e_test = deepcopy(e)
    info_rh = maj_ressources_humaines(par, e_test, d.rh, sim.t)
    depenses = cout_engage(par, e, d, sim.t, info_rh)
    dispo = e.encaisse + d.nouvel_emprunt + e.creances
    st.markdown("#### 💰 Budget de trésorerie du trimestre")
    b1, b2, b3 = st.columns(3)
    b1.metric("Ressources disponibles", htg(dispo),
              help="Encaisse + créances à encaisser + nouvel emprunt.")
    b2.metric("Dépenses engagées", htg(depenses),
              help="Production, marketing, R&D, personnel, réseau, partenariats, "
                   "investissement et remboursement.")
    b3.metric("Marge de manœuvre", htg(dispo - depenses))
    budget_ok = depenses <= dispo + 1e-6
    if not budget_ok:
        st.error("🚫 Vos dépenses dépassent vos ressources. Sans emprunt ni levée "
                 "de fonds, l'entreprise ne peut compter que sur ses ressources "
                 "internes : réduisez vos budgets ou financez-vous.")
    return d, budget_ok


# ======================================================================
# APPLICATION
# ======================================================================
@st.dialog("Confirmation")
def dialogue_confirmation(nom, trimestre):
    st.success(f"Les décisions du trimestre {trimestre} ont bien été soumises "
               f"pour **{nom}**. ✅")
    st.write("Vous pouvez encore les modifier tant que l'animateur n'a pas lancé "
             "le calcul du trimestre.")
    if st.button("Compris"):
        st.rerun()


etat = etat_partage()

st.sidebar.markdown(
    '<div style="font-size:1.5rem;font-weight:700;color:#1F3864;'
    'letter-spacing:-.5px;">Stratèj</div>'
    '<div style="height:3px;width:54px;background:#C9A227;'
    'border-radius:2px;margin:3px 0 8px 0;"></div>', unsafe_allow_html=True)
st.sidebar.caption("Simulation d'entreprise")
role = st.sidebar.radio("Je suis :", ["Équipe", "Animateur"], horizontal=True)
if st.sidebar.button("🔄 Actualiser la page"):
    st.rerun()

# ======================================================================
# PORTAIL ANIMATEUR
# ======================================================================
if role == "Animateur":
    parties = etat["parties"]
    if not parties or st.session_state.get("mode_creation"):
        entete("Créer une nouvelle partie")
        if parties and st.button("← Retour aux parties existantes"):
            st.session_state.mode_creation = False
            st.rerun()
        nom_partie_new = st.text_input(
            "Nom de la partie", f"Groupe {len(parties) + 1}",
            help="Chaque partie est indépendante : un même animateur peut en "
                 "mener plusieurs en parallèle.")
        c1, c2, c3 = st.columns(3)
        noms_txt = c1.text_area("Équipes (une par ligne)",
                                "Équipe 1\nÉquipe 2\nÉquipe 3\nÉquipe 4", height=120)
        nb = c2.number_input("Nombre de trimestres", 4, 16, 8)
        code = c3.text_input("Code d'accès animateur", "PROF")

        st.subheader("Produits du scénario")
        df_produits = st.data_editor(pd.DataFrame([
            {"Nom": "Jus naturel", "Demande de base (u/trim.)": 90_000,
             "Prix de référence (HTG)": 250, "Coût variable initial (HTG)": 90},
            {"Nom": "Confiture", "Demande de base (u/trim.)": 40_000,
             "Prix de référence (HTG)": 400, "Coût variable initial (HTG)": 170},
        ]), num_rows="dynamic", use_container_width=True)

        st.subheader("Départements et marché géographique")
        df_dep = st.data_editor(pd.DataFrame([
            {"Département": "Ouest", "Part du marché (%)": 42,
             "Coût d'un point de vente (HTG)": 1_400_000, "Exploitation (HTG/trim.)": 150_000},
            {"Département": "Nord", "Part du marché (%)": 16,
             "Coût d'un point de vente (HTG)": 1_000_000, "Exploitation (HTG/trim.)": 110_000},
            {"Département": "Artibonite", "Part du marché (%)": 15,
             "Coût d'un point de vente (HTG)": 1_000_000, "Exploitation (HTG/trim.)": 110_000},
            {"Département": "Sud", "Part du marché (%)": 13,
             "Coût d'un point de vente (HTG)": 900_000, "Exploitation (HTG/trim.)": 95_000},
            {"Département": "Centre", "Part du marché (%)": 14,
             "Coût d'un point de vente (HTG)": 900_000, "Exploitation (HTG/trim.)": 95_000},
        ]), num_rows="dynamic", use_container_width=True)

        st.subheader("Canaux de communication")
        df_can = st.data_editor(pd.DataFrame([
            {"Canal": "Réseaux sociaux", "Efficacité": 1.35, "Budget de référence (HTG)": 500_000},
            {"Canal": "Radio", "Efficacité": 0.85, "Budget de référence (HTG)": 400_000},
            {"Canal": "Télévision", "Efficacité": 1.05, "Budget de référence (HTG)": 900_000},
            {"Canal": "Affichage et rue", "Efficacité": 0.75, "Budget de référence (HTG)": 350_000},
            {"Canal": "Marketing terrain", "Efficacité": 1.10, "Budget de référence (HTG)": 450_000},
        ]), num_rows="dynamic", use_container_width=True)

        st.subheader("Environnement économique")
        defaut_dem = ["Stable", "Croissance modérée", "Récession", "Stable",
                      "Expansion", "Forte récession", "Ralentissement", "Croissance modérée"]
        defaut_cout = ["Coûts stables", "Coûts stables", "Forte hausse des intrants",
                       "Hausse modérée des intrants", "Coûts stables",
                       "Hausse modérée des intrants", "Coûts stables", "Coûts stables"]
        nb_i = int(nb)
        df_env = st.data_editor(pd.DataFrame({
            "Trimestre": [f"T{i+1}" for i in range(nb_i)],
            "Conjoncture de la demande": [defaut_dem[i % len(defaut_dem)] for i in range(nb_i)],
            "Coût des intrants": [defaut_cout[i % len(defaut_cout)] for i in range(nb_i)],
        }), column_config={
            "Trimestre": st.column_config.TextColumn(disabled=True),
            "Conjoncture de la demande": st.column_config.SelectboxColumn(
                options=list(NIVEAUX_DEMANDE.keys()), required=True),
            "Coût des intrants": st.column_config.SelectboxColumn(
                options=list(NIVEAUX_COUT.keys()), required=True),
        }, hide_index=True, use_container_width=True)

        st.subheader("Pondération du classement")
        cols_p = st.columns(len(NOMS_CRITERES))
        defauts_p = {"rentabilite": 25, "solvabilite": 15, "liquidite": 10,
                     "gestion": 15, "croissance": 15, "part_marche": 20}
        poids = {}
        for col, (cle_c, libelle) in zip(cols_p, NOMS_CRITERES.items()):
            poids[cle_c] = col.number_input(libelle, 0, 100, defauts_p[cle_c], 5)

        with st.expander("⚙️ Paramètres avancés"):
            c1, c2, c3 = st.columns(3)
            with c1:
                capa = c1.number_input("Capacité initiale (u/trim.)", 1_000.0, value=32_000.0, step=1_000.0)
                cout_capa = c1.number_input("Coût d'une unité de capacité (HTG)", 1.0, value=400.0, step=50.0)
                encaisse = c1.number_input("Encaisse initiale (HTG)", 0.0, value=8_000_000.0, step=500_000.0)
                fixes = c1.number_input("Coûts fixes trimestriels (HTG)", 0.0, value=900_000.0, step=100_000.0)
            with c2:
                effectif0 = c2.number_input("Effectif initial", 1, 2000, 35)
                salaire_m = c2.number_input("Salaire trimestriel du marché (HTG)", 0.0, value=20_000.0, step=1_000.0)
                heures_emp = c2.number_input("Heures par employé et par trimestre", 1.0, value=480.0, step=20.0)
                moral0 = c2.number_input("Moral initial", 0.0, 100.0, 60.0, 5.0)
            with c3:
                inflation = c3.number_input("Inflation trimestrielle", 0.0, 0.2, 0.03, 0.005, format="%.3f")
                croissance = c3.number_input("Croissance du marché / trimestre", -0.1, 0.2, 0.01, 0.005, format="%.3f")
                credit_v = c3.number_input("Ventes à crédit (part)", 0.0, 0.9, 0.30, 0.05)
                credit_a = c3.number_input("Achats à crédit (part)", 0.0, 0.9, 0.25, 0.05)
            c4, c5 = st.columns(2)
            taux = c4.number_input("Taux d'intérêt trimestriel", 0.0, 0.3, 0.03, 0.005, format="%.3f")
            impot = c5.number_input("Taux d'imposition", 0.0, 0.6, 0.30, 0.05, format="%.2f")

        if st.button("Créer la partie", type="primary"):
            from stratej_moteur_v3 import Departement, Canal
            noms = [n.strip() for n in noms_txt.splitlines() if n.strip()]
            produits = [Produit(nom=str(l["Nom"]).strip(),
                                demande_base=float(l["Demande de base (u/trim.)"]),
                                prix_reference=float(l["Prix de référence (HTG)"]),
                                cout_variable_base=float(l["Coût variable initial (HTG)"]))
                        for _, l in df_produits.iterrows() if str(l["Nom"]).strip()]
            total_poids = sum(float(l["Part du marché (%)"]) for _, l in df_dep.iterrows()
                              if str(l["Département"]).strip()) or 100
            departements = [Departement(nom=str(l["Département"]).strip(),
                                        poids=float(l["Part du marché (%)"]) / total_poids,
                                        cout_pdv=float(l["Coût d'un point de vente (HTG)"]),
                                        cout_exploitation_pdv=float(l["Exploitation (HTG/trim.)"]))
                            for _, l in df_dep.iterrows() if str(l["Département"]).strip()]
            canaux = [Canal(nom=str(l["Canal"]).strip(), efficacite=float(l["Efficacité"]),
                            budget_reference=float(l["Budget de référence (HTG)"]))
                      for _, l in df_can.iterrows() if str(l["Canal"]).strip()]
            labels_dem = list(df_env["Conjoncture de la demande"])
            labels_cout = list(df_env["Coût des intrants"])
            par = Parametres(
                nb_trimestres=int(nb), produits=produits or [Produit()],
                departements=departements, canaux=canaux,
                conjoncture=[NIVEAUX_DEMANDE.get(l, 1.0) for l in labels_dem],
                indice_cout=[NIVEAUX_COUT.get(l, 1.0) for l in labels_cout],
                conjoncture_labels=labels_dem, indice_cout_labels=labels_cout,
                capacite_initiale=capa, cout_capacite=cout_capa,
                encaisse_initiale=encaisse, couts_fixes=fixes,
                effectif_initial=int(effectif0), salaire_marche=salaire_m,
                heures_par_employe=heures_emp, moral_initial=moral0,
                inflation_trimestrielle=inflation, croissance_trimestrielle=croissance,
                part_ventes_a_credit=credit_v, part_achats_a_credit=credit_a,
                taux_interet=taux, taux_impot=impot)
            if not nom_partie_new.strip():
                st.error("Donne un nom à la partie.")
            elif nom_partie_new.strip() in parties:
                st.error("Une partie porte déjà ce nom.")
            else:
                parties[nom_partie_new.strip()] = Partie(noms, par, code,
                                                         poids_classement=poids)
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
        entete("Espace animateur", f"Partie « {nom_partie} » — accès protégé")
        code_saisi = st.text_input("Code d'accès animateur", type="password")
        if st.button("Entrer"):
            if code_saisi.strip().upper() == partie.code_animateur:
                autorisees.add(nom_partie)
                st.rerun()
            else:
                st.error("Code incorrect.")
        st.stop()

    sim = partie.sim
    entete("Espace animateur",
           f"Partie « {nom_partie} » — pilotage, résultats et classement")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trimestre", f"{min(sim.t + 1, sim.par.nb_trimestres)} / {sim.par.nb_trimestres}")
    c2.metric("Soumissions", f"{len(partie.soumissions)} / {len(sim.equipes)}")
    c3.metric("Produits", len(sim.par.produits))
    c4.metric("Statut", "Terminée" if partie.terminee else "En cours")

    onglets = st.tabs(["🎮 Ronde en cours", "📈 Résultats", "🧭 Débriefings",
                       "🏆 Classement", "🔑 Codes d'accès", "⚙️ Administration"])

    with onglets[0]:
        if partie.terminee:
            st.success("La partie est terminée.")
        else:
            st.write(f"Trimestre {sim.t + 1} — demande : "
                     f"**{sim.par.label_conjoncture_t(sim.t)}** · intrants : "
                     f"**{sim.par.label_indice_cout_t(sim.t)}**")
            st.dataframe(pd.DataFrame([{
                "Équipe": e.nom,
                "Soumission": "✅ Reçue" if e.nom in partie.soumissions else "⏳ En attente",
                "Effectif": e.effectif, "Moral": round(e.moral),
                "Points de vente": e.nb_pdv,
            } for e in sim.equipes]), hide_index=True, use_container_width=True)
            manquantes = [e.nom for e in sim.equipes if e.nom not in partie.soumissions]
            if manquantes:
                st.warning("Sans soumission (reconduction automatique) : " + ", ".join(manquantes))
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
            st.subheader("Résultats consolidés")
            st.dataframe(pd.DataFrame([{
                "Équipe": nom, "Revenus (HTG)": round(r["etat_resultats"]["revenus"]),
                "Bénéfice net (HTG)": round(r["etat_resultats"]["benefice_net"]),
                "Encaisse (HTG)": round(r["bilan"]["encaisse"]),
                "Fonds de roulement (HTG)": round(r["bilan"]["fonds_roulement"]),
                "Liquidité gén.": fmt(r["ratios"]["liquidite_generale"]),
                "Effectif": r["rh"]["effectif"], "Moral": round(r["rh"]["moral"]),
                "Notes": " · ".join(r["ajustements"]),
            } for nom, r in res["rapports"].items()]),
                hide_index=True, use_container_width=True)
            graphique_parts(sim)
            st.subheader("Détail par équipe")
            for onglet_e, e in zip(st.tabs([e.nom for e in sim.equipes]), sim.equipes):
                with onglet_e:
                    rap = e.rapports[choix_t - 1]
                    afficher_detail_produits(rap)
                    afficher_rh(rap)
                    afficher_etats_financiers(rap)
                    afficher_flux_tresorerie(rap)
                    afficher_ratios(rap)

    with onglets[2]:
        if not partie.historique:
            st.info("Les débriefings apparaîtront après le premier trimestre.")
        else:
            c1, c2 = st.columns([1, 2])
            t_choisi = c1.selectbox("Trimestre ", list(range(len(partie.historique), 0, -1)),
                                    key="t_debrief")
            vue = c2.radio("Affichage", ["Toutes les équipes", "Une équipe"],
                           horizontal=True, key="vue_debrief")
            idx = t_choisi - 1
            if vue == "Une équipe":
                eq = st.selectbox("Équipe", [e.nom for e in sim.equipes], key="eq_debrief")
                with st.container(border=True):
                    st.markdown(debriefing(partie, eq, idx, pour_professeur=True))
            else:
                for e_ in sim.equipes:
                    with st.expander(f"🧭 {e_.nom}"):
                        st.markdown(debriefing(partie, e_.nom, idx, pour_professeur=True))
            st.download_button(
                "⬇️ Télécharger tous les débriefings",
                "\n\n---\n\n".join(debriefing(partie, e_.nom, idx, pour_professeur=True)
                                   for e_ in sim.equipes),
                file_name=f"debriefings_T{t_choisi}.md", mime="text/markdown")

    with onglets[3]:
        if partie.historique:
            total_p = sum(partie.poids_classement.values()) or 1
            st.caption("Pondération : " + " · ".join(
                f"{NOMS_CRITERES[k]} {v/total_p*100:.0f} %"
                for k, v in partie.poids_classement.items()))
            st.dataframe(pd.DataFrame([{
                "Rang": i + 1, "Équipe": l["nom"], "Score": round(l["score"], 1),
                "Rentabilité (profit cumulé)": round(l["rentabilite"]),
                "Solvabilité": f"{l['solvabilite']*100:.1f} %",
                "Liquidité": f"{l['liquidite']:.2f}",
                "Gestion": f"{l['gestion']:.2f}",
                "Croissance": f"{l['croissance']*100:.1f} %",
                "Part de marché": f"{l['part_marche']*100:.1f} %",
            } for i, l in enumerate(sim.classement(partie.poids_classement))]),
                hide_index=True, use_container_width=True)
            if partie.classements:
                lignes_scores, lignes_rangs = {}, {}
                for inst in partie.classements:
                    for rang, l in enumerate(inst["classement"], 1):
                        lignes_scores.setdefault(l["nom"], []).append(round(l["score"], 1))
                        lignes_rangs.setdefault(l["nom"], []).append(rang)
                index_t = [f"T{c['trimestre']}" for c in partie.classements]
                st.subheader("Historique du classement")
                st.line_chart(pd.DataFrame(lignes_scores, index=index_t))
                with st.expander("Rang trimestre par trimestre"):
                    st.dataframe(pd.DataFrame(lignes_rangs, index=index_t).T,
                                 use_container_width=True)
        else:
            st.info("Le classement apparaîtra après le premier trimestre.")

    with onglets[4]:
        st.write("À distribuer aux équipes :")
        st.dataframe(pd.DataFrame([{"Équipe": n, "Code d'accès": c}
                                   for n, c in partie.codes.items()]),
                     hide_index=True, use_container_width=True)

    with onglets[5]:
        st.subheader("Pondération du classement")
        cols_p = st.columns(len(NOMS_CRITERES))
        nouveaux = {}
        for col, (cle_c, libelle) in zip(cols_p, NOMS_CRITERES.items()):
            nouveaux[cle_c] = col.number_input(
                libelle, 0, 100, int(partie.poids_classement.get(cle_c, 20)), 5,
                key=f"poids_{cle_c}")
        if st.button("Enregistrer la pondération"):
            partie.poids_classement = nouveaux
            sauvegarder_parties(parties)
            st.success("Pondération mise à jour.")
        st.divider()
        st.error("Zone sensible")
        if st.button(f"🗑️ Supprimer la partie « {nom_partie} »"):
            del parties[nom_partie]
            sauvegarder_parties(parties)
            st.rerun()

# ======================================================================
# PORTAIL ÉQUIPE
# ======================================================================
else:
    parties = etat["parties"]
    entete("Portail d'équipe",
           "Décisions trimestrielles et résultats de votre entreprise")
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
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Encaisse", htg(e.encaisse))
    c2.metric("Créances", htg(e.creances))
    c3.metric("Capacité", f"{e.capacite:,.0f} u")
    c4.metric("Effectif", e.effectif)
    c5.metric("Moral", f"{e.moral:.0f} / 100")
    c6.metric("Dette totale", htg(e.dette + e.dette_urgence))

    onglets = st.tabs(["📝 Mes décisions", "📊 Mes résultats", "🌍 Le marché"])

    with onglets[0]:
        if partie.terminee:
            st.success("La partie est terminée.")
        else:
            st.write(f"Conjoncture annoncée — demande : "
                     f"**{sim.par.label_conjoncture_t(sim.t)}** · intrants : "
                     f"**{sim.par.label_indice_cout_t(sim.t)}**")
            cf = sim.par.couts_fixes_t(sim.t)
            pdv_ex = sum(dep.cout_exploitation_pdv * e.pdv.get(dep.nom, 0)
                         for dep in sim.par.departements)
            amort = min(e.immobilisations_brutes / sim.par.duree_amortissement,
                        e.immobilisations_nettes)
            ints = (e.dette * sim.par.taux_interet
                    + e.dette_urgence * sim.par.taux_urgence)
            st.info(f"💡 **Charges de structure ce trimestre** — coûts fixes : "
                    f"{htg(cf)} · exploitation du réseau : {htg(pdv_ex)} · "
                    f"amortissement : {htg(amort)} · intérêts prévus : {htg(ints)}. "
                    f"Ajoutez vos budgets discrétionnaires pour calculer votre "
                    f"seuil de rentabilité.")
            if nom in partie.soumissions:
                st.success("✅ Décisions soumises — modifiables tant que "
                           "l'animateur n'a pas lancé le calcul.")
            d, budget_ok = formulaire_decisions(partie, e, f"{nom}{sim.t}")
            if st.button("📨 Soumettre mes décisions", type="primary",
                         disabled=not budget_ok):
                partie.soumettre(nom, d)
                sauvegarder_parties(parties)
                dialogue_confirmation(nom, sim.t + 1)

    with onglets[1]:
        if not e.rapports:
            st.info("Vos premiers résultats apparaîtront après le trimestre 1.")
        else:
            rap = e.rapports[-1]
            with st.container(border=True):
                st.markdown("### 🧭 Votre débriefing")
                st.markdown(debriefing(partie, nom))
            if rap["ajustements"]:
                st.warning(" · ".join(rap["ajustements"]))
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Revenus", htg(rap["etat_resultats"]["revenus"]))
            r2.metric("Bénéfice net", htg(rap["etat_resultats"]["benefice_net"]))
            r3.metric("Flux d'exploitation", htg(rap["flux_tresorerie"]["flux_exploitation"]))
            r4.metric("Profit cumulé", htg(rap["indicateurs"]["profit_cumule"]))
            afficher_detail_produits(rap)
            afficher_rh(rap)
            afficher_etats_financiers(rap)
            afficher_flux_tresorerie(rap)
            afficher_ratios(rap)
            st.markdown("**Ma trajectoire financière**")
            donnees = pd.DataFrame({
                "Trimestre": [f"T{i+1}" for i in range(len(e.rapports))],
                "Revenus": [round(r["etat_resultats"]["revenus"]) for r in e.rapports],
                "Bénéfice net": [round(r["etat_resultats"]["benefice_net"]) for r in e.rapports],
            })
            info = [alt.Tooltip("Trimestre:N"), alt.Tooltip("Revenus:Q", format=","),
                    alt.Tooltip("Bénéfice net:Q", format=",")]
            base_g = alt.Chart(donnees).encode(
                x=alt.X("Trimestre:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)))
            barres = base_g.mark_bar(size=26, cornerRadiusTopLeft=4,
                                     cornerRadiusTopRight=4, color="#2E5FA3",
                                     opacity=0.85).encode(
                y=alt.Y("Revenus:Q", axis=alt.Axis(title="Revenus (HTG)", format="~s")),
                tooltip=info)
            ligne = base_g.mark_line(color="#C9A227", strokeWidth=3,
                                     point=alt.OverlayMarkDef(size=80, filled=True,
                                                              color="#C9A227")).encode(
                y=alt.Y("Bénéfice net:Q",
                        axis=alt.Axis(title="Bénéfice net (HTG)", format="~s")),
                tooltip=info)
            st.altair_chart(alt.layer(barres, ligne).resolve_scale(y="independent")
                            .properties(height=320), use_container_width=True)

    with onglets[2]:
        if not partie.historique:
            st.info("Le bulletin de marché apparaîtra après le premier trimestre.")
        else:
            afficher_bulletin(partie.historique[-1]["bulletin"])
            graphique_parts(sim)
