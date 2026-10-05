#!/usr/bin/env python3
"""
Synchronisation de la bibliothèque Steam pour le consultant jeux vidéo.

Récupère les jeux possédés et la liste de souhaits via l'API Steam,
puis écrit le fichier bibliotheque.md à la racine du dépôt.

Variables d'environnement :
  STEAM_CLE_API  clé API Steam (obligatoire, stockée dans les secrets GitHub)
  STEAM_ID       identifiant SteamID64 (facultatif, valeur par défaut ci-dessous)

N'utilise que la bibliothèque standard de Python : rien à installer.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

STEAM_ID_PAR_DEFAUT = "76561198087673743"
PAYS_BOUTIQUE = "fr"            # prix en euros, boutique française
LANGUE_BOUTIQUE = "french"      # textes de la boutique en français
FICHIER_SORTIE = "bibliotheque.md"
PAUSE_ENTRE_REQUETES = 1.6      # secondes : la boutique limite à environ 200 requêtes / 5 min
FUSEAU = ZoneInfo("Europe/Paris")

URL_JEUX_POSSEDES = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
URL_LISTE_SOUHAITS = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
URL_DETAILS_BOUTIQUE = "https://store.steampowered.com/api/appdetails"


# ---------------------------------------------------------------------------
# Accès aux API
# ---------------------------------------------------------------------------

def requete_json(url, parametres, tentatives=3):
    """Envoie une requête GET et renvoie la réponse JSON décodée."""
    adresse = url + "?" + urllib.parse.urlencode(parametres)
    requete = urllib.request.Request(adresse, headers={"User-Agent": "consultant-jeux/1.0"})
    for essai in range(1, tentatives + 1):
        try:
            with urllib.request.urlopen(requete, timeout=30) as reponse:
                return json.load(reponse)
        except urllib.error.HTTPError as erreur:
            # 429 = trop de requêtes : on patiente puis on réessaie
            if erreur.code == 429 and essai < tentatives:
                time.sleep(60)
                continue
            # On n'affiche jamais l'adresse complète : elle contient la clé API
            raise RuntimeError(f"erreur HTTP {erreur.code} sur {url}") from None
        except urllib.error.URLError as erreur:
            if essai < tentatives:
                time.sleep(10)
                continue
            raise RuntimeError(f"connexion impossible à {url} ({erreur.reason})") from None
    raise RuntimeError(f"échec après {tentatives} tentatives sur {url}")


def recuperer_jeux_possedes(cle_api, steam_id):
    donnees = requete_json(URL_JEUX_POSSEDES, {
        "key": cle_api,
        "steamid": steam_id,
        "include_appinfo": 1,
        "include_played_free_games": 1,
        "format": "json",
    })
    jeux = (donnees or {}).get("response", {}).get("games")
    if jeux is None:
        raise RuntimeError(
            "aucun jeu renvoyé. Vérifie que les « détails des jeux » "
            "de ton profil Steam sont publics."
        )
    return jeux


def recuperer_liste_souhaits(cle_api, steam_id):
    donnees = requete_json(URL_LISTE_SOUHAITS, {"key": cle_api, "steamid": steam_id})
    return (donnees or {}).get("response", {}).get("items", [])


def recuperer_details_boutique(appid):
    """Nom, prix, réduction et langues d'un jeu sur la boutique Steam."""
    donnees = requete_json(URL_DETAILS_BOUTIQUE, {
        "appids": appid,
        "cc": PAYS_BOUTIQUE,
        "l": LANGUE_BOUTIQUE,
    })
    bloc = (donnees or {}).get(str(appid), {})
    if not bloc.get("success"):
        return None
    return bloc.get("data")


# ---------------------------------------------------------------------------
# Mise en forme
# ---------------------------------------------------------------------------

def nettoyer(texte):
    """Empêche un nom de jeu de casser un tableau Markdown."""
    return str(texte).replace("|", "\\|").strip()


def en_heures(minutes):
    if not minutes:
        return "—"
    heures = minutes / 60
    if heures < 1:
        return f"{minutes} min"
    return f"{heures:.1f} h".replace(".", ",")


def en_date(horodatage):
    if not horodatage:
        return "—"
    return datetime.fromtimestamp(horodatage, FUSEAU).strftime("%d/%m/%Y")


def langue_francaise(texte_langues):
    """
    Lit le champ « supported_languages » de la boutique.
    Une langue suivie d'un astérisque a aussi les voix.
    """
    if not texte_langues:
        return "?"
    for morceau in texte_langues.split(","):
        morceau = morceau.split("<br>")[0]   # retire la note de bas de liste
        if "Français" in morceau or "French" in morceau:
            return "textes + voix" if "*" in morceau else "textes"
    return "non"


def decrire_prix(details):
    """Renvoie (prix actuel, réduction, prix normal)."""
    if details.get("is_free"):
        return "Gratuit", "", ""
    prix = details.get("price_overview")
    if not prix:
        if details.get("release_date", {}).get("coming_soon"):
            return "Pas encore sorti", "", ""
        return "Indisponible", "", ""
    reduction = prix.get("discount_percent", 0)
    if reduction:
        return prix.get("final_formatted", "?"), f"-{reduction} %", prix.get("initial_formatted", "")
    return prix.get("final_formatted", "?"), "", ""


