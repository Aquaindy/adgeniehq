from app.skills.seo.canonical import check_canonical
from app.skills.seo.faq_schema import check_faq_schema
from app.skills.seo.open_graph import check_open_graph
from app.skills.seo.sitemap import SitemapResult, discover_sitemap
from app.skills.seo.structured_data import check_structured_data

__all__ = [
    "SitemapResult",
    "check_canonical",
    "check_faq_schema",
    "check_open_graph",
    "check_structured_data",
    "discover_sitemap",
]
