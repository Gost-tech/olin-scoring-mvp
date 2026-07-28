"""HTTP-facing services for the Olin partner MVP.

The scorecard remains in :mod:`olin.scorecard`.  This package owns the
application boundary: authentication, authorization, case creation and case
queries.  Keeping those concerns here lets ``server.py`` remain a small HTTP
adapter over time instead of becoming a second business engine.
"""

