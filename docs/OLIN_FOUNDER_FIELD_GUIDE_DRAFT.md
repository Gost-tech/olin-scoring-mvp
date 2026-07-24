# OLIN — Guide de terrain du fondateur

**Version de travail — 14 juillet 2026**  
**Langue principale : français · scripts prêts à dire : espagnol et anglais**

> Ce guide décrit le produit tel qu'il existe aujourd'hui dans le dépôt Olin. Il ne constitue ni un avis juridique, ni un avis réglementaire, ni une politique de crédit approuvée. Toute activité de crédit réelle au Mexique doit être encadrée par des professionnels qualifiés et par le partenaire qui porte juridiquement et financièrement les prêts.

---

## Comment utiliser ce guide

Tu n'as pas besoin de devenir banquier en une semaine. Tu dois savoir faire quatre choses :

1. expliquer clairement le problème que résout Olin ;
2. distinguer ce qui fonctionne aujourd'hui de ce qui reste à construire ;
3. comprendre assez bien le crédit pour poser les bonnes questions et ne pas faire de promesses dangereuses ;
4. demander un prochain pas précis à un partenaire ou à un investisseur.

Lis d'abord les sections 1, 4, 5 et 8. Elles suffisent pour une première réunion. Les autres sections servent de manuel de référence.

### Les cinq vérités à retenir

1. **Olin est aujourd'hui un prototype de décision et d'opération du crédit.** Ce n'est pas encore une plateforme de prêts en production.
2. **Le moteur actuel est une scorecard explicable basée sur des règles.** Ce n'est pas un modèle d'intelligence artificielle entraîné sur des résultats réels.
3. **Une recommandation `AUTO_APPROVE` ne signifie pas qu'un prêt part automatiquement.** Pour le pilote, chaque accord doit encore être approuvé et justifié par un humain.
4. **Les données bancaires et FMCG de la démo sont synthétiques.** Elles servent à montrer le flux ; elles ne prouvent pas que les intégrations ou les partenariats sont actifs.
5. **Les 30 premiers prêts doivent surtout valider l'opération et la qualité des données.** Trente résultats ne suffisent pas à annoncer un modèle ML fiable.

---

# 1. Ce qu'est Olin — et ce qu'il n'est pas

## 1.1 La phrase simple

**En français**

> Olin transforme des preuves vérifiables de l'activité d'un petit commerce en une recommandation de crédit explicable, afin qu'un prêteur puisse tester une politique de crédit de façon contrôlée.

**En espagnol**

> Olin convierte evidencia verificable de la operación de un pequeño comercio en una recomendación de crédito explicable, para que un originador pueda probar una política de crédito de forma controlada.

**In English**

> Olin turns verified operating evidence from a small merchant into an explainable credit recommendation, so a lender can test a credit policy in a controlled way.

## 1.2 Le problème

Un abarrotes peut être un vrai commerce, vendre chaque jour, se réapprovisionner chaque semaine et exister depuis plusieurs années, tout en laissant peu de traces dans les systèmes financiers traditionnels. Cela ne veut pas dire que le commerce est automatiquement solvable. Cela veut dire qu'une partie de son histoire économique n'est pas visible dans un dossier classique.

Olin essaie de rendre cette histoire lisible à partir de plusieurs familles de preuves : achats FMCG, flux bancaires, ancienneté, activité POS, présence Google Maps et informations IMSS lorsqu'elles sont réellement disponibles. Le moteur sépare ensuite deux questions :

- **Le commerce semble-t-il stable et réel ?** C'est le score interne.
- **Peut-il rembourser ce montant précis ?** C'est l'analyse de capacité, notamment le DSCR.

Ces réponses sont croisées avec Círculo de Crédito et des contrôles de fraude et de portefeuille.

## 1.3 Ce qu'Olin est aujourd'hui

Olin est :

- un moteur de score explicable basé sur six signaux potentiels ;
- une matrice de décision à trois dimensions : Círculo, DSCR et score interne ;
- un outil analyste qui affiche les raisons, le tier, les signaux et la capacité de remboursement ;
- un journal SQLite de la demande, de la décision, du décaissement, des paiements et du résultat final ;
- un simulateur d'onboarding de style WhatsApp ;
- un environnement de démonstration avec données bancaires et FMCG déterministes ;
- une base pour conduire un pilote en mode **shadow**, avec un partenaire qui conserve sa décision officielle ;
- un ensemble de règles et de contrôles déjà couverts par des tests locaux.

## 1.4 Ce qu'Olin n'est pas aujourd'hui

Olin n'est pas encore :

- une banque, une SOFOM ou un prêteur juridiquement établi du seul fait que le code existe ;
- un partenariat signé avec Monex, FEMSA, Bimbo, Syncfy, Círculo ou un autre acteur ;
- une intégration FMCG de production ;
- un accès bancaire de production démontré de bout en bout ;
- un modèle ML, XGBoost, LightGBM ou réseau de neurones entraîné sur des remboursements Olin ;
- un système capable d'annoncer un taux de défaut, une précision ou un rendement observé ;
- un produit prêt à prêter sans supervision ;
- une preuve que le cadre juridique, la documentation contractuelle, le CAT, la confidentialité, la KYC/AML et le recouvrement sont tous approuvés.

## 1.5 Niveau de maturité réel

| Niveau | Statut actuel | Ce que cela veut dire |
|---|---|---|
| Démonstration produit | **Oui** | On peut montrer l'onboarding, la décision, l'interface analyste, un décaissement simulé et le suivi des paiements. |
| Pilote shadow mené avec un partenaire | **Prêt à préparer** | Olin peut scorer des dossiers consentis sans décider ni déplacer d'argent, puis comparer ses recommandations avec celles du partenaire. |
| Pilote de prêts réels contrôlé | **Pas encore autorisé par le produit seul** | Il faut fermer les bloqueurs techniques, opérationnels, juridiques et de gouvernance listés plus bas. |
| Crédit live sans supervision | **Non** | Le dépôt lui-même conclut qu'Olin doit rester bloqué pour du lending autonome. |

## 1.6 Ce qui est vérifié dans le dépôt

### Fonctionnel dans l'environnement actuel

- les bandes Círculo, DSCR et score interne ;
- les 36 combinaisons de la matrice et les tiers 1 à 14 ;
- les contrôles de fraude et de concentration de portefeuille ;
- la recommandation, la justification analyste et l'interdiction d'annuler un refus moteur pendant le pilote ;
- la séparation démo/production et le rejet des mocks en production ;
- la validation CLABE et un connecteur STP avec séparation sandbox/production ;
- un mécanisme de réservation avant décaissement pour réduire le risque de double envoi ;
- le ledger de paiements, les paiements partiels, les doublons et les résultats finaux ;
- l'enregistrement minimal du consentement Círculo et un blocage d'approbation en production si aucun consentement n'est enregistré ;
- une tâche quotidienne pour les retards, les défauts et l'état du portefeuille ;
- des alertes qui partent par e-mail si configurées, sinon dans un fichier de log ;
- au dernier contrôle du 14 juillet 2026, les 13 tests de sécurité pilote et le flux complet passaient (avec des avertissements de fermeture de connexions SQLite à traiter).

### Partiel ou à confirmer en conditions réelles

- le connecteur bancaire existe, mais l'accès de production et la qualité des données ne sont pas démontrés ;
- Google Places peut fournir des éléments lorsque l'API est configurée, mais la qualité et la couverture doivent être mesurées ;
- la consultation Círculo est représentée dans le modèle, mais le flux de consentement et de preuve n'est pas une expérience complète ;
- STP est intégré au code, mais l'état final doit encore être rapproché avec une source STP autoritative ;
- les règles de graduation existent, mais elles sont des hypothèses de politique, pas des conditions commerciales validées.

### Bloqueurs avant du crédit réel

- utilisateurs analystes nommés, rôles, sessions et journal d'acteur immuable ;
- double contrôle avant tout mouvement d'argent ;
- chiffrement des données sensibles, gestion des clés, rétention et procédure de suppression ;
- sauvegarde chiffrée et test de restauration ;
- artefact de consentement complet : texte exact, identité, canal, version, timestamp, preuve et finalité ;
- rapprochement STP autoritatif et gestion durable des états `pending`, `confirmed`, `failed` et `unknown` ;
- sources bancaires et FMCG vérifiées en production ;
- politique de crédit, politique d'exceptions, limites de pertes et règles d'arrêt signées ;
- documentation client, calcul du coût total, confidentialité, KYC/AML et recouvrement revus au Mexique ;
- propriétaires nommés pour underwriting, décaissement, rapprochement, recouvrement, incidents et données personnelles.

**Point important :** des tests verts prouvent que le code fait ce que les tests demandent. Ils ne prouvent ni que les données sont vraies, ni que les prêts seront rentables, ni que l'opération est conforme.

