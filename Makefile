.PHONY: technical-go check-backend check-website pilot-gate

PYTHON ?= python3
PNPM ?= pnpm

technical-go: check-backend check-website
	@echo "TECHNICAL_GO_FOR_SYNTHETIC_UAT"
	@echo "Controlled shadow still requires: make pilot-gate MANIFEST=path/to/pilot_manifest.json"

check-backend:
	$(PYTHON) -m compileall -q olin scripts *.py
	$(PYTHON) -m unittest discover -v
	$(PYTHON) -m olin.test_v2
	$(PYTHON) test_full_flow.py
	$(PYTHON) test_belvo_pipeline.py
	$(PYTHON) -m olin.synthetic_portfolio --cases 1000 --seed 42
	$(PYTHON) -m json.tool docs/openapi-v1.json >/dev/null

check-website:
	cd website && $(PNPM) install --frozen-lockfile
	cd website && $(PNPM) test

pilot-gate:
	@test -n "$(MANIFEST)" || (echo "Usage: make pilot-gate MANIFEST=path/to/pilot_manifest.json" >&2; exit 2)
	$(PYTHON) -m scripts.pilot_gate "$(MANIFEST)"
