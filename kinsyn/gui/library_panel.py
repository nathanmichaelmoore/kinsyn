"""Library browser: grouped, searchable list of mechanism templates."""

import html

from PySide6 import QtCore, QtWidgets

from kinsyn.library.catalog import GROUP_ORDER, load_all


class LibraryPanel(QtWidgets.QWidget):
    entrySelected = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self.entries = load_all()
        lay = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search: e.g. quick-return, over-center, slider…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate)
        lay.addWidget(self.search)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_current)
        lay.addWidget(self.tree, 3)
        self.info = QtWidgets.QTextBrowser()
        self.info.setOpenExternalLinks(False)
        lay.addWidget(self.info, 2)
        self._populate()

    def reload(self):
        self.entries = load_all()
        self._populate()

    def _populate(self):
        text = self.search.text()
        self.tree.clear()
        groups = {}
        order = GROUP_ORDER + sorted({e.group for e in self.entries} - set(GROUP_ORDER))
        for g in order:
            members = [e for e in self.entries if e.group == g and e.matches(text)]
            if not members:
                continue
            node = QtWidgets.QTreeWidgetItem([g])
            node.setFlags(node.flags() & ~QtCore.Qt.ItemIsSelectable)
            f = node.font(0)
            f.setBold(True)
            node.setFont(0, f)
            self.tree.addTopLevelItem(node)
            for e in members:
                child = QtWidgets.QTreeWidgetItem([e.name])
                child.setData(0, QtCore.Qt.UserRole, e)
                child.setToolTip(0, ", ".join(e.tags))
                node.addChild(child)
            groups[g] = node
            node.setExpanded(True)

    def _on_current(self, item, _prev):
        entry = item.data(0, QtCore.Qt.UserRole) if item else None
        if entry is None:
            return
        tags = " ".join(f"<code>{html.escape(t)}</code>" for t in entry.tags)
        self.info.setHtml(f"<h3>{html.escape(entry.name)}</h3><p>{html.escape(entry.description)}</p>"
                          f"<p style='color:#8a93a3'>{tags}</p>")
        self.entrySelected.emit(entry)