---

# 2. Le cycle complet du crédit

Le crédit ne se limite pas à calculer un score. Il commence avant la demande et continue jusqu'au remboursement, au recouvrement éventuel et à l'analyse de la cohorte.

## Vue d'ensemble

```text
Ciblage → Consentement → Demande/KYC → Collecte de preuves → Contrôles
       → Capacité + score → Comité → Offre → Décaissement
       → Suivi des paiements → Recouvrement → Résultat final → Calibration
```

## Étape 1 — Ciblage et éligibilité

**Question :** à qui le produit est-il destiné ?

Pour le premier pilote, la règle du dépôt est simple : **abarrotes uniquement**, avec un maximum de 30 prêts décaissés avant revue des résultats. Il faut encore transformer cette intention en critères écrits : zone géographique, ancienneté minimale, activité exclue, montant, usage du prêt, prêt existant, capacité documentaire et consentement.

**Risque si cette étape est floue :** la cohorte devient hétérogène et les résultats sont impossibles à interpréter.

## Étape 2 — Consentement et confidentialité

**Question :** le commerçant comprend-il quelles données seront consultées, pourquoi et avec qui elles seront partagées ?

Le code peut enregistrer un timestamp, un canal (`whatsapp`, `sms`, `in_person`) et le texte de consentement. En production, l'approbation est bloquée si aucun consentement Círculo n'est enregistré.

Ce qui manque encore pour une preuve solide : version du texte, identité du consentant, preuve du message ou de la signature, finalité, durée, retrait éventuel, notice de confidentialité et règles d'accès. Le texte final doit être validé localement.

## Étape 3 — Demande et KYC

**Question :** savons-nous qui demande le crédit, quel commerce il exploite et où ira l'argent ?

Le simulateur collecte notamment le nom, le type de commerce, le montant, la colonia, la CLABE, le téléphone, le RFC, le CURP éventuel, l'adresse et la vérification INE. Une validation de format n'est pas une validation d'identité complète.

Avant du live, il faut une procédure documentée : pièces acceptées, concordance du nom et de la CLABE, contrôle de fraude documentaire, screening requis, responsable de l'exception et conservation des preuves.

## Étape 4 — Collecte et provenance des preuves

**Question :** chaque donnée importante a-t-elle une source, une date et un statut de vérification ?

Les objets bancaires et FMCG portent déjà les champs `source`, `verified`, `evidence_reference` et `observed_at`. C'est essentiel. Une valeur sans provenance n'est pas une preuve.

Pour le pilote, chaque signal utilisé doit répondre à quatre questions :

1. D'où vient-il ?
2. Quand a-t-il été observé ?
3. Qui ou quoi l'a vérifié ?
4. Peut-on retrouver l'artefact d'origine ?

Les mocks doivent rester visibles comme mocks et ne jamais entrer dans une décision de production.

## Étape 5 — Pré-contrôles : fraude et portefeuille

**Question :** faut-il arrêter le dossier avant même de calculer un score ?

Olin vérifie des éléments d'identité, d'adresse et de banque, puis applique des limites de portefeuille : prêt déjà actif sur la même CLABE, concentration par colonia, exposition locale, concentration par type d'activité et santé générale du portefeuille.

Un blocage fraude ou portefeuille conduit au **Tier 14**. Il ne doit pas être contourné par un meilleur score commercial.

## Étape 6 — Capacité de remboursement et score

**Question 1 :** le commerce paraît-il stable ?  
**Question 2 :** peut-il rembourser ce montant sans étouffer son activité ?

Le score interne agrège les signaux disponibles. L'analyse de remboursement calcule séparément le DSCR, la charge du paiement, la tendance des soldes, la régularité des dépôts et un coussin de stress. Círculo apporte une troisième dimension.

La séparation est saine : un commerce peut sembler stable mais ne pas pouvoir supporter le montant demandé. Olin peut alors refuser ou proposer un montant inférieur.

## Étape 7 — Comité et décision humaine

**Question :** qui prend la décision officielle et pourquoi ?

Pendant le pilote :

- le Tier 1 est une recommandation automatique, pas une autorisation de décaissement ;
- les Tiers 2 à 12 vont au comité ;
- les Tiers 13 et 14 sont refusés et ne peuvent pas être transformés en accord par l'analyste ;
- toute décision humaine doit avoir une justification spécifique ;
- l'identité réelle du décideur et, idéalement, celle du second approbateur doivent être journalisées.

Une raison comme « bon dossier » n'est pas exploitable. Une raison utile ressemble à : « Círculo C2, DSCR 2,1, flux vérifiés, montant réduit pour maintenir la charge sous la politique du pilote ».

## Étape 8 — Offre, disclosures et acceptation

**Question :** le commerçant comprend-il le montant reçu, le montant total à payer, les dates et les conséquences d'un retard ?

Le code actuel représente un terme de 60 jours avec deux paiements et un coût fixe calculé sur deux mois. Cela reste une hypothèse de produit. Avant du live, l'offre doit être traduite en documents et communications approuvés : montant net, coût, calendrier, CAT applicable, taxes éventuelles, remboursement anticipé, défaut, recouvrement, traitement des données et canal de plainte.

Ne jamais présenter « 3 % par mois » comme si cela suffisait à expliquer le coût total.

## Étape 9 — Décaissement

**Question :** pouvons-nous prouver qu'un seul transfert a été envoyé au bon bénéficiaire ?

Le flux actuel réserve d'abord le décaissement, appelle STP, puis finalise ou annule la réservation si STP renvoie une erreur. C'est une amélioration importante contre le double envoi.

Il reste néanmoins une zone critique : si le système ne sait pas si STP a accepté le paiement, l'état doit devenir `unknown` ou `pending`, être bloqué et être rapproché manuellement. Il ne faut jamais « réessayer pour voir ».

## Étape 10 — Servicing et paiements

**Question :** chaque paiement reçu est-il associé une seule fois au bon prêt ?

Olin génère une référence de recouvrement, prévoit deux échéances, enregistre des événements de paiement idempotents, accepte les paiements partiels et détecte doublons ou trop-perçus. Chaque événement doit rester relié à la donnée brute STP et au relevé de règlement.

Le ledger Olin ne doit pas être la seule vérité. Il faut le comparer quotidiennement avec le système de paiement et le compte bancaire.

## Étape 11 — Retard, recouvrement et défaut

**Question :** qui agit, quand, par quel canal et avec quelle trace ?

Le code peut signaler une échéance après une période de grâce et marquer un défaut selon la règle opérationnelle actuelle. Une politique réelle doit préciser : rappel avant échéance, premier contact, escalade, promesse de paiement, restructuration éventuelle, frais autorisés, traitement équitable, récupération et fermeture du dossier.

Le recouvrement n'est pas « envoyer des messages ». C'est une séquence contrôlée, mesurable et juridiquement revue.

## Étape 12 — Résultat final et apprentissage

**Question :** savons-nous exactement ce qui est arrivé à chaque prêt ?

Les statuts utiles incluent :

- `not_disbursed` ;
- `disburse_pending` ou `disburse_failed` ;
- `active` ;
- `paid_on_time` ;
- `paid_late` ;
- `defaulted` ;
- `defaulted_recovered`.

Pour chaque prêt décaissé, conserver : version du moteur, score, tier, DSCR, bande Círculo, montant, coût, preuves, décision humaine, acteurs, folio STP, tous les paiements, actions de recouvrement, statut final et jours jusqu'au remboursement complet.

Ne jamais entraîner ou calibrer sur : données de démo, dossiers non décaissés, prêts encore actifs ou résultats non définitifs.

---

# 3. Les concepts de crédit indispensables

## 3.1 Principal / capital / monto principal

Le **principal** est le montant prêté avant intérêts, commissions et autres coûts. Si le commerçant reçoit un montant différent du montant contractuel à cause de frais retenus, il faut distinguer clairement les deux.

**Question à poser :** combien le commerçant reçoit-il réellement et sur quel montant les coûts sont-ils calculés ?

## 3.2 Intérêt, coût fixe et montant total à payer

L'**intérêt** rémunère le temps et le risque du capital. Un **coût fixe** peut être présenté différemment dans le produit, mais il reste un coût pour le client et peut entrer dans le calcul réglementaire du coût total.

Formule pédagogique simple :

```text
Montant total à payer = principal + intérêts + commissions + taxes et coûts applicables
```

Le code Olin calcule aujourd'hui un coût fixe à partir d'un taux mensuel et d'un terme de deux mois. Ce calcul technique ne remplace pas un calcul contractuel ou réglementaire approuvé.

## 3.3 CAT au Mexique et APR en anglais

