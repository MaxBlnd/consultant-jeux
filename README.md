# Synchronisation de bibliothèque Steam

Génère chaque jour `bibliotheque.md` : jeux possédés, temps de jeu et liste de souhaits avec prix.

- `scripts/synchro_steam.py` interroge l'API Steam et réécrit `bibliotheque.md`.
- `.github/workflows/synchro-steam.yml` le lance chaque matin via GitHub Actions.
- Lancement manuel : onglet **Actions** → **Synchronisation Steam** → **Run workflow**.
- La clé API Steam est stockée dans le secret `STEAM_CLE_API` (Settings → Secrets and variables → Actions). Elle ne doit jamais apparaître dans un fichier du dépôt.
