---
workflow: product-launch-video
flow: automation
storyboard: no
message: "A live local product test follows one synthetic merchant case from intake to decision and outcome"
destination: website
aspect: 1920x1080
language: en
audience: "Credit, risk, product, and partnership teams at Mexican lenders and payment networks"
length: 60s
angle: live-product-test
narration: yes
---

## Intent

Show the product as it actually works. Frame the video as a live local test and follow one synthetic merchant from
evidence intake through Círculo, repayment capacity, internal signals, tiering,
committee review, controlled disbursement logic, repayment events, and outcome
recording. Keep the institution's final authority visible throughout.

## Assets

- ../../../olin/server.py — analyst application and API behavior.
- ../../../olin_scoring.db — seeded demo data only.
- http://127.0.0.1:8080/ — local analyst interface when the demo server is running.

## Customizations

- Feature the real Olin analyst interface and make each test step explicit rather than presenting a generic product tour.
- Use a visible cursor and restrained zooms to direct attention.
- Show the difference between Olin's recommendation and the analyst's final decision.
- End with the outcome loop that makes future policy calibration possible.

## Notes

- Every displayed case must be clearly identified as synthetic demo data.
- Do not imply that software tests prove repayment performance.
- Do not show secrets, credentials, personal data, or a production database.
- Use Olin's dark green, warm cream, and electric lime visual system.
