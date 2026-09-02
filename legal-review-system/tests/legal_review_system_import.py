from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "legal_review_workflow.py"
SPEC = spec_from_file_location("olin_legal_review_workflow", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load legal review workflow")
workflow = module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)
