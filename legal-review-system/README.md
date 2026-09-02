# Olin legal review system

This folder prepares a shadow-pilot contract for review by licensed Mexican counsel. It does not replace legal advice and does not send anything automatically.

## Safe workflow

```bash
python3 legal-review-system/scripts/legal_review_workflow.py prepare \
  --contract legal-review-system/contracts/OLIN_PILOTO_SOMBRA_BORRADOR_REVISION_LEGAL.docx \
  --matter OLIN-PILOT-001 \
  --recipient-name "Nombre de la abogada" \
  --recipient-email "abogada@example.mx"

python3 legal-review-system/scripts/legal_review_workflow.py approve \
  --matter OLIN-PILOT-001 \
  --approved-by "Brice Garnier"

python3 legal-review-system/scripts/legal_review_workflow.py send \
  --matter OLIN-PILOT-001 \
  --confirm-send SEND
```

`prepare` creates a review package and `.eml` preview in `legal-review-system/outbox/`. `approve` records who approved the exact contract hash. `send` refuses unapproved, changed, or previously sent packages.

Actual sending requires these environment variables:

- `OLIN_LEGAL_SMTP_HOST`
- `OLIN_LEGAL_SMTP_PORT` (default `465`)
- `OLIN_LEGAL_SMTP_USER`
- `OLIN_LEGAL_SMTP_PASSWORD`
- `OLIN_LEGAL_FROM_EMAIL`

Do not put credentials in repository files. Review the generated `.eml` and attachment before approval. A lawyer should return comments or a redline; the counterparty should not receive this preliminary draft.