Le **CAT** est un indicateur annualisé destiné à comparer le coût total d'un crédit en intégrant les éléments requis par les règles applicables. L'**APR** est un concept comparable dans le vocabulaire anglophone, mais les méthodes et obligations ne sont pas automatiquement identiques.

Ne calcule pas le CAT « à la main » pour une présentation commerciale. Utilise une méthode validée par les responsables juridiques et financiers du produit.

**À dire :** « Nous avons une hypothèse de pricing dans le prototype ; les disclosures et le CAT doivent être finalisés avec le partenaire et le conseil local. »

## 3.4 DSCR — capacité de remboursement

Le **Debt Service Coverage Ratio** compare les ressources disponibles au paiement de la dette.

```text
DSCR = cash-flow net disponible / paiement de dette sur la même période
```

- DSCR de 1,0 : juste assez de cash pour payer, sans marge.
- DSCR supérieur à 1,0 : présence d'un coussin.
- DSCR inférieur à 1,0 : ressources estimées insuffisantes.

Dans la politique codée d'Olin :

- **D1 :** DSCR au moins égal à 2,5 et aucun signal prudentiel ;
- **D2 :** DSCR de 1,5 à moins de 2,5, ou DSCR plus élevé avec des alertes ;
- **D3 :** DSCR inférieur à 1,5, indisponible ou présence d'un échec dur.

Ces seuils sont une politique initiale à tester, pas une vérité universelle.

## 3.5 Burden ratio — poids du paiement

Le burden ratio compare le paiement aux entrées de fonds :

```text
Charge = paiement périodique / entrées de fonds de la même période
```

Le code considère actuellement qu'une charge supérieure à 25 % force de la prudence et qu'une charge supérieure à 40 % est un échec dur. Là encore, ces seuils doivent être approuvés et observés sur la cohorte.

## 3.6 Círculo de Crédito et bureau

Un bureau de crédit agrège des informations de comportement de crédit. Olin utilise **Círculo de Crédito** dans son modèle actuel. Dire « nous n'utilisons pas le bureau » est donc faux.

L'absence de dossier n'est pas interprétée comme un bon score. Elle devient la bande **C3**, qui oblige le comité. Une délinquance active ou un score inférieur au seuil de politique devient **C4**, donc refus.

## 3.7 Underwriting / souscription / originación y evaluación

L'**underwriting** est le processus complet qui décide si un crédit doit être accordé, pour quel montant, à quel prix et sous quelles conditions. Le score n'est qu'un élément de l'underwriting.

Un bon underwriting combine : identité, fraude, capacité, comportement, garanties éventuelles, politique, concentration, prix, documentation et jugement humain.

## 3.8 PD, LGD et EAD

- **PD — Probability of Default :** probabilité qu'un emprunteur tombe en défaut sur un horizon défini.
- **LGD — Loss Given Default :** part de l'exposition réellement perdue après récupérations et coûts.
- **EAD — Exposure at Default :** montant exposé au moment du défaut.

Formule de base :

```text
Perte attendue = PD × LGD × EAD
```

Olin ne possède pas encore assez de résultats pour estimer ces paramètres de manière crédible. Pour le pilote, ils doivent être des limites et scénarios prudents définis par le responsable du risque, pas des sorties « apprises » par le moteur.

## 3.9 Mora, NPL et défaut

- **Mora :** paiement en retard selon l'échéance et la règle applicable.
- **Days Past Due (DPD) :** nombre de jours depuis l'échéance impayée.
- **NPL — Non-Performing Loan :** prêt classé non performant selon une définition précise.
- **Défaut :** événement défini par la politique ; il ne faut pas changer cette définition après avoir vu les résultats.

Toujours indiquer la définition et l'horizon. « Taux de défaut de 5 % » ne veut rien dire sans savoir : défaut à combien de jours, sur combien de prêts matures, en nombre ou en montant ?

## 3.10 Cohorte et vintage

Une **cohorte** regroupe des prêts qui partagent une caractéristique utile. Un **vintage** est souvent une cohorte par mois ou trimestre d'origination.

Exemples de découpes utiles : mois de décaissement, type de commerce, canal d'acquisition, tier de score, montant et premier prêt/récurrence.

Avec seulement 30 prêts, il faut éviter de multiplier les segments. La priorité est de conserver des données propres et de regarder le portefeuille comme une cohorte pilote, avec quelques découpes prévues à l'avance.

## 3.11 KYC et AML

- **KYC — Know Your Customer :** identifier et vérifier la personne ou l'entreprise.
- **AML/PLD — lutte contre le blanchiment :** détecter, contrôler, documenter et déclarer selon les obligations applicables.

Valider le format d'un RFC, d'un CURP ou d'une CLABE n'est pas une KYC complète. Enregistrer un seuil réglementaire dans un e-mail n'est pas un programme AML. Il faut savoir quelle entité porte l'obligation et qui exécute chaque contrôle.

## 3.12 Collections / cobranza / recouvrement

Le recouvrement commence avant le retard : calendrier clair, rappel, canal disponible et référence de paiement correcte. Après le retard, il faut une séquence, un propriétaire, un journal de contacts et des règles de traitement.

Mesures utiles : taux de contact, promesses de paiement, promesses tenues, cure rate, jours de retard, récupération brute, coût de récupération et résultat final.

## 3.13 Unit economics

La marge d'un crédit ne se résume pas aux intérêts facturés.

```text
Contribution par prêt
= revenus réellement encaissés
− coût du capital
− pertes de crédit
− coût d'acquisition
− vérifications, bureau et données
− paiement et décaissement
− servicing et recouvrement
− fraude
− opérations, technologie et coûts applicables
```

Mesures à suivre par cohorte :

- montant moyen décaissé ;
- revenu contractuel et revenu réellement encaissé ;
- coût des données et du bureau par dossier ;
- coût d'acquisition par prêt décaissé, pas seulement par lead ;
- taux d'approbation et taux d'acceptation de l'offre ;
- premier paiement en retard ;
- retard et perte en nombre **et** en montant ;
- coût de recouvrement ;
- repeat rate seulement après un cycle complet ;
- contribution nette par prêt mature.

Ne jamais présenter une projection comme une unit economics observée.

## 3.14 Risque de portefeuille

Un bon prêt individuel peut devenir un mauvais portefeuille si tous les prêts dépendent du même quartier, distributeur, saison ou activité. Olin possède déjà des alertes de concentration. Les seuils codés sont des points de départ et doivent être repris dans une politique signée.

La question du comité n'est pas seulement « ce commerçant peut-il payer ? », mais aussi « que se passe-t-il si le choc touche tous les commerçants similaires en même temps ? »

---

# 4. Comment le moteur Olin décide

## 4.1 Les six signaux du score interne

Pour les abarrotes, les poids codés actuels sont :

| Signal | Poids initial | Ce qu'il essaie de représenter |
|---|---:|---|
| Historique d'achats FMCG | 30 % | continuité et tendance de réapprovisionnement |
| Flux bancaire | 20 % | volume, régularité, soldes, incidents et tendance |
| Ancienneté du commerce | 20 % | permanence et cohérence de l'activité |
| Google Maps | 15 % | existence, rating, avis et activité visible |
| Volume POS | 10 % | volume et régularité des paiements électroniques |
| IMSS | 5 % | présence d'une activité employeur lorsqu'elle existe |

Si une donnée manque, le moteur redistribue le poids entre les signaux disponibles et calcule séparément la couverture. Cela rend la démonstration possible, mais exige de la prudence : deux scores identiques peuvent reposer sur une quantité de preuve très différente.

Le score interne devient :

- **S1 :** score au moins égal à 75 ;
- **S2 :** score de 50 à moins de 75 ;
- **S3 :** score inférieur à 50.

## 4.2 Les bandes Círculo

| Bande | Règle actuelle | Conséquence |
|---|---|---|
| C1 | score au moins égal à 670, sans délinquance active | éligible au Tier 1 si les autres dimensions sont fortes |
| C2 | score de 600 à 669 | comité au mieux |
| C3 | aucun dossier, non consulté ou score numérique indisponible | comité au mieux |
| C4 | score inférieur à 600 ou délinquance active | refus Tier 13 |

## 4.3 Les bandes DSCR

| Bande | Règle actuelle | Conséquence |
|---|---|---|
| D1 | DSCR au moins égal à 2,5, sans alerte de capacité | peut accéder au Tier 1 |
| D2 | DSCR de 1,5 à moins de 2,5, ou alerte prudente | comité |
| D3 | DSCR inférieur à 1,5, indisponible ou échec dur | refus Tier 13 |

## 4.4 La matrice 1 à 14

Les colonnes ci-dessous représentent les quatre combinaisons qui restent lorsque le DSCR et le score sont au-dessus de leur plancher :

