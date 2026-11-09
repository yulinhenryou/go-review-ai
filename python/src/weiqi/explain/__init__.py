"""L4 explanation: text rendered from structured results through locale
catalogs (`zh-CN`, `en`). Results carry codes and numbers; this layer
chooses words, and never adds a number or coordinate the result lacks."""

from weiqi.explain.catalog import LOCALES, Catalog, load_catalog
from weiqi.explain.report import render_report

__all__ = ["LOCALES", "Catalog", "load_catalog", "render_report"]
