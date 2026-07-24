# Olin — rapport complet de modifications pour revue par Claude

Date de vérification : 14 juillet 2026  
Dossier analysé : `/Users/pc/Downloads/olin_scoring_mvp_1`  
Archive de référence : `/Users/pc/Downloads/olin_scoring_mvp_1.zip`

## 1. Limite importante sur l'historique

Le dossier actuel ne contient pas de dépôt Git. Il n'existe donc ni commits, ni
auteurs, ni historique permettant d'attribuer chaque ligne à Codex, Claude ou
une intervention humaine.

Ce rapport distingue deux choses vérifiables :

1. la différence entre l'archive originale du 25 juin et le dossier actuel ;
2. les dernières modifications de documentation réalisées par Codex le 14 juillet.

Il ne faut pas présenter toutes les différences comme ayant nécessairement été
écrites par Codex. La seule attribution certaine pour la dernière intervention
est donnée dans la section 10.

## 2. Point de départ vérifié

L'archive originale contient seulement huit entrées :

- `README.md`
- `olin/__init__.py`
- `olin/demo.py`
- `olin/signals.py`
- `olin/models.py`
- `olin/store.py`
- `olin/scorecard.py`
- le dossier `olin/`

Parmi ces fichiers d'origine :

- `olin/demo.py` et `olin/__init__.py` sont toujours identiques à l'archive ;
- `README.md`, `olin/models.py`, `olin/signals.py`, `olin/store.py` et
  `olin/scorecard.py` ont été modifiés ;
- tous les autres modules, interfaces, tests, documents et sites listés
  ci-dessous ont été ajoutés après cette archive.

## 3. Modèle de décision et scorecard

### `olin/scorecard.py` — réécriture majeure

- Remplacement de l'ancienne logique de bureau par Círculo de Crédito.
- Ajout des bandes :
  - C1 : score au moins égal à 670 ;
  - C2 : score de 600 à 669 ;
  - C3 : aucun dossier/score disponible ;
  - C4 : score inférieur à 600 ou retard actif.
- Ajout des bandes DSCR :
  - D1 : DSCR au moins égal à 2,5 sans signal de dégradation ;
  - D2 : DSCR de 1,5 à 2,49 ou présence d'un signal prudentiel ;
  - D3 : DSCR inférieur à 1,5, indisponible ou échec dur de remboursement.
- Ajout des bandes de score interne :
  - S1 : 75 ou plus ;
  - S2 : de 50 à 74,99 ;
  - S3 : moins de 50.
- Ajout de la matrice de tiers :
  - Tier 1 : seule voie `AUTO_APPROVE` ;
  - Tiers 2 à 12 : `COMMITTEE` ;
  - Tier 13 : refus lié au bureau, au DSCR ou au score interne ;
  - Tier 14 : blocage avant score pour fraude, portefeuille ou provenance.
- Les 36 combinaisons Círculo × DSCR × score interne sont résolues.
- Ajout de règles de repli : données insuffisantes, fraude élevée, filtres de
  phase 0 ou intervalle d'incertitude peuvent renvoyer un Tier 1 au comité.
- Ajout de pondérations par type de commerce.
- Ajout d'un intervalle de confiance par bootstrap.
- Ajout d'une analyse de sensibilité indiquant ce qu'il faudrait améliorer pour
  changer de bande.
- Ajout d'une contre-proposition de montant lorsque la capacité de remboursement
  ne permet pas le montant demandé.
- Ajout d'un coût fixe calculé sur deux mois et prise en charge d'un taux de
  graduation pour les emprunteurs récurrents.
- En production, les données bancaires ou FMCG synthétiques et non vérifiées
  sont désormais bloquées.
- Un refus moteur produit un montant approuvé égal à zéro.

### `olin/repayment.py` — nouveau