| Círculo | D1 + S1 | D1 + S2 | D2 + S1 | D2 + S2 |
|---|---:|---:|---:|---:|
| C1 | **Tier 1 — AUTO_APPROVE** | Tier 2 — COMMITTEE | Tier 3 — COMMITTEE | Tier 4 — COMMITTEE |
| C2 | Tier 5 — COMMITTEE | Tier 6 — COMMITTEE | Tier 7 — COMMITTEE | Tier 8 — COMMITTEE |
| C3 | Tier 9 — COMMITTEE | Tier 10 — COMMITTEE | Tier 11 — COMMITTEE | Tier 12 — COMMITTEE |

- **Tier 13 :** C4, ou D3, ou S3 → `DECLINE`.
- **Tier 14 :** blocage avant score pour fraude, portefeuille ou provenance interdite → `DECLINE`.

Il existe 36 combinaisons possibles de Círculo × DSCR × score. Celles qui ne figurent pas dans les 12 routes positives tombent dans le Tier 13.

## 4.5 Pourquoi un Tier 1 peut encore aller au comité

Même si la matrice donne Tier 1, Olin route la recommandation vers le comité si l'un des garde-fous suivants apparaît :

- distributeur FMCG non confirmé ;
- ancienneté inférieure au minimum de phase 0 ;
- rating Google Maps sous le minimum de phase 0 ;
- borne basse de l'intervalle de confiance sous 70 ;
- couverture de données sous 60 % ;
- score de risque fraude au moins égal à 30 ;
- autre alerte de capacité de remboursement.

Le tier de matrice est conservé pour l'audit, mais la décision devient plus prudente.

## 4.6 Les deux systèmes de tiers à ne pas confondre

Olin contient deux notions différentes :

1. **Tier de score 1 à 14 :** qualité et décision du dossier actuel.
2. **Tier de graduation 0 à 3 :** hypothèse de conditions pour un client récurrent selon son historique.

Ne dis jamais simplement « il est Tier 1 » sans préciser de quel système tu parles. Les conditions de graduation sont codées, mais ne doivent pas être présentées comme une offre validée avant approbation commerciale, risque et juridique.

## 4.7 Conditions actuelles du prototype

Le code représente un nouveau client avec un plafond initial de MXN 30 000, un terme de 60 jours, deux paiements et une hypothèse de coût mensuel. Ce sont des paramètres du prototype et du runbook, pas une promesse publique. Tout changement de ticket, prix ou terme doit devenir une décision de politique versionnée et testée.

---

# 5. Comment présenter Olin

## 5.1 L'ordre qui fonctionne

Ne commence pas par « nous avons 14 tiers, six APIs et un moteur ». Commence ainsi :

1. un commerce réel peut être mal décrit par le dossier traditionnel ;
2. Olin transforme des preuves d'opération en une recommandation reconstruisible ;
3. montre un dossier et la raison de la décision ;
4. explique honnêtement ce qui est live, mocké ou manquant ;
5. propose un pilote shadow très précis.

La confiance vient davantage d'une frontière claire que d'une longue liste de fonctionnalités.

## 5.2 Script de 3 minutes — espagnol

> Gracias por el tiempo. Olin nace de una observación simple: un abarrotes puede ser un negocio real, vender todos los días y reabastecerse cada semana, pero seguir siendo difícil de evaluar porque gran parte de su operación no aparece en un expediente financiero tradicional.
>
> Olin es un prototipo de infraestructura de decisión crediticia. No reemplaza al originador y hoy no pretende tomar decisiones sin supervisión. Organiza evidencia verificable del comercio —por ejemplo compras FMCG, flujo bancario, antigüedad, POS, Google Maps e IMSS cuando están disponibles— y separa dos preguntas: ¿es un negocio estable? y ¿puede pagar este monto específico?
>
> El motor cruza tres dimensiones: Círculo de Crédito, DSCR y un indicador interno. El resultado es una recomendación explicable en 14 rutas: una sola combinación puede recomendar aprobación automática, doce van a comité y los bloqueos de capacidad, bureau, fraude o portafolio se rechazan. Durante el piloto, incluso una recomendación automática necesita la aprobación y la justificación de un analista.
>
> En esta pantalla vemos un expediente ilustrativo. Podemos reconstruir qué señales estaban disponibles, su fuente, el score, el DSCR, la banda de Círculo, las alertas y el monto recomendado. Después registramos la decisión humana, el desembolso, cada pago y el resultado final. Eso permite aprender de la cohorte sin perder el contexto de cada caso.
>
> Quiero ser transparente: los datos bancarios y FMCG de la demo son mocks deterministas. En producción el sistema los bloquea. Todavía necesitamos fuentes verificadas, controles de acceso por usuario, doble control del desembolso, cifrado, reconciliación autoritativa de STP y validación jurídica y operativa.
>
> Por eso no proponemos empezar con originación automática. El siguiente paso correcto es un piloto sombra con expedientes consentidos: Olin genera su recomendación, el socio conserva su proceso oficial y comparamos calidad de datos, tiempo, concordancia y resultados. Si esa fase funciona y se cierran los controles, se puede diseñar el piloto vivo más pequeño posible. Lo que buscamos hoy es un socio para definir ese piloto y las fuentes de datos necesarias.

## 5.3 Script de 3 minutes — anglais

> Thank you for the time. Olin starts with a simple observation: a corner store can be a real business, sell every day and restock every week, yet remain difficult to assess because much of its operation does not appear in a traditional financial file.
>
> Olin is a credit decision infrastructure prototype. It does not replace the lender, and today it is not meant to make unsupervised decisions. It organizes verified operating evidence — such as FMCG purchases, bank cash flow, business tenure, POS, Google Maps and IMSS when available — and separates two questions: is this a stable business, and can it repay this specific amount?
>
> The engine combines three dimensions: Círculo de Crédito, DSCR and an internal indicator. It produces an explainable recommendation across 14 routes: only one combination can recommend auto-approval, twelve go to committee, and capacity, bureau, fraud or portfolio blocks are declined. During the pilot, even an automatic recommendation requires an analyst's approval and written rationale.
>
> This screen shows an illustrative case. We can reconstruct which signals were available, where they came from, the score, DSCR, Círculo band, warnings and recommended amount. We then record the human decision, disbursement, each payment and the final outcome. That creates a useful cohort without losing the context of each case.
>
> I want to be transparent: the banking and FMCG data in the demo are deterministic mocks. Production mode rejects them. We still need verified data sources, named-user access, dual control for disbursement, encryption, authoritative STP reconciliation, and legal and operational validation.
>
> That is why we are not proposing automated origination first. The right next step is a shadow pilot using consented files: Olin produces a recommendation, the partner keeps its official process, and we compare data quality, turnaround, agreement and later outcomes. If that works and the controls are closed, we can design the smallest possible live pilot. Today we are looking for a partner to define that pilot and the required data sources.

## 5.4 Trame de 7 minutes — prête à dire

### 0:00–0:45 — Le problème

**Espagnol :** « No decimos que todo comercio sin historial sea buen sujeto de crédito. Decimos que el expediente tradicional deja fuera señales de operación que pueden mejorar una evaluación prudente. »

**English:** “We are not saying every thin-file merchant is creditworthy. We are saying the traditional file misses operating evidence that can improve a prudent assessment.”

### 0:45–1:30 — L'idée Olin

**Espagnol :** « Olin convierte esa evidencia en una recomendación explicable y separa calidad del negocio de capacidad para pagar. »

**English:** “Olin turns that evidence into an explainable recommendation and separates business quality from repayment capacity.”

### 1:30–3:30 — Démonstration

Montre dans cet ordre :

1. l'identité et le montant demandé ;
2. les sources et leur statut vérifié/non vérifié ;
3. Círculo, DSCR et score interne ;
4. le tier, les raisons et les alertes ;
5. la décision humaine et sa justification ;
6. le ledger de décaissement/paiements et le statut final.

**Espagnol :** « No les pido que confíen en un número. Les muestro cómo reconstruir la recomendación y qué evidencia falta. »

**English:** “I am not asking you to trust a number. I am showing you how to reconstruct the recommendation and see which evidence is missing.”

### 3:30–4:30 — Contrôles

**Espagnol :** « Los mocks son visibles y están bloqueados en producción. Los rechazos del motor no se pueden sobreescribir durante el piloto y todo acuerdo requiere razón humana. »

**English:** “Mocks are visible and blocked in production. Engine declines cannot be overridden during the pilot, and every approval requires a human rationale.”

### 4:30–5:30 — Vérité produit

**Espagnol :** « Esto es un prototipo funcional, no un modelo ML validado ni una operación de crédito lista. La prioridad es cerrar datos, seguridad, reconciliación y marco operativo. »

**English:** “This is a functional prototype, not a validated ML model or a ready lending operation. The priority is closing data, security, reconciliation and the operating framework.”

