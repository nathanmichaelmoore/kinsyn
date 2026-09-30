import re
from pathlib import Path

import pytest

from kinsyn.help.topics import DOCS_DIR, PARAM_TERMS, PLOT_TERMS, TERMS, all_doc_paths

DOCS = sorted(DOCS_DIR.rglob("*.md"))
LINK = re.compile(r"\]\(([^)#\s]+)")


def test_toc_covers_every_doc():
    listed = {str((DOCS_DIR / p).resolve()) for p in all_doc_paths()}
    on_disk = {str(p.resolve()) for p in DOCS}
    assert listed == on_disk


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(DOCS_DIR)))
def test_links_and_images_resolve(doc):
    for target in LINK.findall(doc.read_text()):
        if target.startswith(("http:", "https:", "help:")):
            continue
        assert (doc.parent / target).resolve().exists(), f"{doc.name}: broken link {target}"


def test_terms_point_at_docs():
    for key, (title, short, path) in TERMS.items():
        assert (DOCS_DIR / path).exists(), key
        assert short and title
    assert set(PLOT_TERMS.values()) <= set(TERMS)
    assert set(PARAM_TERMS.values()) <= set(TERMS)


def test_diagrams_are_generated_svgs():
    imgs = list((DOCS_DIR / "img").glob("*.svg"))
    assert len(imgs) >= 10
    for p in imgs:
        assert p.read_text().startswith("<svg")
