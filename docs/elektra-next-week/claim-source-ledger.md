# Claim-to-source ledger

| ID | Claim | Source | Use / limitation |
|---|---|---|---|
| C01 | Grupo Elektra operates an integrated retail and financial-services model with more than 4,800 contact points in Mexico. | [Grupo Elektra — Nosotros](https://www.grupoelektra.com.mx/es/nosotros) | Establishes public business context; does not establish an Olin need. |
| C02 | Grupo Elektra reported 28.3 million digital customers in Q1 2026 and described a consistent credit-origination focus across physical and digital channels. | [Q1 2026 presentation](https://www.grupoelektra.com.mx/Documents/ES/Downloads/Grupo_Elektra_1T26_Espa%C3%B1ol.pdf) | Supports integration hypothesis; point-in-time public disclosure. |
| C03 | Elektra markets business-use products under Mi Negocio. | [Elektra Mi Negocio](https://www.elektra.mx/mi-negocio) | Supports the proposed equipment journey; cohort must be verified internally. |
| C04 | Préstamo Elektra is Banco Azteca Credimax. | [Préstamo Elektra](https://www.elektra.mx/prestamo-elektra) | Supports decision-system separation between Elektra journey and Banco Azteca credit. |
| C05 | Internal credit models must support the credit process and materially differentiate risk using borrower and transaction information. | [CNBV Anexo 15](https://www.cnbv.gob.mx/Anexos/Anexo%2015%20CUB.pdf) | Governance baseline; applicability and current bank interpretation require counsel/compliance review. |
| C06 | A model or external dataset must demonstrate predictive ability for the relevant borrowers and operations. | [DOF](https://dof.gob.mx/nota_detalle_popup.php?codigo=5138193), [Basel vendor-model guidance](https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/cri/30) | Supports prohibition on treating synthetic/public data as Elektra validation. |
| C07 | Validation should cover conceptual soundness, inputs, design and ongoing outcome performance, with independent review. | [Federal Reserve 2026 guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm), [Basel ECL validation](https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/pap/20) | International good practice; Elektra's binding internal model-risk policy controls. |
| C08 | Calibration requires evaluating predicted probabilities against observed frequencies; Brier/log-loss need careful interpretation. | [scikit-learn calibration documentation](https://scikit-learn.org/stable/modules/calibration.html) | Technical evaluation reference, not a regulatory source. |
| C09 | Mexican private-sector personal-data processing must be lawful, informed and controlled. | [LFPDPPP](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf) | Current-law source; exact roles/wording require qualified Mexican counsel. |
| C10 | A credit bureau report is shared with an institution only with the relevant authorization. | [Círculo de Crédito guide](https://www.circulodecredito.com.mx/b/guia-de-mi-reporte-de-credito-especial) | Product guidance; contractual and legal implementation needs formal review. |
| C11 | Alternative data can help address SME information gaps but introduces responsible-use and data-quality considerations. | [World Bank report](https://documents1.worldbank.org/curated/en/701331497329509915/pdf/116186-WP-AlternativeFinanceReportlowres-PUBLIC.pdf) | Supports research direction, not an Olin performance claim. |
| C12 | The current Olin repository is not reproducibly releasable and concentrates routing/persistence risk in large prototype modules. | Local audit in `docs/ELEKTRA_TECHNICAL_AUDIT_2026-09-01.md` | Local point-in-time evidence; rerun after release reset. |

## Claims expressly prohibited for next week's review

- “Olin is production ready for Elektra.”
- “Olin increases approvals or reduces defaults.”
- “Olin has a validated AI credit model.”
- “Two hundred loans are enough to train XGBoost.”
- “Synthetic or public data proves performance on Banco Azteca customers.”
- “Olin can approve, decline or move money.”
