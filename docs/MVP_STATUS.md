# Olin Shadow MVP — état canonique

Dernière validation : 27 juillet 2026.

## Produit actuel

Olin est un outil B2B d’aide à la décision. Il transforme un dossier, ses
preuves et le consentement associé en une recommandation explicable. La
banque, SOFOM ou fintech partenaire conserve la décision officielle et le
risque. La première cohorte est limitée à dix petits commerces autorisés en
mode shadow, répartis entre plusieurs routes de preuve.

Modèle unique :

`case → evidence → recommendation → partner outcome`

Un dossier shadow ne peut jamais être décaissé.

## Architecture à connaître

- `olin/scorecard.py` : moteur de scoring conservé sans modification.
- `olin/api/cases.py` : création, validation, scoring, persistance et file.
- `olin/api/auth.py` : utilisateurs nommés, rôles et permissions.
- `olin/api/synthetic.py` : trois cas de démonstration cohérents.
- `olin/server.py` : transport HTTP et interface analyste; extraction encore en
  cours.
- `olin/shadow_intake.html` : création d’un dossier shadow.
- `olin/store.py` : SQLite, consentement, propriétaire, audit et outcomes.
- `test_product_mvp.py` : contrat du MVP et isolation entre partenaires.
- `docs/DEMO_5_MINUTES.md` : script de démonstration.
- `fly.synthetic.toml` : déploiement synthétique isolé.

## Rôles

- `partner` : crée, lit et complète uniquement ses propres dossiers.
- `analyst` : consulte la cohorte, ajoute notes/décisions et exporte.
- `admin` : administration; seul rôle pouvant atteindre la route de
  décaissement, elle-même bloquée pour tout dossier shadow.

Configuration production : `OLIN_USERS` au format JSON.

## Validation

```bash
python3 -m unittest -v test_shadow_mvp test_pilot_safety test_product_mvp olin.test_v2 test_belvo_pipeline
python3 test_full_flow.py
cd website && pnpm test
```

Résultat au 27 juillet : 27/27 tests API et sécurité, flux historique complet,
0 erreur Astro, 309 contrôles statiques et parcours navigateur validé avec un
faux partenaire puis un faux analyste.

## Limites connues

- Les trois dossiers de démonstration sont synthétiques.
- La plateforme accepte plusieurs secteurs, mais seule la politique abarrotes
  est actuellement éligible à une route automatique. Tous les autres secteurs
  sont obligatoirement soumis à la revue du partenaire.
- Aucune intégration Círculo, Syncfy, TPV ou distributeur n’est encore active
  dans cette démo.
- `server.py` contient encore du code historique de prêt direct non exposé.
  Continuer l’extraction avant toute exploitation live.
- Ce produit n’est pas encore autorisé pour un décaissement réel.

## Règle de benchmark HayCash

HayCash montre qu’un produit peut couvrir plusieurs secteurs tout en restant
très précis sur sa preuve principale : le flux TPV et un remboursement lié aux
ventes. Olin ne doit pas copier sa promesse de financement direct. Son avantage
à tester est un expediente explicable capable de combiner plusieurs routes de
preuve pour les institutions et les commerces moins bien servis. Ne jamais
présenter HayCash, Monex, Syncfy ou Círculo comme partenaire sans accord
vérifiable.