- Couche de capacité de remboursement distincte du score de qualité.
- Calcule DSCR, charge de paiement, revenu net estimé, coussin de stress,
  régularité des dépôts et tendance du solde.
- Applique des refus durs et des dégradations vers comité.
- Peut proposer le montant maximal compatible avec le seuil DSCR.

### `olin/signals.py` — modifié

- Adaptation du signal bancaire aux nouveaux champs de flux.
- Seules les sources directes `belvo` et `syncfy` obtiennent la confiance pleine.
- Les sources manuelles ou synthétiques ne sont pas traitées comme des APIs
  vérifiées.

### `olin/models.py` — étendu

- Ajout de `COMMITTEE` tout en conservant `MANUAL_REVIEW` pour compatibilité.
- Ajout de provenance, vérification et date d'observation aux données FMCG.
- Ajout des volumes d'entrées/sorties, solde minimum, provenance et vérification
  aux données bancaires.
- Ajout ou extension des structures pour fraude, bureau, remboursement,
  résultat de score, décaissement, graduation et blocage portefeuille.
- Ajout du score numérique Círculo dans `BuroData`.
- Ajout d'identité, CLABE, données de fraude et autres informations de dossier
  dans `Application`.

## 4. Contrôles de risque et sécurité du pilote

### `olin/fraud.py` — nouveau

- Vérification du format téléphone mexicain, RFC et CURP.
- Cohérence de l'adresse et de la banque détectée par la CLABE.
- Contrôle manuel INE.
- Séparation entre blocages durs et avertissements analyste.

### `olin/portfolio.py` — nouveau

- Bloque deux prêts actifs sur la même CLABE.
- Surveille concentration par colonia, exposition locale et concentration par
  type de commerce.
- Peut bloquer l'auto-approbation si le taux de défaut du portefeuille dépasse
  le seuil prévu.
- En production, une erreur de lecture du portefeuille échoue en mode fermé.

### `olin/config.py` — nouveau

- Ajout des modes `demo`, `production` et `test`.
- Séparation des bases demo et production.
- Identification des sources synthétiques.
- Gestion des secrets analyste et webhook via variables d'environnement.

### `olin/stp.py` — nouveau

- Validation de la CLABE, y compris contrôle de checksum.
- Connecteur de décaissement STP/SPEI.
- Séparation stricte sandbox/production.
- Vérification des paramètres d'environnement avant mouvement d'argent.

### Contrôles encore manquants

Le fichier `ADVERSARIAL_REVIEW.md` conclut que le système doit rester bloqué
pour le crédit live autonome. Les cinq blocages principaux sont :

1. décaissement non transactionnel et pas complètement idempotent en cas de
   crash entre l'acceptation STP et l'écriture SQLite ;
2. authentification partagée, sans utilisateurs nommés, rôles ni double contrôle ;
3. données d'identité et financières non chiffrées dans SQLite et les backups ;
4. absence d'un artefact complet de consentement Círculo ;
5. rotation nécessaire des identifiants de connecteurs déjà utilisés localement.

Autres limites : absence de rapprochement STP autoritatif, absence d'alertes
durables, TLS non intégré, limites globales de ticket non indépendantes de la
scorecard, stratégie SQLite à clarifier et lien de démonstration public encore
dirigé vers localhost.

## 5. Connecteurs et données alternatives

### `olin/bank_mock.py` — nouveau

- Profils bancaires déterministes `healthy`, `adequate`, `stressed` et
  `cash_only`.
- Les données portent explicitement `source="mock_sandbox"` et
  `verified=False`.

### `olin/fmcg_mock.py` — nouveau

- Profils FMCG déterministes `strong`, `regular` et `weak`.
- Les données sont explicitement synthétiques et non vérifiées.

### `olin/buro_mock.py` — nouveau

- Profils Círculo C1, C2, multi-crédit, délinquant et sans dossier.
- Affectation déterministe pour les démonstrations et les tests.

### `olin/syncfy.py` — nouveau

