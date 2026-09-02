# Olin wording audit — bank readiness

**Date:** 27 August 2026  
**Scope:** current text sources in `website/src`, primary README/start-here documents, partner/pilot runbooks, legal-path notes, analyst intake wording, and bank-integration documentation. Generated PDFs, videos, old website builds, and third-party dependencies were not treated as authoritative text.  
**Status:** preliminary legal-operations review, not Mexican legal advice.

## Verdict

The core public positioning is disciplined: Olin is generally described as rules-based decision support, the institution owns the decision, demo data is synthetic, and the proposed first step moves no money. The highest risk is not an aggressive lending claim; it is incomplete privacy/contract language and technical statements that can sound broader than the actual control.

## Priority findings

| Severity | Surface | Finding | Required action |
| --- | --- | --- | --- |
| BLOCK | Website privacy notice | The page calls itself preliminary and lacks the final responsible entity, domicile, complete purpose/retention description, ARCO procedure, transfer/processor position, and final contact route. | Do not treat it as a final privacy notice. Mexican counsel must complete it before commercial collection of personal data. |
| BLOCK | Bank pilot contract | No executed agreement currently fixes data roles, permitted fields, ten-case ceiling, security schedule, retention/deletion, incidents, audit, fees, liability, or stop rights. | Use the new draft only as a lawyer mark-up starting point. |
| COUNSEL | Círculo wording | Several materials say consent is recorded, but the repository itself acknowledges that the current record is not a complete authorization artifact. | Replace unqualified `consentimiento registrado` in external demos with `registro técnico ilustrativo; suficiencia jurídica pendiente` until approved text and evidence exist. |
| COUNSEL | Regulatory responsibility | `El originador conserva ... responsabilidades regulatorias` could be read as transferring all responsibility away from Olin. Contractual allocation cannot eliminate Olin's own direct duties. | Use `La institución conserva la decisión y sus obligaciones; cada parte mantiene las obligaciones que legalmente le correspondan.` |
| COUNSEL | Data-role language | Documents do not determine whether Olin is `encargado`, independent `responsable`, or another role for each flow. | Add a data inventory and have counsel decide role per purpose and dataset. |
| NEGOTIATE | Free diagnostic | `diagnóstico de cartera sin costo` may imply review of actual portfolio data, while the form is only B2B lead intake. | Change to `sesión inicial de diagnóstico del proceso, sin costo`; say no portfolio files are requested at this stage. |
| CLARIFY | Encryption statement | The privacy page correctly says the email is encrypted, but other fields—name, organization, role, portfolio band, and free text—are stored in plaintext in the waitlist table. | State exactly which field is encrypted and avoid suggesting the complete record is encrypted. Minimize or encrypt the remaining personal fields before stronger claims. |
| CLARIFY | Production language | Phrases such as `En producción, la ruta ... exige` describe intended enforcement but can be mistaken for deployed, institution-approved production. | Prefer `En el código configurado para modo producción...`; add that real-data deployment and external approval remain blocked. |
| CLARIFY | `aprobación automática` | Internal scorecard language can recommend an automatic route, while the pilot still requires human/institution approval. | Use `ruta favorable del motor` in external materials; reserve `auto-approve` for technical policy documentation. |
| CLARIFY | Partnerships and logos | Materials correctly warn against naming Monex/Círculo/providers as partners, but old exported decks/PDFs may still circulate. | Create a controlled current-assets register and archive superseded files with a visible `NO USAR` label. |

## Wording approved for current bank conversations

> Olin es un prototipo funcional de apoyo a la decisión basado en reglas explicables. En el piloto propuesto, la institución conserva su proceso, su decisión oficial y las obligaciones que legalmente le correspondan. Olin genera una segunda lectura trazable de hasta diez expedientes autorizados, en paralelo y sin mover dinero. El piloto mide cobertura, tiempo, faltantes, trazabilidad y utilidad operativa; no valida todavía precisión predictiva ni desempeño de cartera.

## Wording to avoid

- `Olin cumple con toda la regulación mexicana.`
- `El consentimiento ya es legalmente válido.`
- `Olin está listo para producción con datos reales.`
- `Olin aprueba créditos automáticamente.`
- `Monex, Círculo, Syncfy, FEMSA o Bimbo son socios de Olin.`
- `La información está cifrada` without specifying fields, storage layer, configuration, and exceptions.
- `Piloto sin riesgo`, `precisión comprobada`, `reduce pérdidas`, or any guaranteed outcome.

## Immediate copy changes recommended

1. On `lista-espera`, replace `diagnóstico de cartera sin costo` with `sesión inicial de diagnóstico del proceso, sin costo`.
2. On the terms page, replace the statement that the originator retains regulatory responsibilities with a two-sided statement preserving each party's legal duties.
3. On the privacy page, explicitly say it is not the final integral notice and identify the fields that are not encrypted; preferably pause production intake until counsel supplies the final notice.
4. On demo scenes, label the Círculo consent artifact illustrative and legally unapproved.
5. Add a footer to every pilot proposal: `Borrador comercial sujeto a contrato, privacidad, seguridad, riesgo y aprobación jurídica; no es oferta de crédito.`

## Questions for counsel

1. Can Olin operate the described shadow pilot strictly as a B2B software provider, and what direct duties remain with Olin?
2. Who is responsible or processor for lead data, case data, derived features, audit logs, and outcome labels?
3. What exact merchant notice, consent, and separate Círculo authorization/evidence are required?
4. Can the bank provide normalized derived features rather than raw statements, and does this materially change the data role?
5. What retention, deletion, correction, portability, and incident terms should appear in the agreement and notice?
6. Are electronic signatures and evidence preservation under the proposed flow adequate, including any NOM-151 use?
7. Which liability, indemnity, audit, insurance, dispute, and subcontractor provisions are market-acceptable for a Mexican bank pilot?
8. What changes before Olin may support live decisions, disbursement, servicing, or collections?

## Official starting points checked

- [LFPDPPP](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf)
- [LRSIC](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRSIC.pdf)
- [Fintech Law](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRITF.pdf)
- [LFPIORPI](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPIORPI.pdf)
- [Código de Comercio](https://www.diputados.gob.mx/LeyesBiblio/pdf/CCom.pdf)
- [NOM-151-SCFI-2016](https://dof.gob.mx/normasOficiales.php?codp=6499&view=si)
- [CONDUSEF RECA](https://registros.condusef.gob.mx/reca/reca.php)

Every legal conclusion must be rechecked against the exact facts and current official text by licensed Mexican counsel.