def generer_markdown(jeux, souhaits, maintenant):
    lignes = []
    ajouter = lignes.append

    ajouter("# Bibliothèque Steam")
    ajouter("")
    ajouter(f"> Générée automatiquement le {maintenant:%d/%m/%Y à %H:%M} (heure de Paris). "
            "Ne pas modifier à la main : le fichier est réécrit à chaque synchronisation.")
    ajouter("> Les prix de la liste de souhaits datent de cette génération : "
            "les revérifier avant de les citer.")
    ajouter("")

    # --- Résumé ---
    jamais_lances = [j for j in jeux if not j.get("playtime_forever")]
    moins_une_heure = [j for j in jeux if 0 < j.get("playtime_forever", 0) < 60]
    total_minutes = sum(j.get("playtime_forever", 0) for j in jeux)

    ajouter("## Résumé")
    ajouter("")
    ajouter(f"- Jeux possédés : {len(jeux)}")
    ajouter(f"- Jamais lancés : {len(jamais_lances)}")
    ajouter(f"- Lancés moins d'une heure : {len(moins_une_heure)}")
    ajouter(f"- Temps de jeu total : {en_heures(total_minutes)}")
    ajouter(f"- Jeux dans la liste de souhaits : {len(souhaits)}")
    ajouter("")

    # --- Liste de souhaits, promotions en tête ---
    ajouter("## Liste de souhaits")
    ajouter("")
    if souhaits:
        def cle_tri_souhait(souhait):
            details = souhait["details"] or {}
            reduction = (details.get("price_overview") or {}).get("discount_percent", 0)
            return (-reduction, (details.get("name") or "").lower())

        ajouter("| Jeu | Prix actuel | Réduction | Prix normal | Français | Ajouté le |")
        ajouter("|---|---|---|---|---|---|")
        for souhait in sorted(souhaits, key=cle_tri_souhait):
            details = souhait["details"]
            lien = f"https://store.steampowered.com/app/{souhait['appid']}"
            if details is None:
                ajouter(f"| [Jeu {souhait['appid']}]({lien}) | ? | | | ? | {en_date(souhait['ajoute_le'])} |")
                continue
            prix, reduction, prix_normal = decrire_prix(details)
            ajouter(
                f"| [{nettoyer(details.get('name', souhait['appid']))}]({lien}) "
                f"| {prix} | {reduction} | {prix_normal} "
                f"| {langue_francaise(details.get('supported_languages'))} "
                f"| {en_date(souhait['ajoute_le'])} |"
            )
    else:
        ajouter("Liste de souhaits vide.")
    ajouter("")

    # --- Joués récemment ---
    recents = sorted(
        (j for j in jeux if j.get("playtime_2weeks")),
        key=lambda j: -j["playtime_2weeks"],
    )
    ajouter("## Joués ces deux dernières semaines")
    ajouter("")
    if recents:
        ajouter("| Jeu | Deux dernières semaines | Total |")
        ajouter("|---|---|---|")
        for jeu in recents:
            ajouter(f"| {nettoyer(jeu.get('name', jeu['appid']))} "
                    f"| {en_heures(jeu['playtime_2weeks'])} | {en_heures(jeu.get('playtime_forever'))} |")
    else:
        ajouter("Aucun jeu lancé ces deux dernières semaines.")
    ajouter("")

    # --- Jeux lancés, du plus joué au moins joué ---
    lances = sorted(
        (j for j in jeux if j.get("playtime_forever")),
        key=lambda j: -j["playtime_forever"],
    )
    ajouter("## Jeux lancés (du plus joué au moins joué)")
    ajouter("")
    if lances:
        ajouter("| Jeu | Temps total | Dont Steam Deck | Dernière session |")
        ajouter("|---|---|---|---|")
        for jeu in lances:
            ajouter(f"| {nettoyer(jeu.get('name', jeu['appid']))} "
                    f"| {en_heures(jeu.get('playtime_forever'))} "
                    f"| {en_heures(jeu.get('playtime_deck_forever'))} "
                    f"| {en_date(jeu.get('rtime_last_played'))} |")
    ajouter("")

    # --- Jamais lancés ---
    ajouter("## Jamais lancés")
    ajouter("")
    for jeu in sorted(jamais_lances, key=lambda j: (j.get("name") or "").lower()):
        ajouter(f"- {nettoyer(jeu.get('name', jeu['appid']))}")
    if not jamais_lances:
        ajouter("Aucun.")
    ajouter("")

    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def principal():
    cle_api = os.environ.get("STEAM_CLE_API")
    if not cle_api:
        sys.exit("Erreur : la variable STEAM_CLE_API est absente (secret GitHub non configuré ?).")
    steam_id = os.environ.get("STEAM_ID", STEAM_ID_PAR_DEFAUT)

    try:
        print("Récupération des jeux possédés…")
        jeux = recuperer_jeux_possedes(cle_api, steam_id)
        print(f"  {len(jeux)} jeux trouvés.")

        print("Récupération de la liste de souhaits…")
        elements_souhaits = recuperer_liste_souhaits(cle_api, steam_id)
        print(f"  {len(elements_souhaits)} jeux, récupération des prix…")
    except RuntimeError as erreur:
        sys.exit(f"Erreur : {erreur}")

    souhaits = []
    for element in elements_souhaits:
        appid = element["appid"]
        try:
            details = recuperer_details_boutique(appid)
        except RuntimeError as erreur:
            print(f"  Jeu {appid} ignoré : {erreur}")
            details = None
        souhaits.append({
            "appid": appid,
            "ajoute_le": element.get("date_added", 0),
            "details": details,
        })
        time.sleep(PAUSE_ENTRE_REQUETES)

    contenu = generer_markdown(jeux, souhaits, datetime.now(FUSEAU))
    with open(FICHIER_SORTIE, "w", encoding="utf-8") as fichier:
        fichier.write(contenu)
    print(f"{FICHIER_SORTIE} écrit.")


if __name__ == "__main__":
    principal()