### 5:30–7:00 — Demande

**Espagnol :** « Propongo una sesión de diseño del piloto: definir la población, datos disponibles, consentimiento, comparación contra la decisión actual, métricas y condiciones de avance. El primer entregable sería un protocolo de piloto sombra, no un compromiso de originación. »

**English:** “I propose a pilot-design session: define the population, available data, consent, comparison against the current decision, metrics and stage gates. The first deliverable would be a shadow-pilot protocol, not an origination commitment.”

## 5.5 Trame de 15 minutes — réunion partenaire

| Temps | Ce que tu montres | Phrase de transition |
|---:|---|---|
| 0–2 min | Un cas réel du problème, sans statistique non sourcée | **ES:** « El problema no es falta de actividad; es falta de evidencia organizada. » / **EN:** “The problem is not a lack of activity; it is a lack of organized evidence.” |
| 2–4 min | La proposition de valeur et la séparation qualité/capacité | **ES:** « Una buena tienda todavía puede ser un mal crédito para un monto demasiado alto. » / **EN:** “A good store can still be a bad loan at the wrong amount.” |
| 4–8 min | Démo complète d'un dossier illustratif | **ES:** « Cada recomendación deja una ruta de auditoría. » / **EN:** “Every recommendation leaves an audit trail.” |
| 8–10 min | Gouvernance : humain, refus, consentement, provenance, démo/production | **ES:** « Diseñamos el control antes de escalar la automatización. » / **EN:** “We design control before scaling automation.” |
| 10–12 min | Ce qui manque et pourquoi le shadow pilot est la bonne étape | **ES:** « La pregunta de esta fase no es cuántos créditos podemos colocar, sino si podemos producir evidencia consistente y decisiones comparables. » / **EN:** “The question at this stage is not how many loans we can place, but whether we can produce consistent evidence and comparable decisions.” |
| 12–15 min | Questions au partenaire et prochain pas daté | **ES:** « ¿Quién debe participar en una sesión técnica y de riesgo para definir el protocolo? » / **EN:** “Who should join a technical and risk session to define the protocol?” |

### Démonstration : comportement à adopter

- utilise toujours un dossier marqué **illustratif** ;
- dis explicitement quelles données sont mockées ;
- ne cache pas un passage au comité ; il démontre justement l'explicabilité ;
- montre une raison de refus et explique qu'elle n'est pas surmontable pendant le pilote ;
- ne déclenche aucun transfert réel pendant une présentation ;
- termine sur le journal du résultat, pas sur le score : la valeur future vient de la boucle complète.

---

# 6. Pitch partenaire et pitch investisseur

## 6.1 Ce ne sont pas les mêmes conversations

| Sujet | Partenaire opérationnel | Investisseur equity |
|---|---|---|
| Question principale | « Est-ce que cela améliore mon workflow sans créer un risque incontrôlé ? » | « Cette équipe peut-elle construire une entreprise défendable et rentable ? » |
| Preuve attendue | protocole, données, intégration, gouvernance, comparaison, sécurité | marché sourcé, wedge, adoption, economics, équipe, vitesse d'apprentissage |
| Demande | accès à une équipe, définition d'un shadow pilot, données consenties, critères de passage | capital lié à des milestones précis et à un plan d'usage |
| Risque perçu | conformité, qualité des données, perturbation opérationnelle, responsabilité | risque réglementaire, accès aux données, défaut, financement du portefeuille, distribution |
| Erreur à éviter | demander immédiatement un partenariat commercial ou un financement des prêts | présenter une démo comme de la traction et des projections comme des résultats |

## 6.2 Pitch partenaire — version courte

**Espagnol**

> Estamos construyendo una capa explicable de decisión para microcomercios. No buscamos reemplazar su política ni originar automáticamente. Queremos evaluar, con consentimiento, una muestra de expedientes en paralelo a su proceso, medir cobertura y calidad de datos, comparar recomendaciones y acordar de antemano las condiciones para avanzar. El primer paso que proponemos es una sesión conjunta de riesgo, datos y operación para diseñar el protocolo.

**English**

> We are building an explainable decision layer for micro-merchants. We are not asking to replace your policy or automate origination. We want to assess a consented sample in parallel with your process, measure data coverage and quality, compare recommendations, and pre-agree the conditions for moving forward. Our proposed first step is a joint risk, data and operations session to design the protocol.

## 6.3 Pitch investisseur — version honnête aujourd'hui

**Espagnol**

> Olin está construyendo infraestructura de decisión para crédito a microcomercios con poca historia formal. El prototipo explicable y el flujo operativo existen, pero todavía no presentamos performance crediticio ni integraciones de producción como hechos. Nuestra siguiente prueba de valor es conseguir un piloto sombra con datos consentidos, cerrar los controles de operación y convertir una cohorte limitada en resultados auditables. Buscamos conversaciones con inversionistas que entiendan fintech mexicana y puedan ayudarnos a alcanzar esos hitos, no sólo financiar una historia.

**English**

> Olin is building credit decision infrastructure for thin-file micro-merchants. The explainable prototype and operating workflow exist, but we are not presenting credit performance or production integrations as facts. Our next proof point is a shadow pilot using consented data, closing the operating controls, and turning a limited cohort into auditable outcomes. We want conversations with investors who understand Mexican fintech and can help us reach those milestones, not just fund a story.

## 6.4 Qui approcher maintenant

### Priorité 1 — Un originator ou prêteur encadré

Ce partenaire peut apporter une politique de crédit existante, une décision de référence, la documentation, les opérations et éventuellement le capital. La première demande n'est pas « financez Olin », mais « construisons un protocole shadow et définissons qui porte chaque responsabilité ».

### Priorité 2 — Infrastructure de compte, POS et paiement

Une banque, un acquéreur ou un fournisseur POS peut aider sur l'ouverture de compte, les encaissements, les données de settlement et les mécanismes de remboursement. Cela ne signifie pas automatiquement qu'il peut ou veut originer les prêts.

Dans le cas d'une conversation avec Monex, présente les rôles comme des **hypothèses à explorer** :

- un compte pour le commerçant emprunteur ;
- une terminale POS ou une solution d'acceptation ;
- des données de transactions et de settlement avec consentement ;
- un mécanisme de remboursement compatible avec le cadre juridique et le produit ;
- éventuellement, plus tard, une discussion sur l'origination ou le financement.

Le commerçant emprunteur pourrait ouvrir le compte et utiliser le POS. Le prêteur/originator et l'infrastructure de paiement peuvent rester des entités différentes.

### Priorité 3 — Distributeur ou détenteur de données FMCG

L'objectif initial est de comprendre la disponibilité, le droit d'usage, la granularité, l'identifiant marchand, la fraîcheur et la qualité. Ne demande pas d'abord une API complète ; demande un atelier de faisabilité et un échantillon gouverné.

### Priorité 4 — Experts de risque et d'opération

Il faut au minimum une personne capable de posséder la politique de crédit, une personne de servicing/recouvrement et un conseil mexicain sur structure, contrats, données et PLD/AML.

### Priorité 5 — Marchands du pilote

Ils aident à vérifier l'expérience, le consentement, la disponibilité des preuves et la compréhension des conditions. Une interview n'est pas une demande de prêt et ne doit pas être présentée comme une conversion.

## 6.5 Qui approcher plus tard

- angels fintech et opérateurs crédit, après un protocole partenaire crédible ;
- fonds pre-seed/seed fintech, lorsque les milestones, le modèle économique et les risques sont mieux démontrés ;
- fournisseurs de capital de dette ou warehouse, seulement lorsque l'entité, la politique, les performances et le servicing le permettent ;
- partenariats de distribution plus larges, après preuve que le flux fonctionne sur une cohorte limitée.

## 6.6 Questions à poser à un partenaire comme Monex

1. Quelle entité pourrait ouvrir un compte aux commerçants ciblés et sous quelles conditions KYC ?
2. Quels produits POS ou d'acceptation sont disponibles pour ces profils ?
3. Quelles données de transaction et de settlement peuvent être partagées, avec quel consentement, quelle fréquence et quelle granularité ?
4. Un remboursement automatique ou une retenue sur settlement est-il techniquement et juridiquement envisageable ?
5. Monex se voit-il d'abord comme infrastructure de compte/paiement, ou existe-t-il une équipe crédit à consulter plus tard ?
6. Qui doit participer à une session de conception : risque, conformité, produit, acquiring, data et juridique ?

Ne demande pas « pouvez-vous tout faire ? ». Demande quel rôle est possible maintenant et quels critères ouvriraient le rôle suivant.

---

# 7. Refaire le deck sans surpromettre

## 7.1 Diagnostic du deck existant

Le document actuel ressemble davantage à un rapport de 20 pages qu'à un deck de réunion. Il est dense, mélange présent et futur et contient des affirmations qui doivent être supprimées ou prouvées.

