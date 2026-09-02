# Olin — runbook du pilote bancaire

## Périmètre autorisé

Le premier lancement est un pilote shadow B2B. Olin produit une recommandation
et un expediente; la banque garde la décision officielle et le risque. La route
de décaissement reste désactivée. Cette architecture suit l'avis juridique
communiqué par le fondateur; elle ne remplace pas une validation finale des
contrats, avis de confidentialité et textes de consentement.

## Avant d'accepter un vrai dossier

1. Déployer avec `OLIN_MODE=production` et `OLIN_LIVE_LENDING_ENABLED=0`.
2. Configurer `OLIN_USERS` avec des secrets uniques (partner, analyst, admin).
3. Configurer `OLIN_BANK_WEBHOOK_SECRET` dans un gestionnaire de secrets.
4. Mettre TLS, WAF/rate limiting et journaux devant le service.
5. Faire valider par la banque le texte/version de consentement et les durées de
   rétention; utiliser un environnement et une base séparés de la démo.
6. Échanger avec la banque uniquement des métriques dérivées. Ne jamais envoyer
   credentials, CLABE, numéro de compte ou transactions brutes.
7. Exécuter les tests et conserver le rapport synthétique avec le numéro de
   version déployé.

La plateforme interroge `GET /readyz`. En production, la réponse reste `503`
tant que la base, les trois rôles, le secret callback et le blocage du
décaissement ne sont pas tous conformes.

## Contrat callback banque

`POST /api/v1/webhooks/bank-evidence`, avec le corps JSON exact signé dans
`X-Olin-Signature: sha256=<HMAC-SHA256>`. Champs requis : `event_id`,
`application_id`, `provider`, `connection_id`, `consent_id`, `observed_at` et
`metrics`. L'événement est accepté une seule fois et uniquement si le
consentement correspondant est actif. Les métriques dérivées sont ensuite
lisibles via `GET /api/v1/cases/{id}/bank-evidence` pour créer le dossier
scoré; le callback ne modifie jamais rétroactivement un score existant.

Test sandbox reproductible :

```bash
export OLIN_BANK_WEBHOOK_SECRET='<secret sandbox de 32+ caractères>'
python3 -m scripts.simulate_bank_callback \
  --base-url https://<hôte-pilote> \
  --application-id <application-id> \
  --consent-id <consent-id>
```

## Consentement et rectification

- `GET|POST /api/v1/cases/{id}/consents`
- `POST /api/v1/cases/{id}/consents/{consent_id}/withdraw`
- `GET|POST /api/v1/cases/{id}/corrections`
- `POST /api/v1/cases/{id}/corrections/{request_id}/resolve`

Une rectification acceptée n'altère pas le dossier historique. Créer un nouveau
dossier, conserver la référence au dossier précédent et refaire la décision.

## Liaison bancaire hébergée avant scoring

1. `POST /api/v1/intakes` crée un `intake_id` appartenant au partenaire.
2. `POST /api/v1/intakes/{id}/consents` capture le texte et ne conserve que son
   empreinte, sa version, son canal et son acteur.
3. `POST /api/v1/intakes/{id}/link-sessions` retourne un token client à usage
   unique, valable 5 à 30 minutes.
4. `POST /api/v1/link-sessions/exchange` consomme ce token et fournit au
   connecteur le contrat callback.
5. Le connecteur envoie les métriques signées avec `intake_id`,
   `link_session_id` et `consent_id`.
6. `POST /api/v1/intakes/{id}/score` crée exactement un expediente immuable en
   forçant la preuve bancaire et le consentement issus de l'intake.

Olin ne demande et ne reçoit jamais l'identifiant ou le mot de passe bancaire.
Le connecteur commercial doit échanger le bootstrap Olin contre sa propre
session Widget côté serveur.

## Go / no-go

Go shadow seulement si : tests verts, secrets chargés, TLS actif, utilisateurs
nommés, consentement validé, callback sandbox signé, retrait testé et incident
owner nommé. No-go si une donnée bancaire brute apparaît dans les logs, si le
consentement ne peut pas être retiré, si la banque n'a pas validé le callback,
ou si une route permet un mouvement d'argent.

Le déploiement Fly utilise `/readyz`, et le workflow
`.github/workflows/pilot-readiness.yml` bloque une régression du contrat, des
tests de sécurité ou du portefeuille synthétique avant fusion.
