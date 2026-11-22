"""Import every pipeline package so its step handlers register (see `app.jobs.registry`).

Packages that are not on this branch yet are skipped; add new pipeline packages here.
"""

import importlib
import logging

log = logging.getLogger(__name__)

PIPELINES = (
    "app.pipelines.discover",
    "app.pipelines.investors",
    "app.pipelines.verify",
    "app.pipelines.act",
    "app.pipelines.evaluate",
    "app.pipelines.memo",
)

for _name in PIPELINES:
    try:
        importlib.import_module(_name)
    except ModuleNotFoundError as exc:
        if exc.name is None or not _name.startswith(exc.name):
            raise
        log.info("pipeline package %s not present; skipping", _name)