### À corriger immédiatement

- l'ancienne logique de décision par seuil simple n'est plus le produit actuel ;
- Olin utilise Círculo : ne pas écrire « no bureau » ;
- ne pas présenter XGBoost, LightGBM, GNN, SHAP ou un taux de précision comme déjà validés ;
- ne pas présenter FEMSA, Monex, Syncfy ou une autre organisation comme partenaire sans accord explicite ;
- ne pas annoncer un temps de décaissement ou un SLA non mesuré ;
- ne pas présenter des personas ou prêts fictifs comme des clients réels ;
- ne pas annoncer une structure juridique, une validation CNBV, KYC/AML « live » ou une conformité confirmée sans documents ;
- ne pas présenter des projections de rendement investisseur comme des résultats ou des attentes garanties ;
- ne pas utiliser de statistiques de marché sans source, date et définition ;
- ne pas présenter 30 prêts comme suffisants pour entraîner un modèle ML de production ;
- ne pas afficher des conseillers, logos ou biographies sans vérification et consentement.

## 7.2 Règle visuelle

Une slide doit porter **une idée principale**, lisible en quelques secondes. Le détail va dans la discussion, les notes ou une annexe. Une capture produit, un schéma simple ou un chiffre sourcé vaut mieux que six paragraphes.

## 7.3 Outline précis d'un deck de 10 slides

### Slide 1 — Olin en une phrase

**Titre :** « Explainable credit decisions for Mexico's thin-file micro-merchants »  
**Sous-titre :** prototype + étape actuelle + nom du fondateur.  
Pas de chiffre de marché non sourcé.

### Slide 2 — Le problème observable

Un exemple simple d'abarrotes : opération réelle, dossier financier incomplet. Utiliser une donnée externe seulement si sa source, sa date et sa définition sont affichées. Sinon rester qualitatif.

### Slide 3 — L'insight

Le commerce laisse des preuves opérationnelles dispersées. La valeur d'Olin est de les organiser avec provenance, puis de séparer qualité du commerce et capacité de remboursement.

### Slide 4 — Comment Olin fonctionne

Un flux visuel : consentement → preuves → pré-contrôles → Círculo + DSCR + score → recommandation → humain → résultat.

### Slide 5 — La décision explicable

Une capture de l'interface et les trois dimensions. Montrer le Tier 1, le comité et les refus, sans afficher les 36 cases si cela surcharge la slide.

### Slide 6 — Ce qui existe aujourd'hui

Deux colonnes : **Working prototype** et **Not yet live**. C'est une slide de crédibilité, pas un aveu de faiblesse.

### Slide 7 — Le pilote proposé

Shadow pilot d'abord : population, consentement, données, décision de référence, métriques, gouvernance et conditions de passage. Aucun décaissement automatique.

### Slide 8 — Modèle économique à tester

Présenter les hypothèses séparément : logiciel/decisioning facturé au dossier ou à la plateforme, service d'origination, partage économique ou autre. Ne retenir qu'une hypothèse principale après les conversations partenaires. Distinguer revenus logiciel et revenus/risque de prêt.

### Slide 9 — Équipe et capacité d'exécution

Qui construit, qui possède le risque, qui possède l'opération et quels rôles manquent. N'afficher que des personnes confirmées.

### Slide 10 — Demande et milestones

Pour un partenaire : session de design, propriétaire, données et protocole.  
Pour un investisseur : capital éventuel lié à des milestones concrets — pilote shadow, contrôles fermés, entité et voie réglementaire, premières cohortes matures — sans promettre le résultat.

## 7.4 Checklist avant d'envoyer le deck

- chaque chiffre a une source, une date et une définition ;
- chaque logo correspond à une relation autorisée ;
- les mots « live », « partner », « customer », « approved » et « integrated » sont vérifiés ;
- présent, pilote et roadmap sont visuellement séparés ;
- le scorecard actuel Círculo/DSCR/interne est correct ;
- les mocks sont identifiés ;
- aucun rendement investisseur n'est promis ;
- aucun résultat fictif n'est présenté comme réel ;
- l'ask tient en une phrase ;
- le deck peut être expliqué sans lire le texte.

---

# 8. Plan 30 / 60 / 90 jours

Le plan est construit avec des **gates**. Si une gate n'est pas fermée, on ne compense pas en accélérant le marketing ou le décaissement.

## Jours 0–30 — Rendre Olin présentable et gouvernable

### Produit et vérité commerciale

- figer une phrase de positionnement et supprimer toutes les affirmations non prouvées du site et du deck ;
- préparer une démo illustrative stable avec un scénario accord, comité et refus ;
- créer un one-pager partenaire et le deck de 10 slides ;
- tenir un registre « fonctionne / partiel / roadmap » mis à jour à chaque réunion.

### Risque et droit

- faire répondre par écrit : quelle entité porte le crédit, les contrats, le capital, le CAT/disclosure, les obligations de données et les obligations PLD/AML ?
- faire approuver une politique pilote : éligibilité, ticket, pricing, exceptions, quorum, fraude, concentration, retard, défaut et conditions d'arrêt ;
- finaliser le texte de consentement et la notice de confidentialité avec version et preuve ;
- nommer les responsables de chaque étape du cycle.

### Sécurité et argent

- mettre en place des utilisateurs nommés et une trace de l'acteur ;
- ajouter le double contrôle du décaissement ;
- définir chiffrement, rétention, sauvegarde et tester une restauration ;
- définir les états STP, le rapprochement quotidien et la procédure `unknown` ;
- exécuter un exercice d'incident sans argent réel.

### Partenariats

- obtenir des réunions de discovery avec un originator, une infrastructure compte/POS/paiement et une source FMCG ;
- terminer chaque réunion avec un responsable et un prochain pas, pas avec « restons en contact ».

## Jours 31–60 — Conduire un shadow pilot

- convenir d'un protocole écrit avec le partenaire : population, consentement, champs, décision de référence, durée, sécurité et sortie ;
- utiliser uniquement des dossiers consentis et des preuves réelles ou clairement absentes ;
- ne jamais remplacer une donnée manquante par un mock dans l'analyse shadow ;
- mesurer la couverture par signal, les erreurs de rapprochement d'identité, le temps analyste, la proportion comité et l'accord/désaccord avec le processus partenaire ;
- documenter chaque désaccord : politique différente, donnée absente, calcul, erreur ou jugement ;
- tester le cycle de paiement et le rapprochement avec des montants sandbox ou un exercice contrôlé ;
- finaliser les scripts de rappel, l'escalade et la journalisation du recouvrement ;
- mettre à jour le scorecard seulement par une décision versionnée, pas au cas par cas.

**Sortie attendue :** un rapport shadow qui montre ce que les données permettent réellement, où le moteur diverge et quels contrôles restent ouverts. Pas un taux de défaut inventé.

## Jours 61–90 — Décider si un pilote live est responsable

### Gate de passage

Ne passer au live que si toutes les réponses sont oui :

- entité, contrats, consentement, confidentialité et obligations opérationnelles validés ;
- capital et propriétaire du risque identifiés ;
- sources utilisées en production réellement vérifiées ;
- utilisateurs, rôles, double contrôle, chiffrement et sauvegarde opérationnels ;
- STP et ledger rapprochables avec traitement des états inconnus ;
- comité, servicing, recouvrement, incidents et stop conditions testés ;
- politique et limites signées ;
- partenaire et équipe acceptent le protocole.

Si la gate est fermée, commencer par la plus petite tranche live approuvée par le responsable risque et n'étendre que lorsque les décaissements et rapprochements sont propres. Le cap global reste 30 prêts avant revue de la cohorte.

Si la gate n'est pas fermée, continuer le shadow pilot. Ce n'est pas un échec ; c'est éviter qu'une erreur opérationnelle transforme une bonne idée en perte ou en problème réglementaire.

## Ce qu'il faut faire dès la prochaine semaine

1. apprendre et réciter la phrase Olin en français, espagnol et anglais ;
2. préparer une démo de 7 minutes avec trois dossiers illustratifs ;
3. remplacer le deck existant par l'outline de 10 slides ;
4. faire une liste écrite des claims interdits tant qu'ils ne sont pas prouvés ;
5. préparer le protocole d'une session de design avec Monex ou un autre partenaire potentiel ;
6. obtenir une réponse écrite sur le rôle juridique et opérationnel de chaque entité ;
7. choisir un responsable risque expérimenté capable de challenger la politique du pilote.

---

# 9. Objections fréquentes et réponses

## « Pourquoi ne pas utiliser uniquement le bureau ? »

**Réponse :** le bureau reste important et Olin l'utilise. La thèse est que des preuves opérationnelles vérifiées peuvent améliorer la compréhension d'un commerce thin-file et la taille du montant, sans ignorer le bureau.

