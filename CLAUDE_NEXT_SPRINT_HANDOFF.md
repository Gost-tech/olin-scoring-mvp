# Olin — handoff pour le prochain sprint Claude

## Goal of next session

Préparer Olin pour un **pilote sombra de 10 dossiers** sans déplacer d'argent.
Commencer par une revue indépendante et un plan de changements borné. Ne pas
transformer ce sprint en lancement de crédit live.

## State of play

- Le produit, les tests, le site et les documents sont dans
  `/Users/pc/Downloads/olin_scoring_mvp_1`.
- Le verdict actuel est `READY` pour démo/pilote sombra et `BLOCK` pour lending
  live autonome. Voir `ADVERSARIAL_REVIEW.md`.
- La réservation anti-double décaissement, le consentement minimum, les alertes
  durables et la configuration séparée du site sont déjà implémentés.
- `test_pilot_safety.py` passe 13/13 et `test_full_flow.py` passe. Des
  `ResourceWarning` SQLite persistent.
- Il n'existe pas de dépôt Git dans le dossier : aucune attribution ligne par
  ligne n'est fiable.
- Ne pas lire, afficher ou copier `.env`. Les identifiants déjà utilisés doivent
  être renouvelés avant toute production.

## Open decisions

1. Obtenir l'autorisation du fondateur avant d'initialiser Git et figer un
   baseline propre.
2. Définir avec le partenaire les champs exacts du pilote sombra : identifiant
   partenaire, décision partenaire, raison, temps analyste, divergences et
   données manquantes.
3. Obtenir le texte/version de consentement et les exigences d'artefact auprès
   du conseil mexicain avant d'étendre le schéma de consentement.
4. Obtenir les capacités STP réelles avant de concevoir le rapprochement et la
   gestion des états ambigus.
5. Décider qui sera originador, responsable risque, approbateur du
   décaissement et propriétaire du rapprochement avant tout crédit live.

## Skills to use

- `code-reviewer` pour la revue read-only initiale.
- `data-quality-auditor` pour le schéma des 10 dossiers et l'export.
- `security-threat-model` avant RBAC, double contrôle ou mouvement d'argent.
- `database-designer` pour les migrations et la traçabilité.
- `focused-fix` pour chaque changement accepté, un par un.

## Artifacts

- État complet et tests : `CODEX_HANDOFF_FOR_CLAUDE.md`
- Blocages et sévérité : `ADVERSARIAL_REVIEW.md`
- Opérations et stop conditions : `PILOT_RUNBOOK.md`
- Plan fondateur : `START_HERE_OLIN.md`
- Positionnement autorisé : `docs/OLIN_BRAND_AND_MESSAGE.md`
- Moteur : `olin/scorecard.py`
- État/audit/paiements : `olin/store.py`
- API analyste : `olin/server.py`
- Rapprochement entrant : `olin/collection.py`
- STP : `olin/stp.py`
- Tests : `test_pilot_safety.py`, `test_full_flow.py`

## Requested execution order

1. Revue read-only, exécution des tests et confirmation/contestation des
   blocages. Aucun changement à cette étape.
2. Corriger uniquement le cycle de vie des connexions SQLite et obtenir zéro
   `ResourceWarning`, sans changer le comportement métier.
3. Proposer le schéma minimal et les tests d'un dossier sombra exploitable :
   cohorte, mode, décision partenaire, raison, timestamps, couverture,
   divergences et temps analyste. Attendre validation avant implémentation.
4. Après validation, implémenter l'enregistrement et l'export des 10 dossiers,
   avec interdiction de décaissement en mode sombra.
5. Laisser RBAC/double contrôle, consentement complet, chiffrement et machine
   d'états STP dans un plan live séparé. Ne pas les improviser sans les décisions
   externes listées ci-dessus.
