"""Compatibility wrapper — article_updater is archived.

Symbols moved to note.workflows:
  load_manifest → load_manifest_by_sheet_no
  _check_published → check_published
  NOTE_KEY_RE → NOTE_KEY_RE
"""
from note.workflows import (
    load_manifest_by_sheet_no as load_manifest,
    check_published as _check_published,
    NOTE_KEY_RE,
)