**ES :** « No sustituimos Círculo; lo combinamos con capacidad de pago y evidencia operativa verificable. »  
**EN :** “We do not replace Círculo; we combine it with repayment capacity and verified operating evidence.”

## « Est-ce de l'IA ? »

**Réponse :** pas aujourd'hui. C'est une scorecard explicable à règles. Le ML ne deviendrait pertinent qu'avec un volume suffisant de données propres, matures et représentatives.

**ES :** « Hoy es una política explicable basada en reglas, no un modelo ML entrenado. »  
**EN :** “Today it is an explainable rules-based policy, not a trained ML model.”

## « Où sont les données réelles ? »

**Réponse :** la démo utilise des mocks bancaires et FMCG clairement identifiés. La priorité du shadow pilot est précisément de vérifier l'accès, la couverture et la qualité de données consenties.

**ES :** « La demo separa claramente mock y producción; no presentamos el mock como evidencia real. »  
**EN :** “The demo clearly separates mock and production data; we do not present mock data as real evidence.”

## « Trente prêts suffisent-ils ? »

**Réponse :** ils peuvent révéler des problèmes d'opération, de données et d'expérience. Ils ne suffisent pas à valider une précision ML ou une performance de portefeuille stable.

**ES :** « Treinta créditos sirven para aprender operación y calidad de datos, no para declarar un modelo predictivo validado. »  
**EN :** “Thirty loans can teach us about operations and data quality, not validate a predictive model.”

## « Olin est-il le prêteur ? »

**Réponse :** le rôle juridique et économique doit être défini avec le partenaire et le conseil. Aujourd'hui, le produit se présente comme une infrastructure de décision, pas comme une entité de crédit confirmée.

**ES :** « Hoy presentamos Olin como infraestructura de decisión; la entidad que origina y asume el riesgo debe quedar definida por escrito. »  
**EN :** “We currently present Olin as decision infrastructure; the entity that originates and owns the risk must be defined in writing.”

## « Que se passe-t-il sans banque ou sans POS ? »

**Réponse :** POS manquant n'est pas automatiquement un refus. En revanche, sans données suffisantes pour mesurer la capacité, le dossier ne doit pas être auto-approuvé ; le modèle actuel place un DSCR indisponible en D3.

**ES :** « La ausencia de POS no mata el expediente, pero no inventamos capacidad de pago cuando faltan datos. »  
**EN :** “Missing POS does not kill the file, but we do not invent repayment capacity when data is absent.”

## « Qu'est-ce qui empêche la fraude ? »

**Réponse :** il existe des pré-contrôles d'identité, adresse, INE, CLABE et portefeuille. Ils réduisent le risque mais ne remplacent pas une KYC complète, la vérification documentaire et les procédures du partenaire.

**ES :** « Tenemos precontroles y bloqueos, pero no los presentamos como una KYC completa. »  
**EN :** “We have pre-checks and blocks, but we do not present them as complete KYC.”

## « Pourquoi le partenaire ne construirait-il pas cela lui-même ? »

**Réponse :** il pourrait. Olin doit prouver qu'il réduit le temps de design, organise des sources difficiles, rend les décisions auditables et produit une boucle outcome exploitable. C'est une hypothèse à démontrer, pas un avantage acquis.

**ES :** « Nuestra prueba no es que nadie pueda construirlo; es que Olin pueda acelerar una evaluación auditable con menos carga operativa. »  
**EN :** “Our proof is not that nobody can build it; it is that Olin can accelerate an auditable assessment with less operational burden.”

## « Qu'en est-il de la réglementation ? »

**Réponse :** ne réponds jamais « c'est réglé ». Explique quelle structure est envisagée, quelles questions sont encore ouvertes et qui doit les approuver.

**ES :** « Tenemos una ruta en revisión; no afirmamos certeza jurídica antes de tener la estructura, los contratos y las responsabilidades aprobados. »  
**EN :** “We have a path under review; we do not claim legal certainty before the structure, contracts and responsibilities are approved.”

## « Quel est votre taux de défaut ? »

**Réponse :** aucun taux observé ne doit être annoncé sans prêts réels matures et définition précise. Donne le statut actuel et le plan de mesure.

**ES :** « Todavía no tenemos una cohorte madura para reportar performance; definimos desde ahora cómo mediremos mora, pérdida y recuperación. »  
**EN :** “We do not yet have a mature cohort for reporting performance; we are defining now how delinquency, loss and recovery will be measured.”

---

# 10. « Ne jamais dire » / « Dire plutôt »

| Ne jamais dire | Dire plutôt |
|---|---|
| « Olin utilise une IA avec 89 % de précision. » | « Olin utilise aujourd'hui une scorecard explicable basée sur des règles ; la performance doit être mesurée sur des résultats matures. » |
| « Nous prêtons déjà aux abarrotes. » | « Nous avons un prototype et préparons un pilote shadow ; l'entité qui originerait les prêts reste à formaliser. » |
| « Monex est notre partenaire. » | « Nous explorons avec des contacts potentiels le rôle que Monex ou un acteur similaire pourrait jouer. » |
| « Nous sommes intégrés à FEMSA/Bimbo. » | « L'accès à une preuve FMCG vérifiée est une priorité de partenariat ; la démo utilise un mock. » |
| « La banque est live. » | « Le connecteur existe, mais l'accès et le flux de production restent à démontrer. » |
| « Prêt pour la production. » | « Prêt pour une démo et la préparation d'un shadow pilot ; plusieurs gates restent ouvertes avant le live. » |
| « Auto-approve signifie argent en deux heures. » | « Tier 1 peut recommander l'accord ; pendant le pilote, un analyste doit encore approuver et justifier. » |
| « Nous n'utilisons pas le bureau. » | « Nous croisons Círculo avec le DSCR et un score opérationnel. » |
| « Trente prêts vont entraîner notre XGBoost. » | « Les 30 premiers prêts servent à tester l'opération, la qualité des données et les premiers signaux de politique. » |
| « Le cadre légal est confirmé. » | « Une voie est en cours de revue ; chaque responsabilité doit être confirmée par écrit. » |
| « Le commerçant est garanti de rembourser. » | « Le moteur estime et documente le risque ; aucun crédit n'est sans risque. » |
| « Rendement investisseur de 3–5x ou 10–15x. » | « Voici les milestones, les risques et l'usage du capital ; le rendement n'est pas garanti. » |
| « Nos personas ont déjà reçu un prêt. » | « Ce scénario est illustratif et sert à montrer le flux. » |
| « 95 % n'ont pas accès au crédit. » sans source | « Une partie des microcommerces reste thin-file ; voici la source, la date et la population exacte de la donnée utilisée. » |
| « Il suffit d'ouvrir un compte Monex et de donner un POS. » | « Compte, POS, données de settlement et remboursement sont quatre sujets à valider séparément. » |

---

# 11. Glossaire trilingue