- Création utilisateur/session/credentials, polling et récupération des comptes
  et transactions Syncfy.
- Transformation des transactions en `BankData`.
- Le connecteur existe, mais le forfait testé a renvoyé une limitation 402 lors
  de la synchronisation des credentials.

### `olin/belvo.py` — nouveau

- Pipeline alternatif de connexion, récupération de comptes/transactions et
  transformation en `BankData`.
- Couvert par un test local simulé ; cela ne signifie pas qu'une intégration
  bancaire de production est active.

### `olin/places.py` — nouveau

- Recherche Google Places, détails, avis, rating, ancienneté estimée, vélocité
  des avis et cohérence d'adresse.

### `olin/imss.py` — nouveau

- Validation du RFC et structure de récupération des informations IMSS.
- Une partie reste une intégration de démonstration/fallback et ne doit pas être
  considérée comme un signal live sans vérification.

## 6. Cycle complet du prêt et stockage

### `olin/store.py` — extension majeure

- Migration progressive du schéma SQLite.
- Ajout du score Círculo, tier, coût, environnement demo/production, CLABE,
  décision analyste et justification.
- Ajout de l'état de décaissement, folio STP et référence de recouvrement.
- Ajout d'un ledger de paiements avec `event_id` unique.
- Paiements partiels, doublons et trop-perçus traités explicitement.
- États de résultat : non décaissé, actif, payé à temps, payé en retard,
  défaut et défaut récupéré.
- Export d'entraînement limité aux dossiers production décaissés avec résultat
  final.
- Ajout de vues portefeuille, prêts actifs et historique par CLABE.
- Correction de l'ancien `INSERT OR REPLACE` : un doublon ne peut plus effacer
  l'historique de décaissement ou de remboursement.
- Un analyste ne peut pas transformer un refus moteur en approbation.
- Ajout d'une réservation atomique avant appel STP avec finalisation ou rollback
  pour bloquer les décaissements ordinaires en double.
- Ajout du timestamp, du canal et du texte du consentement Círculo.

### `olin/collection.py` — nouveau

- Création de références de paiement et calendrier en deux échéances.
- Rapprochement d'un paiement entrant avec le ledger.
- Idempotence par identifiant d'événement.
- Détection des échéances en retard et passage en défaut.

### `olin/graduation.py` — nouveau

- Offre progressive pour emprunteur récurrent selon historique de paiement.
- Plafond et taux adaptés, avec bonus de remboursement anticipé.

### `jobs/daily.py` — nouveau

- Tâche quotidienne : défaut à J+75, détection des retards et snapshot du
  portefeuille.
- Peut fonctionner en mode simulation.
- Les alertes utilisent SMTP lorsque `OLIN_ALERT_EMAIL` est configuré et sont
  sinon écrites avec timestamp dans `logs/alerts.log`.
- L'acquittement, le retry et l'escalade restent à mettre en place.

### `olin/calibration.py` — nouveau

- Chargement des résultats finaux utilisables.
- Rapport de tiers et outils exploratoires de calibration.
- Trente prêts sont suffisants pour apprendre sur l'opération, pas pour valider
  un modèle ML de production.

### `olin/batch.py` — nouveau

- Scoring CSV en lot pour pré-qualification et export des résultats.

## 7. Interfaces construites

### `onboard.py` — nouveau

- Simulateur conversationnel de type WhatsApp dans le terminal.
- Collecte l'identité, l'activité, le montant, la CLABE et le bureau.
- Essaie les connecteurs disponibles et utilise les mocks uniquement en mode
  autorisé.
- Lance les contrôles portefeuille, fraude, remboursement et scorecard.
- Enregistre le résultat dans SQLite.

### `olin/server.py` — nouveau

