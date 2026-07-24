# Olin — Start here

## La décision à prendre maintenant

Le projet n'est pas impossible. Il est simplement plus tôt que le deck ne le laissait croire.

Olin est aujourd'hui un **prototype fonctionnel de décision de crédit**, pas encore un prêteur ni un modèle d'IA validé. Ton objectif des 30 prochains jours n'est donc pas de lever 300 000 USD ou de faire 30 prêts. Ton objectif est d'obtenir **un pilote sombra de 10 dossiers consentis avec un partenaire sérieux**.

> **Phrase à retenir :** Olin organise des preuves vérifiables d'activité, applique une scorecard explicable et aide un prêteur à tester une décision de crédit sans perdre le contrôle.

## Ce que tu dois faire cette semaine

### 1. Préparer la réunion Monex — mercredi 22 juillet, 15:00

Apporte seulement trois choses :

- le nouveau site ;
- le deck partenaire de 10 slides ;
- la proposition de pilote de 10 dossiers.

Demande une réponse à cinq questions :

1. Les personnes physiques avec activité professionnelle peuvent-elles ouvrir le compte adapté au pilote, et sous quelles conditions ?
2. Monex peut-il fournir la TPV/adquirencia et rendre visibles les dates et montants de règlement ?
3. Quelles données de compte, de TPV et de règlement peuvent être partagées avec consentement, et par quel mécanisme : API, Host-to-Host ou export contrôlé ?
4. Une domiciliación ou instruction de paiement peut-elle être synchronisée avec les jours où les règlements TPV arrivent sur le compte ?
5. Un compte de garantie ou mécanisme d'escrow est-il possible pour réduire le risque, et qui chez Monex doit porter la prochaine session de travail ?

**Pourquoi ce sont réellement des questions :** le site officiel de Monex confirme une Cuenta Digital, des paiements SPEI et un accès Host-to-Host. En revanche, son crédit digital PyME publié commence à MXN 200 000 et demande notamment MXN 5 millions de chiffre d'affaires annuel ainsi qu'un historique bancaire formel. Je n'ai pas trouvé d'offre POS/adquirencia publique correspondant au projet. Le segment Olin de MXN 20 000–80 000 n'entre donc pas automatiquement dans l'offre Monex actuelle : la réunion doit tester une exception, un nouveau pilote ou un rôle d'infrastructure, pas présenter une compatibilité déjà acquise.

Ne demande pas « un partenariat » en général. Demande :

> **¿Podemos nombrar a un responsable de cada lado y diseñar en dos semanas un piloto sombra de 10 expedientes, sin mover dinero?**

### 2. Trouver les trois propriétaires manquants

- Un prêteur/originador qui garde la décision finale et, plus tard, peut porter les prêts.
- Un responsable risque/crédit mexicain qui signe la politique du pilote.
- Un avocat/compliance qui transforme le chemin S.A. de C.V. évoqué par conseil en checklist réellement exécutée.

Monex peut remplir une partie de ces rôles, mais ne le suppose pas avant la réunion.

### 3. Recruter 10 dossiers, pas 30 prêts

Cherche dix abarrotes qui acceptent que leur dossier soit analysé en parallèle. Aucun argent n'est déplacé. Pour chaque dossier, tu dois pouvoir enregistrer :

- consentement ;
- identité du commerce ;
- source et date de chaque preuve ;
- Círculo, DSCR, score interne, tier et raisons ;
- décision du partenaire ;
- éléments manquants et temps analyste.

Le résultat des dix dossiers doit répondre à une seule question : **Olin produit-il un dossier plus clair et comparable sans perturber l'opération du partenaire ?**

### 4. Arrêter les anciennes promesses

Ne plus présenter publiquement :

- « Olin prête aujourd'hui » ;
- « IA / XGBoost / LightGBM entraîné » ;
- « 89 % de précision » ;
- « intégration FEMSA, Bimbo, Belvo ou Monex live » ;
- « cash en 38 minutes / 2 heures » ;
- « 95 % sans crédit » sans source datée ;
- taux de défaut, rendement ou retour investisseur non observé ;
- nom ou logo d'un partenaire, conseiller ou client sans permission écrite.

Dire plutôt :

- « prototype fonctionnel » ;
- « scorecard explicable » ;
- « données synthétiques dans la démo » ;
- « intégration à valider avec un partenaire » ;
- « prêt pour un pilote sombra contrôlé ».

## Plan 30 / 60 / 90 jours

### Jours 1–30 — Devenir crédible

**Résultat attendu :** un pilote sombra signé ou défini avec un propriétaire et dix cas.