| Français | Español | English | Définition courte |
|---|---|---|---|
| Emprunteur | acreditado / prestatario | borrower | personne ou entreprise qui reçoit le crédit |
| Prêteur | prestamista / acreditante | lender | entité qui accorde le crédit et porte la créance |
| Originator | originador | originator | entité/processus qui crée le prêt et le dossier |
| Principal | capital / principal | principal | montant de base prêté |
| Intérêt | interés | interest | prix du temps et du risque du capital |
| CAT | CAT | total annual cost | indicateur réglementaire mexicain du coût total annualisé |
| APR | tasa anual equivalente | APR | indicateur annualisé anglophone ; méthode à ne pas assimiler automatiquement au CAT |
| Échéance | fecha de pago / vencimiento | due date | date à laquelle un paiement est exigible |
| Mensualité / paiement | pago / cuota | installment | montant prévu à une échéance |
| Capacité de remboursement | capacidad de pago | repayment capacity | aptitude à payer sans mettre l'activité en danger |
| DSCR | DSCR | DSCR | cash-flow disponible divisé par service de la dette |
| Charge du paiement | carga de pago | payment burden | paiement rapporté aux entrées de fonds |
| Bureau de crédit | sociedad de información crediticia / buró | credit bureau | source d'historique et de comportement de crédit |
| Thin-file | expediente limitado | thin-file | dossier formel très limité ou absent |
| Score interne | indicador interno | internal score | synthèse Olin des signaux opérationnels |
| Souscription | evaluación crediticia | underwriting | processus complet de décision et de conditions |
| Comité de crédit | comité de crédito | credit committee | groupe humain qui examine les dossiers non automatiques |
| Politique de crédit | política de crédito | credit policy | règles formelles d'éligibilité, montant, prix et exceptions |
| Exception | excepción | exception | décision hors règle, autorisée et documentée selon une procédure |
| KYC | conocimiento del cliente | KYC | identification et vérification du client |
| AML / PLD | PLD/FT | AML | prévention du blanchiment et du financement illicite |
| Mora | mora | delinquency | retard de paiement |
| Jours de retard | días de atraso | days past due | nombre de jours après l'échéance |
| Défaut | incumplimiento | default | événement défini par la politique indiquant une défaillance |
| NPL | cartera vencida / crédito improductivo | non-performing loan | prêt classé non performant selon une définition précise |
| PD | probabilidad de incumplimiento | probability of default | probabilité de défaut sur un horizon défini |
| LGD | pérdida dado incumplimiento | loss given default | part perdue après récupération |
| EAD | exposición al incumplimiento | exposure at default | montant exposé lors du défaut |
| Perte attendue | pérdida esperada | expected loss | PD × LGD × EAD |
| Cohorte | cohorte | cohort | groupe de prêts comparable |
| Vintage | cosecha / vintage | vintage | cohorte par période d'origination |
| Recouvrement | cobranza | collections | actions visant à obtenir les paiements dus |
| Récupération | recuperación | recovery | montant récupéré après retard ou défaut |
| Décaissement | desembolso | disbursement | envoi du montant du prêt |
| Rapprochement | conciliación | reconciliation | comparaison entre ledger interne, paiement et banque |
| Ledger | libro mayor / registro | ledger | journal structuré des mouvements et états |
| Idempotence | idempotencia | idempotency | une répétition du même événement ne crée pas un second effet |
| CLABE | CLABE | CLABE | identifiant bancaire mexicain à 18 chiffres |
| SPEI | SPEI | SPEI | infrastructure de transferts interbancaires au Mexique |
| STP | STP | STP | fournisseur/rail utilisé dans le prototype pour les transferts |
| POS / TPE | terminal punto de venta | point of sale | terminal ou canal d'acceptation de paiements |
| Settlement | liquidación | settlement | règlement des transactions vers le compte du commerçant |
| FMCG | consumo masivo | fast-moving consumer goods | produits de grande consommation et historique de réapprovisionnement |
| Taux d'approbation | tasa de aprobación | approval rate | demandes approuvées divisées par demandes évaluées |
| Taux d'acceptation | tasa de toma | take-up rate | offres acceptées divisées par offres émises |
| Coût d'acquisition | costo de adquisición | acquisition cost | coût pour obtenir un prêt décaissé |
| Unit economics | economía unitaria | unit economics | revenus et coûts complets par prêt/cohorte |
| Shadow pilot | piloto sombra | shadow pilot | Olin score en parallèle sans prendre la décision officielle |
| Gate | condición de avance | stage gate | condition obligatoire avant l'étape suivante |

---

# 12. Plan d'apprentissage du fondateur — 7 jours

Prévois 60 à 90 minutes par jour. Chaque journée se termine par un livrable, pas seulement par de la lecture.

## Jour 1 — La vérité produit

**À apprendre :** ce qu'Olin est, n'est pas, ce qui est mocké, le niveau de maturité.  
**Exercice :** récite les trois one-liners et explique les cinq vérités sans notes.  
**Livrable :** une page « working / partial / not live ».

## Jour 2 — La mécanique d'un crédit

**À apprendre :** principal, coût, CAT/APR, échéance, DSCR, burden ratio, défaut.  
**Exercice :** dessine le flux d'un montant décaissé jusqu'au remboursement complet.  
**Livrable :** explique en deux minutes pourquoi « 3 % par mois » n'est pas une description complète.

## Jour 3 — Risque et scorecard

**À apprendre :** C1–C4, D1–D3, S1–S3, Tiers 1–14, fraude, concentration.  
**Exercice :** prends cinq combinaisons et annonce tier, décision et raison.  
**Livrable :** présente la matrice sans confondre tier de score et graduation.

## Jour 4 — Opération, données et conformité

**À apprendre :** consentement, provenance, KYC/AML, décaissement, rapprochement, collections, résultat.  
**Exercice :** joue un incident « STP inconnu après demande de transfert ». La seule bonne réponse commence par bloquer et rapprocher.  
**Livrable :** la checklist avant premier live.

## Jour 5 — Réunion partenaire

**À apprendre :** script de 7 minutes, questions Monex, protocole shadow.  
**Exercice :** fais la démo avec un chronomètre et enregistre-toi.  
**Livrable :** un e-mail de suivi avec propriétaire, date et prochain pas.

## Jour 6 — Réunion investisseur

**À apprendre :** différence partenaire/investisseur, 10 slides, milestones et risques.  
**Exercice :** réponds aux dix objections de la section 9 en moins de 30 secondes chacune.  
**Livrable :** deck sans claim non sourcé et data room minimale.

## Jour 7 — Red team

Demande à une personne expérimentée de jouer un directeur risque sceptique.

Questions à subir :

- qui perd l'argent si le prêt fait défaut ?
- qui a légalement accordé le crédit ?
- pourquoi ces seuils ?
- comment prouves-tu le consentement ?
- que fais-tu si STP et ton ledger ne sont pas d'accord ?
- quelles données sont réelles ?
- quelle est ta perte observée ?
- pourquoi 30 prêts ?
- quelle condition arrête le pilote ?
- que veux-tu exactement de moi ?

**Livrable :** une liste de réponses faibles et les actions pour les rendre solides.

---

# 13. Fiche de réunion à imprimer

## Avant

- audience : partenaire, investisseur, conseil ou marchand ;
- objectif unique de la réunion ;
- ask en une phrase ;
- démo testée sans dépendance imprévisible ;
- trois claims vérifiés ;
- trois limites que tu es prêt à dire ouvertement ;
- questions prioritaires ;
- personne qui prendra les notes.

## Pendant

- demande le rôle et les priorités des personnes présentes ;
- donne la phrase Olin ;
- pose le problème sans exagération ;
- montre un dossier, une décision et un résultat ;
- distingue actuel, shadow pilot et roadmap ;
- pose les questions métier avant de parler intégration ;
- reformule ce que tu as compris ;
- demande un propriétaire et une date.

## Après

- envoie un résumé en moins de 24 heures ;
- sépare faits, décisions, questions et actions ;
- ne transforme pas une réunion positive en « partenariat » ;
- mets à jour le registre des hypothèses ;
- ajoute toute promesse au backlog avec un responsable.

## Formule de conclusion

**Espagnol**

> Para confirmar que entendí bien: el siguiente paso no es una integración ni un compromiso de crédito. Es una sesión con riesgo, datos y operación para definir el protocolo, y tú nos ayudarías a identificar a las personas correctas. ¿Es correcto? ¿Podemos salir hoy con un responsable y una fecha tentativa?

**English**

> To make sure I understood correctly: the next step is not an integration or a lending commitment. It is a session with risk, data and operations to define the protocol, and you would help us identify the right people. Is that correct? Can we leave today with an owner and a tentative date?

---

# 14. Sources internes utilisées

Ce guide s'appuie sur l'état du dépôt et notamment :

- [`README.md`](../README.md) — positionnement, modes et limites générales ;
- [`olin/scorecard.py`](../olin/scorecard.py) — bandes, poids, matrice et garde-fous ;
- [`olin/repayment.py`](../olin/repayment.py) — DSCR, charge, stress et capacité ;
- [`olin/models.py`](../olin/models.py) — structures de données et provenance ;
- [`olin/store.py`](../olin/store.py) — audit, consentement, décisions, paiements et outcomes ;
- [`olin/server.py`](../olin/server.py) — interface analyste, approbation et décaissement ;
- [`olin/stp.py`](../olin/stp.py) — validation CLABE et rail de paiement ;
- [`olin/collection.py`](../olin/collection.py) — échéances, paiements et retards ;
- [`olin/portfolio.py`](../olin/portfolio.py) — concentration et santé du portefeuille ;
- [`olin/graduation.py`](../olin/graduation.py) — hypothèses de graduation ;
- [`PILOT_RUNBOOK.md`](../PILOT_RUNBOOK.md) — règles opérationnelles du pilote ;
- [`ADVERSARIAL_REVIEW.md`](../ADVERSARIAL_REVIEW.md) — risques et conditions de blocage ;
- [`CODEX_HANDOFF_FOR_CLAUDE.md`](../CODEX_HANDOFF_FOR_CLAUDE.md) — inventaire et statut des tests au 14 juillet 2026.

---

## La phrase finale à retenir

> Olin n'a pas besoin de prétendre être déjà une fintech de crédit complète. Sa meilleure histoire aujourd'hui est plus crédible : un prototype explicable qui sait transformer des preuves opérationnelles en recommandation, enregistrer la décision et suivre le résultat — et qui cherche maintenant le bon partenaire pour tester cette boucle proprement, avant de déplacer de l'argent à grande échelle.
