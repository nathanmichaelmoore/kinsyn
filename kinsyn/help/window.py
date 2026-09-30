"""Non-modal help window: table of contents, full-text search, and a
Markdown viewer with back / forward."""

import re

from PySide6 import QtCore, QtGui, QtWidgets

from .topics import DOCS_DIR, TOC


class HelpWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("kinsyn help")
        self.resize(1050, 760)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search help…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item)
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 0, 6)
        ll.addWidget(self.search)
        ll.addWidget(self.tree)

        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_link)
        self.browser.setSearchPaths([str(DOCS_DIR)])
        f = self.browser.font()
        f.setPointSizeF(f.pointSizeF() + 1)
        self.browser.setFont(f)

        split = QtWidgets.QSplitter()
        split.addWidget(left)
        split.addWidget(self.browser)
        split.setSizes([260, 790])
        self.setCentralWidget(split)

        tb = self.addToolBar("Navigation")
        tb.setMovable(False)
        tb.addAction("◀ Back", self.browser.backward)
        tb.addAction("Forward ▶", self.browser.forward)
        tb.addAction("Home", lambda: self.open("index.md"))
        self._populate()
        self.open("index.md")

    # --- navigation ------------------------------------------------------
    def open(self, path):
        """Open a doc by path relative to the docs folder."""
        path = path.removeprefix("help:")
        target = (DOCS_DIR / path).resolve()
        if not target.exists():
            self.browser.setMarkdown(f"# Not found\n\n`{path}` does not exist.")
            return
        self.browser.setSource(QtCore.QUrl.fromLocalFile(str(target)), QtGui.QTextDocument.MarkdownResource)
        self._select_in_tree(target)
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_link(self, url):
        if url.scheme() in ("http", "https"):
            QtGui.QDesktopServices.openUrl(url)
            return
        if url.scheme() == "help":
            self.open(url.path() or url.toString().removeprefix("help:"))
            return
        resolved = self.browser.source().resolved(url)
        if resolved.isLocalFile() and resolved.toLocalFile().endswith(".md"):
            self.browser.setSource(resolved, QtGui.QTextDocument.MarkdownResource)
            self._select_in_tree(resolved.toLocalFile())
        else:
            self.browser.setSource(resolved)

    def _on_item(self, item):
        path = item.data(0, QtCore.Qt.UserRole)
        if path:
            self.open(path)

    def _select_in_tree(self, target):
        target = str(target)
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            p = item.data(0, QtCore.Qt.UserRole)
            if p and str((DOCS_DIR / p).resolve()) == target:
                self.tree.setCurrentItem(item)
                return
            it += 1

    # --- contents / search ----------------------------------------------
    def _populate(self):
        text = self.search.text().strip().lower()
        self.tree.clear()
        if text:
            words = text.split()
            for section, items in TOC:
                for title, path in items:
                    body = (DOCS_DIR / path).read_text(errors="replace").lower()
                    if all(w in body or w in title.lower() for w in words):
                        hit = QtWidgets.QTreeWidgetItem([f"{title}  ({section})"])
                        hit.setData(0, QtCore.Qt.UserRole, path)
                        m = re.search(re.escape(words[0]), body)
                        if m:
                            snippet = body[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
                            hit.setToolTip(0, "…" + snippet + "…")
                        self.tree.addTopLevelItem(hit)
            if not self.tree.topLevelItemCount():
                self.tree.addTopLevelItem(QtWidgets.QTreeWidgetItem(["No matches"]))
            return
        for section, items in TOC:
            node = QtWidgets.QTreeWidgetItem([section])
            f = node.font(0)
            f.setBold(True)
            node.setFont(0, f)
            for title, path in items:
                child = QtWidgets.QTreeWidgetItem([title])
                child.setData(0, QtCore.Qt.UserRole, path)
                node.addChild(child)
            self.tree.addTopLevelItem(node)
            node.setExpanded(True)