- Présenter le nouveau site et le deck partenaire.
- Tenir la réunion Monex et documenter réponses, responsables et date suivante.
- Approcher deux originadores/prêteurs et un distributeur régional.
- Finaliser avec conseil la structure, la confidentialité, le consentement Círculo, KYC/AML, disclosures et recouvrement.
- Écrire la politique de crédit, les exceptions, les limites et les conditions d'arrêt.
- Chiffrer un budget réel sur 6–9 mois en séparant capital d'entreprise et capital de prêts.
- Ne pas lancer de prêt live.

### Jours 31–60 — Prouver l'opération

**Résultat attendu :** dix dossiers complets et un rapport de faisabilité.

- Exécuter les dix dossiers en sombra.
- Mesurer couverture, données absentes, temps analyste et concordance avec le partenaire.
- Ajouter utilisateurs nommés, rôles, double contrôle, chiffrement, rétention et rapprochement STP autoritatif.
- Tester sauvegarde et restauration.
- Faire une revue formelle de préparation live avec prêteur, risque et conseil.
- Si une condition échoue, rester en sombra.

### Jours 61–90 — Apprendre avant de grossir

**Résultat attendu :** décision `go / no-go` documentée.

- Si toutes les gates sont validées, commencer avec seulement 3–5 prêts contrôlés de faible montant via le partenaire convenu.
- Rapprocher chaque mouvement quotidiennement.
- Suivre premier paiement, jours de retard, plaintes, actions de recouvrement et temps opérationnel.
- Attendre la maturité de cette micro-cohorte avant de passer à 10.
- Aller vers 30 seulement si les premières opérations sont comprises.
- Ne pas entraîner ni annoncer un modèle ML sur 30 observations.

## Quand lever de l'argent

Commence les relations avec des investisseurs maintenant, mais ne lance pas une campagne avec l'ancien deck.

Le meilleur moment pour une vraie levée pre-seed est après :

1. une voie juridique écrite ;
2. un partenaire ou une LOI sérieuse ;
3. dix dossiers sombra complets ;
4. une politique de crédit et un propriétaire risque ;
5. un budget trois scénarios ;
6. un plan clair disant qui origine, finance, sert, recouvre et porte la perte.

Si tu manques de cash avant cela, cherche d'abord un **pilote payé/sponsorisé** ou un petit bridge chaud construit à partir d'un budget réel, pas d'un chiffre rond.

Sépare toujours :

- **capital de la société** : salaire minimum du fondateur, juridique, sécurité, intégrations, analyste ;
- **capital de prêts** : principal déployé, pertes attendues et liquidité, porté dans la structure convenue avec le prêteur/funder.

## Ton script d'ouverture — 30 secondes

### Espagnol

> Hoy Olin es un prototipo funcional basado en reglas explicables. No reemplaza al originador ni al comité de crédito. Organiza Círculo, capacidad de pago y evidencia operativa en una recomendación trazable. Buscamos probarlo primero con 10 expedientes consentidos, en paralelo y sin mover dinero.

### Anglais

> Olin is a functional, rules-based credit-decision prototype. It does not replace the lender or credit committee. It organizes bureau, affordability, and merchant operating evidence into a traceable recommendation. Our next step is a ten-case shadow pilot, with consent and no money movement.

## Ordre de présentation — 7 minutes

1. **30 secondes :** le problème d'un commerce réel avec un dossier incomplet.
2. **45 secondes :** ce qu'Olin organise et ce qu'il ne remplace pas.
3. **2 minutes :** le dossier illustratif : Círculo, DSCR, score, tier, raisons.
4. **1 minute :** décision humaine et refus non contournable.
5. **1 minute :** cycle consentement → décision → paiement → outcome.
6. **45 secondes :** ce qui est construit / synthétique / dépendant du partenaire.
7. **1 minute :** demande précise du pilote de dix dossiers.

## Qui pitcher, dans quel ordre

1. Monex et un autre acteur compte/POS/paiement pour la faisabilité.
2. Deux prêteurs/SOFOMs capables d'originer et de garder la décision.
3. Un distributeur FMCG régional pour les preuves d'achat consenties.
4. Un opérateur risque/collections mexicain.
5. Quelques anges fintech chauds pour feedback et introductions.
6. Fonds pre-seed après le pilote sombra et une LOI.
7. Capital de dette seulement après plusieurs cohortes matures.

## Le contrôle final avant chaque réunion

- Chaque nombre a-t-il une source ou le label `hypothèse` ?
- Chaque capture et chaque dossier sont-ils marqués `illustratif` ou `synthétique` ?
- Est-ce clair qu'Olin ne prête pas aujourd'hui ?
- Est-ce clair que le partenaire garde la décision ?
- Sais-tu exactement ce que tu demandes à la fin ?
- As-tu retiré les logos et noms non autorisés ?

Si ces six réponses sont oui, tu peux présenter Olin sans jouer un rôle. Tu n'as pas besoin de connaître tout le crédit. Tu dois montrer que tu connais les limites, que tu apprends vite et que tu proposes le prochain pas le plus sûr.
