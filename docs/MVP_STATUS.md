# Olin Shadow MVP — état canonique

## Investigator development status — 20 September 2026

Phase 6 bounded synthetic development ACCEPTED by Brice's conditional sign-off,
satisfied in the final scoped acceptance check at
`77808219422c9ecfacb97f8ab1196fa2faf780d0`. The implementation session executed
491 local tests; inspected exact-SHA CI35518373373 independently reported491
passing discovery tests including93 PostgreSQL16.15 tests, legacy/synthetic and
website checks. The focused report reviewer covered the final invalidation
correction. The acceptance check reused that evidence; it did not rerun suites.

Accepted development: deterministic Phase0–4 foundations, bounded synthetic
human investigation and paired read-only Phase6 reports. Phase5B is research-only:
model narrative usefulness/representative cases and guarded hosted analyst
integration remain unvalidated. Inference allowance is exhausted at6/6.
Phase7 attributable annotations/cohorts are under implementation, NOT accepted.

Deferred release checks: generic catalogue wording tied to260,000MXN; targeted
monthly-normalization convention review (not a confirmed defect); hosted shadow
integration if retained in V1; representative-case/model-semantic validation;
real evidence intake, accountable operating ownership and bank prerequisites.
Production SSO, hosting, data permissions, retention/deletion and bank usefulness
are not approved. The legacy roadmap below and blueprint's bank-owned outcomes
describe separate/future capabilities: they do not authorize Phase7 to authenticate
an analyst-reported bank statement, store full reports or invoke models.

Dernière validation : 20 août 2026.

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
- `olin/bank_ingestion.py` : contrat signé et neutre de fournisseur pour les
  métriques bancaires dérivées; aucun identifiant bancaire ni transaction brute.
- `olin/synthetic_portfolio.py` : validation reproductible du moteur sur données
  entièrement synthétiques.
- `test_live_readiness.py` : consentement, rectification, signature, rejeu et
  invariants du portefeuille synthétique.
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

Validation additionnelle au 19 août : 30 tests ciblés passent. Un portefeuille
de 1 000 dossiers synthétiques (seed 42) exerce les trois chemins de décision :
334 AUTO_APPROVE, 333 COMMITTEE et 333 DECLINE. Tous les contrôles logiciels
passent. Ce résultat ne mesure ni le défaut ni la précision prédictive.

## Contrôles du pilote bancaire

- Consentement append-only avec version, empreinte SHA-256, acteur et retrait.
- Retrait de consentement bloquant immédiatement toute nouvelle ingestion banque.
- Demande de rectification distincte; aucune mutation silencieuse de la preuve.
- Une rectification acceptée exige un nouveau dossier et un nouveau score.
- Callback banque signé HMAC, lié au consentement et idempotent par `event_id`.
- Rejet des credentials, CLABE, numéros de compte et transactions brutes.
- Authentification nominative et permissions par rôle; isolation des partenaires.
- Limite locale de requêtes, CSP, blocage iframe, no-sniff, no-store et
  Permissions-Policy.
- Aucun décaissement en mode shadow, même après une recommandation positive.
- Tokens opérateur conservés uniquement en mémoire de page, jamais dans le Web
  Storage; un rafraîchissement déconnecte l'utilisateur.
- Sonde `/readyz`, conteneur non-root, healthcheck et pipeline CI de validation.
- Workflow pré-scoring `intake_id` : consentement, token de liaison à usage
  unique, session expirante, callback signé, retrait et conversion atomique en
  un seul dossier scoré.

Commande de validation synthétique :

```bash
python3 -m olin.synthetic_portfolio --cases 1000 --seed 42
python3 -m unittest -v test_live_readiness
```

## Limites connues

- Les trois dossiers de démonstration sont synthétiques.
- La plateforme accepte plusieurs secteurs, mais seule la politique abarrotes
  est actuellement éligible à une route automatique. Tous les autres secteurs
  sont obligatoirement soumis à la revue du partenaire.
- Le contrat d'ingestion bancaire est prêt, mais l'adaptateur commercial, les
  identifiants sandbox et l'URL de callback doivent être fournis par la banque
  ou l'agrégateur. Syncfy Widget n'est pas encore activé.
- Aucune intégration Círculo, TPV ou distributeur n’est encore active dans cette
  démo.
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
