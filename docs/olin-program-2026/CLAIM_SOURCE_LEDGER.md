# Claim–source ledger

**Checked:** 27 August 2026

| Claim used in the program | Source | Strength / limitation |
|---|---|---|
| The current private-sector data law defines consent as free, specific and informed; the privacy notice may be electronic. | [Cámara de Diputados — LFPDPPP, reform 14 Nov 2025](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf) | Primary law; exact application needs counsel. |
| Express authorization is required for credit-report queries for natural persons and certain legal persons, with special-section/signature requirements. | [Cámara de Diputados — LRSIC, reform 24 Jan 2024](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRSIC.pdf) | Primary law; Círculo and partner must approve operational form. |
| Mexican commercial message preservation can use NOM-151 conservation evidence. | [DOF — NOM-151-SCFI-2016](https://dof.gob.mx/nota_detalle.php?codigo=5478024&fecha=30/03/2017) | Primary standard; necessity depends on document and counsel. |
| Financial institutions register customer adhesion contracts in RECA; registration does not always mean prior substantive approval. | [CONDUSEF — RECA](https://registros.condusef.gob.mx/reca/) | Primary regulator registry. |
| Círculo production onboarding requests affiliation details and security-test evidence. | [Círculo API Hub — production path](https://developer.circulodecredito.com.mx/pase_a_produccion) | Provider source; commercial terms still unknown. |
| DENUE provides identification, location, activity and size data for more than six million establishments; it does not provide cash flow. | [INEGI — DENUE](https://www.inegi.org.mx/app/mapa/denue/default.aspx) and [API](https://www.inegi.org.mx/servicios/api_denue.html) | Primary public data source; inferential limitation stated by Olin. |
| Syncfy markets read-only bank/fiscal data, a consented widget, synchronization and notifications. | [Syncfy — Open Finance](https://syncfy.com/es/) | First-party vendor claim; verify security and coverage contractually. |
| ENAFIN 2024 covers financing needs and barriers among firms with six or more workers; its individual microdata is restricted. | [INEGI — ENAFIN 2024](https://www.inegi.org.mx/programas/enafin/2024/) and [microdata policy](https://www.inegi.org.mx/rnm/index.php/catalog/1106) | Primary statistics; not an underwriting dataset for Olin. |
| Mexico’s 2025–2030 inclusion policy cites high prices, requirements, inaccessible terms and procedural complexity as financing barriers. | [CNBV — PNIF 2025–2030](https://www.cnbv.gob.mx/Inclusi%C3%B3n/Documents/PNIF_2025_2030_Version_Accesible.pdf) | Primary policy document; population and measures must be read in context. |
| Mifiel publishes e-signature/NOM-151 functionality and pricing, including optional biometric verification. | [Mifiel pricing PDF](https://guia.mifiel.com/hubfs/Pricing/Mifiel%20Precios.pdf) | Vendor source, useful for shortlist only; legal sufficiency not independently established here. |
| Public credit datasets such as UCI’s card-default dataset can test pipelines but are not Mexican SME validation data. | [UCI Default of Credit Card Clients](https://archive.ics.uci.edu/dataset/350/default%2Bof%2Bcredit%2Bcard%2Bclients) | Authoritative repository; different country, product and population. |
| A public longitudinal Mexico City micro-business dataset derives from DENUE and can test geo/data engineering, not credit performance. | [GitHub research repository](https://github.com/ckelling/micro_business_mexico_city) | Public research code/data; no repayment labels. |
| Syncfy publishes sample integrations and widget/webhook code. | [Paybook/Syncfy code samples](https://github.com/Paybook/sync-code-samples) | Useful engineering reference; review versions and security before use. |

## Known evidence gaps

- Comparable enterprise decisioning vendors do not expose sufficiently similar
  Mexico bank contract prices publicly. Olin pricing is therefore a hypothesis
  range, not a market-price claim.
- No public dataset found combines Mexican micro-business alternative evidence
  with lender decisions and mature repayment outcomes at individual-case level.
- Provider marketing claims do not replace Olin's vendor due diligence, DPA,
  penetration evidence, SLA, data-location review, or bank approval.
