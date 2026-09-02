# Olin: plan de mise en état pour lundi 10 août 2026

## Résultat à montrer lundi

Un analyste crée un dossier pour un commerçant réel et consentant, rattache des
preuves autorisées, vérifie l'établissement via Google Places, obtient une
recommandation explicable, prend une décision de partenaire et exporte le
résultat. Le dossier est en mode pilote sans décaissement. Aucun mouvement
d'argent et aucune promesse de crédit ne sont possibles dans ce parcours.

Ce résultat est un MVP de décision utilisable pour un pilote. Ce n'est pas
encore une plateforme de prêt en production.

## Les six couches de preuve

| Couche | État visé lundi | Preuve minimale | Ne doit jamais être inventé |
|---|---|---|---|
| Identité et consentement | Vérifié | INE contrôlée, RFC, texte/canal/date du consentement | Identité validée sans pièce |
| Círculo de Crédito | Disponible ou vérifié | Réponse réelle et référence du fournisseur | Score saisi comme s'il venait de Círculo |
| Flux bancaire | Disponible ou vérifié | Relevé autorisé ou référence d'agrégateur | Profil mock renommé “réel” |
| TPV et liquidations | Disponible ou vérifié | Export du processeur et référence récupérable | Volume déclaré seul marqué vérifié |
| Achats fournisseurs | Disponible ou vérifié | Factures, relevé distributeur ou référence | Cadence simulée |
| Présence et continuité géographique | Disponible ou vérifié | Google Place ID + adresse cohérente; ensuite DENUE | Ancienneté déduite du nombre d'avis |

Les couches mesurent la qualité des preuves. Elles ne créent pas six nouveaux
poids de score et ne garantissent pas le remboursement.

## Checklist vendredi à lundi

### Vendredi 7 août

- [x] Remplacer l'entrée “synthetic” par la création d'un dossier à preuves réelles.
- [x] Ajouter les six couches dans l'API et la console analyste.
- [x] Ajouter la recherche Google Places côté serveur sans exposer la clé.
- [x] Ne conserver de Google que le Place ID et la provenance autorisée.
- [x] Bloquer la validation géographique en cas d'adresse incohérente.
- [x] Tester authentification, consentement, preuves, décision, outcome et blocage du décaissement.
- [ ] Choisir un seul commerçant réel avec autorisation explicite pour la répétition.
- [ ] Lui demander uniquement les documents nécessaires à ce dossier pilote.

### Samedi 8 août

- [ ] Créer le dossier réel dans `/nuevo` avec un identifiant partenaire.
- [ ] Enregistrer le consentement exact, son canal et sa date.
- [ ] Ajouter une référence récupérable pour chaque source réellement fournie.
- [ ] Laisser les couches absentes en `missing`; ne pas les maquiller.
- [ ] Vérifier manuellement que le résultat Google correspond au nom, au numéro et à l'adresse.
- [ ] Capturer le parcours de cinq minutes sans afficher de donnée personnelle.
- [ ] Faire relire le dossier par José comme contrôleur crédit, pas comme approbateur légal.

### Dimanche 9 août

- [ ] Rejouer le parcours depuis un navigateur privé avec les rôles partner et analyst.
- [ ] Tester les cas : consentement absent, référence absente, mauvaise adresse, double clic, dossier incomplet.
- [ ] Préparer un export anonymisé du dossier.
- [ ] Préparer une page de limites : intégrations contractuelles manquantes, aucune validation statistique, aucun décaissement.
- [ ] Sauvegarder une copie locale de la base pilote et vérifier qu'elle n'est pas publiée.

### Lundi 10 août

- [ ] Démonstration en direct : intake, preuves, six couches, recommandation, revue analyste, outcome.
- [ ] Demander à l'investisseur une due-diligence produit de 30 minutes et ses conditions écrites.
- [ ] Demander au partenaire de données un pilote de 10 dossiers anonymisés avec critères de succès.
- [ ] Envoyer les cinq prises de contact prioritaires ci-dessous.

## Critères d'acceptation du MVP

- Le commerçant a réellement consenti à l'analyse.
- Chaque donnée “verified” possède une source et une référence récupérable.
- Les données manquantes restent visibles et peuvent bloquer la recommandation.
- Le score affiche raisons, couverture, intervalle de confiance et route de décision.
- La décision partenaire est distincte de la recommandation Olin.
- Le dossier pilote ne peut pas déclencher un décaissement.
- Les données personnelles ne sont pas exposées sur le site public ou dans la vidéo.
- Un export anonymisé permet de comparer Olin et la décision du partenaire.

## Démarrage du mode pilote

Définir `OLIN_MODE=pilot`, un secret analyste distinct et les rôles API avant
de démarrer le serveur. Ce mode utilise `olin_pilot.db`, interdit les mocks et
ne peut jamais activer les rails de décaissement, même si le switch de prêt est
positionné par erreur.

## Cibles prioritaires

