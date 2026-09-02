# All-business bank policy catalogue

Olin currently accepts 20 business types grouped into nine underwriting archetypes. Every type is committee-only by default. A type can enter an automated policy only after bank/model-risk approval backed by outcome validation.

| Business types | Archetype | Primary evidence | Operating metrics | Downside tests |
|---|---|---|---|---|
| `pharmacy` | Pharmacy inventory | Bank cash flow, suppliers, regulatory status | Inventory days, margin, expiries, stockouts | Supplier disruption, margin compression, expiry shock |
| `abarrotes`, `retail`, `wholesale` | Inventory retail | Supplier purchases, bank cash flow | Turnover, margin, supplier concentration, cash-sales share | Supplier prices, sales decline, obsolescence |
| `jugueria`, `taqueria`, `restaurant`, `hospitality` | Food/hospitality | POS, bank cash flow | Daily sales, food cost/occupancy, ticket, platform share | Sales decline, input costs, seasonal trough |
| `services`, `health_beauty`, `education`, `healthcare` | Recurring services | Bank cash flow, POS | Repeat revenue, concentration, margin, cancellations | Customer loss, utilization decline, owner unavailability |
| `professional`, `construction` | Professional/project | Bank cash flow, identity/consent | Backlog, receivable days, project margin, largest-project share | Payment delay, cost overrun, cancellation |
| `transport`, `logistics` | Asset/route | Bank cash flow, identity/consent | Route revenue, utilization, fuel share, maintenance | Fuel increase, downtime, contract loss |
| `light_manufacturing`, `agriculture` | Production cycle | Bank cash flow, supplier purchases | Production, unit margin, inputs, cycle length | Input inflation, yield decline, collection delay |
| `ecommerce` | Digital commerce | Net POS/platform settlements, bank cash flow | Refunds, platform share, advertising share | Platform suspension, refund spike, acquisition-cost increase |
| `other` | Unclassified/manual | Bank cash flow, identity/consent | Verified revenue/costs, concentration, cash-conversion cycle | Bank-defined downside, revenue interruption |

## Common bank contract for every type

- Identity, consent, ownership and account-holder match.
- Credit bureau status and existing obligations.
- Bank Feature Contract v2 with monthly-normalized operating inflows/outflows, separately classified transfers, debt proceeds and refunds.
- Account coverage, classification coverage, calculation version, source and retrievable evidence reference.
- Facility amount, term, rate, policy ceiling, target DSCR and stress assumptions.
- Geo/continuity evidence where location materially affects repayment.
- Independent bank decision followed by immutable DPD, payment, restructuring, default, charge-off or paid-off outcomes.

## Current acceptance result

`scripts/all_business_bank_acceptance.py` runs one positive journey for every type plus negative cases for untrusted evidence, incomplete accounts and negative cash flow. Passing this suite proves software routing and controls only; it does not validate credit performance.