- Interface analyste et API HTTP dans un seul module.
- Liste des dossiers, détails des signaux, tiers, raisons et portefeuille.
- Actions analyste : approbation, refus, note, décaissement et suivi des paiements.
- Authentification par token en production et vérification du secret webhook.
- Refus de démarrer avec un mélange dangereux entre base demo et mode production.
- `--seed-demo` est explicite ; un démarrage normal ne crée plus automatiquement
  de faux dossiers.
- En production, l'approbation analyste est bloquée si le consentement Círculo
  n'est pas enregistré ; en démo l'interface affiche un avertissement.

### `website/index.html`, `website/styles.css`, `website/app.js` — nouveaux

- Site public responsive en espagnol refondu autour d'un dossier de décision
  interactif, d'un pilote sombra et d'un état construit/requis/futur.
- Nouveau symbole Olin, motion finie, menu clavier/mobile, focus visible et
  préférence de mouvement réduit.
- Le lien du démonstrateur lit `OLIN_DEMO_URL` depuis `website/config.js`; la
  valeur locale doit être remplacée par un URL authentifié avant publication.
- Nouvelles captures de contrôle desktop, mobile et console de décision.

## 8. Tests ajoutés et statut réel au 14 juillet 2026

### `test_pilot_safety.py`

Commande exécutée : `python3 -m unittest -v test_pilot_safety`  
Résultat : **13 tests réussis, 0 échec**.

Couverture : 36 combinaisons de matrice, limites Círculo/DSCR/score, checksum
CLABE, rejet des mocks en production, non-écrasement de l'historique, refus non
modifiable, paiements partiels/doublons, trop-perçu, retards, consentement,
alertes durables et séparation des rails demo/production. Des `ResourceWarning`
signalent encore des connexions SQLite non fermées pendant un test.

### `test_full_flow.py`

Commande exécutée : `python3 test_full_flow.py`  
Résultat : **toutes les assertions réussies**.

Flux couvert : score → enregistrement → décaissement simulé → deux paiements →
résultat payé à temps → tâche quotidienne → offre graduée pour le second prêt.

### `test_belvo_pipeline.py`

Commande exécutée : `python3 test_belvo_pipeline.py`  
Résultat : **assertions réussies**.

Le test utilise des réponses Belvo simulées. Il valide la transformation vers
`BankData` et la scorecard, pas une connexion live en production.

### `olin/test_v2.py`

Commande exécutée : `python3 -m olin.test_v2`  
Résultat : **toutes les assertions réussies**.

Couverture : cinq scénarios métier, Tiers 1 à 12, refus Tier 13, cas multi-prêts,
absence de données bancaires, graduation, limites de score et sensibilité.

### Remarque sur pytest

`python3 -m pytest -q` n'a pas pu être exécuté car `pytest` n'est pas installé
dans le Python système. Les quatre suites prévues par le README ont cependant
été lancées directement et ont toutes réussi.

## 9. Documentation opérationnelle ajoutée

### `PILOT_RUNBOOK.md`

- Règle de cohorte limitée à 30 abarrotes.
- Checklist avant le premier prêt et checklist par dossier.
- Exploitation quotidienne, données de résultat obligatoires et conditions
  d'arrêt du pilote.
- Toute approbation demande une décision et une justification humaines.

### `ADVERSARIAL_REVIEW.md`

- Revue critique de la scorecard, du stockage, des APIs, de STP, du recouvrement,
  de la calibration et du site.
- Verdict documenté : prêt pour démonstration ou shadow pilot partenaire, mais
  bloqué pour le crédit live autonome.

### `README.md`

- Documentation du nouveau modèle, des modes de sécurité, des commandes de
  lancement, des tests et des prérequis de production.

### `.env.example` et `.gitignore`

- Exemple de configuration sans secrets.
- Exclusion des `.env`, bases SQLite, backups et caches.
- Le vrai fichier `.env` existe localement et ne doit pas être transmis ou
  copié dans une revue. Les credentials utilisés auparavant doivent être
  considérés comme potentiellement exposés et renouvelés.

