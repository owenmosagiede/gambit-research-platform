"""Subprocess fixture boundary only. Not included in production releases."""
from pathlib import Path
import os
from test_research_runtime import Adapter
from services.research_worker import WebResearchJobs
from api.catalog_cache import CatalogCache

def web():
    from web.wsgi import application
    import logging
    logging.getLogger("django.request").addHandler(logging.StreamHandler())
    import web.views
    root=Path(os.environ['GAMBIT_RESEARCH_ROOT'])
    jobs=WebResearchJobs(root,adapter=Adapter())
    catalogs=CatalogCache()
    web.views.services=lambda _: (jobs,catalogs)
    return application

if __name__=='__main__':
    from test_separate_services import worker_main
    worker_main(Path(os.environ['GAMBIT_RESEARCH_ROOT']))