| Priorité | Cible | Pourquoi maintenant | Demande précise |
|---|---|---|---|
| 1 | Trust-Tech Fund / Francisco Junco | Thèse exacte: données alternatives et cycle du crédit au Mexique | Revue MVP + accès pilote Círculo + critères d'investissement |
| 2 | Finnovista / Fermín Bueno | Réseau fintech, banques, accélération et investisseurs | Introduction à 2 prêteurs pour shadow pilot |
| 3 | 500 Global LatAm / Santiago Zavala | Pré-seed au Mexique, ticket annoncé de 300 kUSD | Office hour et retour sur les preuves nécessaires avant candidature |
| 4 | Accion Ventures | Inclusion financière, financement MSME, early stage | Revue du protocole de validation et fit d'investissement |
| 5 | FinTech México | Accès à l'écosystème réglementaire, prêteurs et fournisseurs | Deux introductions: responsable crédit et responsable data |

Ensuite: QED Investors, ADN.vc, GAIN, YC, Decelera et les business angels déjà
connus de Brice. Une candidature de fonds ne doit pas remplacer le pilote réel.

## Messages courts

### Trust-Tech / Círculo

Hola, estoy construyendo Olin, una capa de decisión para crédito a pequeños
negocios en México. Ya tenemos un flujo funcional que reúne consentimiento,
evidencia bancaria/TPV/proveedores y verificación geográfica en un expediente
auditable. Por su tesis en datos alternativos y operaciones crediticias, me
gustaría mostrarles un caso real en piloto sin desembolso y entender qué haría
falta para evaluar una integración con Círculo. ¿Tendrían 20 minutos la próxima
semana?

### Finnovista

Hola Fermín, estoy construyendo Olin, infraestructura de decisión para que un
originador evalúe pequeños negocios con evidencia operativa y una ruta
explicable. El MVP ya procesa un expediente real sin mover dinero; el siguiente
hito es un shadow pilot de 10 casos con una institución. ¿Podría mostrarte el
flujo en 20 minutos y pedirte feedback sobre los dos originadores con mejor fit?

### Expert crédit à recruter comme advisor

Hola, estoy preparando un piloto de Olin, una plataforma de decisión para
crédito a pequeños negocios. Busco a alguien que haya liderado riesgo de crédito
en México para revisar 10 expedientes, política y métricas una vez por semana.
No te escribo para venderte software: quiero saber si el protocolo aguanta una
revisión profesional. ¿Tendrías 20 minutos para verlo?

## Profils à approcher sur LinkedIn ou X

- Fractional Head of Credit Risk ayant travaillé chez Konfío, Covalto, Kueski,
  Clip, Creze ou un prêteur SME mexicain.
- Responsable PLD/AML ayant opéré une SOFOM, une banque ou une fintech de crédit.
- Backend/security engineer senior pour authentification, chiffrement, secrets,
  audit et migration SQLite vers Postgres.
- Data partnerships lead avec expérience TPV, open finance, bureau ou fraude.

Requêtes de recherche:

- `("credit risk" OR underwriting) (Konfío OR Covalto OR Kueski) México`
- `(PLD OR AML) (SOFOM OR fintech) México`
- `("open finance" OR "data partnerships") México fintech`

Commencer par demander une revue de 20 minutes. Ne pas proposer un poste avant
d'avoir validé la disponibilité, l'absence de conflit et le besoin.

## Geo-intelligence: prochaine couche

Google Places sert à vérifier en direct l'existence, le statut et la cohérence
de l'adresse. Seul le Place ID est conservé; la note, les avis et l'adresse sont
affichés en direct conformément aux règles Google.

DENUE doit devenir la source persistante: identifiant établissement, activité,
taille, adresse et coordonnées. L'intégration nécessite un token INEGI. Ensuite,
on pourra calculer des variables explicables et non discriminatoires: densité de
commerces comparables, stabilité apparente du point de vente, distance entre
adresse déclarée et registre, et concentration locale. Ces variables doivent
rester des éléments de revue jusqu'à validation sur des outcomes réels.

À ne pas utiliser: niveau de richesse supposé du quartier, démographie sensible,
criminalité comme proxy individuel ou toute donnée qui produirait une
discrimination géographique non contrôlée.

## Liens officiels

- Trust-Tech Fund: https://www.trust-tech.fund/
- Francisco Junco, Trust-Tech Fund Lead: rechercher ce titre exact sur LinkedIn
- Finnovista: https://www.finnovista.com/
- Fermín Bueno: https://es.linkedin.com/in/ferminbueno
- 500 Global LatAm: https://latam.500.co/latam
- Santiago Zavala: https://mx.linkedin.com/in/santiago-zavala-47a68b7
- Accion: https://www.accion.org/how-we-work/investment-strategies/
- QED / Fernando Gonzalez: https://www.qedinvestors.com/team/fernando-gonzalez
- FinTech México: https://www.fintechmexico.org/
- INEGI DENUE API: https://www.inegi.org.mx/servicios/api_denue.html
- Google Place IDs: https://developers.google.com/maps/documentation/places/web-service/place-id
- Google Places policies: https://developers.google.com/maps/documentation/places/web-service/policies