## 10. Dernière intervention Codex certaine : document Monex

Lors de la dernière demande, Codex n'a pas modifié le moteur de crédit, la base,
les tests, le serveur ou le site. Les changements certains ont été limités à :

- création/modification de `tmp/documents/build_monex_brief.py` ;
- génération de `output/docx/Olin_Propuesta_Piloto_Monex.docx` ;
- génération de `output/pdf/Olin_Propuesta_Piloto_Monex.pdf` ;
- génération de `output/docx/Olin_Presentacion_Empresa_Monex.docx` ;
- génération de `output/pdf/Olin_Presentacion_Empresa_Monex.pdf` ;
- rendus temporaires de contrôle dans `tmp/documents/`.

La présentation finale a été corrigée pour :

- présenter Olin, le problème, le produit, le fonctionnement et l'état réel de
  l'entreprise sur la première page ;
- présenter ensuite un pilote exploratoire Monex avec 10 abarrotes ;
- ne pas affirmer que Monex fournit déjà un POS, finance déjà les prêts ou a
  accepté une intégration ;
- présenter ces éléments comme des questions à confirmer en réunion ;
- indiquer que l'entreprise et les contrôles juridiques/compliance doivent être
  finalisés avant tout prêt réel.

Le DOCX final a été rendu visuellement en deux pages et audité : zéro problème
d'accessibilité de niveau élevé, moyen ou faible détecté par l'outil utilisé.

## 11. Fichiers temporaires et données à ne pas confondre avec le produit

- `tmp/documents/company_render_v1` à `company_render_v4` : itérations de rendu
  de la présentation, dont certaines versions intermédiaires sur trois pages.
- `tmp/documents/rendered*` : rendus de l'ancienne proposition Monex.
- `website/*.png` : captures de vérification visuelle.
- `olin_scoring.db` : base locale de démonstration, pas une base de production.
- `backups/olin_scoring.pre_pilot_safety_2026-07-13.db` : sauvegarde locale avant
  les contrôles de sécurité ; elle contient potentiellement des données de demo
  et ne doit pas être publiée.

## 12. Questions précises à demander à Claude

Claude doit effectuer une revue indépendante, sans supposer que les tests
prouvent la sécurité de production :

1. comparer le dossier actuel à `olin_scoring_mvp_1.zip` ;
2. vérifier la matrice complète et toutes les limites exactes ;
3. chercher les chemins permettant un double décaissement ou un paiement mal
   rapproché ;
4. vérifier la séparation demo/production et tout fail-open ;
5. revoir les migrations SQLite et la qualité des données d'entraînement ;
6. vérifier que tout prêt décaissé possède consentement, preuves, acteur,
   justification et résultat final traçables ;
7. confirmer ou contester les cinq blocages de `ADVERSARIAL_REVIEW.md` ;
8. produire une liste P0/P1/P2 sans modifier les fichiers ;
9. ne lire ni reproduire les valeurs du fichier `.env` ;
10. distinguer clairement « démonstration fonctionnelle », « shadow pilot » et
    « système autorisé à déplacer de l'argent réel ».

## 13. Conclusion honnête

Olin est beaucoup plus avancé que l'archive initiale : le dossier contient un
moteur explicable, un cycle de prêt simulé complet, une interface analyste, un
site public, des connecteurs, des contrôles de pilote et plusieurs suites de
tests. Cela représente aussi une augmentation importante de surface et de
complexité.

Le système est démontrable et peut servir à un shadow pilot contrôlé. Il ne doit
pas encore être décrit comme une plateforme de crédit live sûre. La réservation
avant décaissement et le consentement minimal sont maintenant en place, mais les
états STP ambigus, l'identité des acteurs, le double contrôle, le chiffrement,
la preuve complète de consentement et le rapprochement autoritatif doivent être
fermés avant de déplacer de l'argent réel.
