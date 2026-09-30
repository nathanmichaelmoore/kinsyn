"""The editable target with undo/redo and selection."""

from PySide6 import QtCore, QtGui

from kinsyn.core.target import Target


class SnapshotCommand(QtGui.QUndoCommand):
    """Swap whole-target snapshots. Consecutive commands with the same
    merge key (e.g. one drag) collapse into a single undo step."""

    def __init__(self, doc, before, after, text, merge_key=None):
        super().__init__(text)
        self.doc, self.before, self.after, self.merge_key = doc, before, after, merge_key

    def id(self):
        return 1 if self.merge_key else -1

    def mergeWith(self, other):
        if other.merge_key != self.merge_key:
            return False
        self.after = other.after
        return True

    def redo(self):
        self.doc._set(self.after.copy())

    def undo(self):
        self.doc._set(self.before.copy())


class TargetDocument(QtCore.QObject):
    changed = QtCore.Signal()
    selectionChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target = Target()
        self.selected = None  # keyframe id
        self.selected_item = None  # (kind, id, point index) for curves / zones / pivots
        self.undo = QtGui.QUndoStack(self)
        self._merge_serial = 0

    def _set(self, target):
        self.target = target
        if self.selected_item and not self._item_exists(self.selected_item):
            self.selected_item = None
        if self.selected and self.target.keyframe(self.selected) is None:
            self.selected = None
            self.selectionChanged.emit()
        self.changed.emit()

    def apply(self, new_target, text, merge_key=None):
        """Record an edit. Pass the same merge_key for every step of one drag."""
        self.undo.push(SnapshotCommand(self, self.target.copy(), new_target.copy(), text, merge_key))

    def new_merge_key(self):
        self._merge_serial += 1
        return f"m{self._merge_serial}"

    def edit(self, text, fn, merge_key=None):
        """Apply `fn(target_copy)` as one undoable edit."""
        t = self.target.copy()
        fn(t)
        self.apply(t, text, merge_key)

    def reset(self, target):
        """Replace the whole target (new/open project); clears history."""
        self.undo.clear()
        self.selected = None
        self.selected_item = None
        self._set(target.copy())
        self.selectionChanged.emit()

    def select(self, kid):
        if kid != self.selected or (kid and self.selected_item):
            self.selected = kid
            if kid:
                self.selected_item = None
            self.selectionChanged.emit()

    def select_item(self, item):
        if item != self.selected_item or (item and self.selected):
            self.selected_item = item
            if item:
                self.selected = None
            self.selectionChanged.emit()

    def _item_exists(self, item):
        kind, iid, _ = item
        group = {"curve": self.target.curves, "zone": self.target.zones, "pivot": self.target.pivots}[kind]
        return any(x.id == iid for x in group)

    def delete_selection(self):
        """Delete the selected keyframe, or the whole selected curve / zone / pivot."""
        if self.selected:
            kid = self.selected
            self.edit("Delete keyframe", lambda t: t.keyframes.pop(t.index_of(kid)))
        elif self.selected_item:
            kind, iid, _ = self.selected_item
            attr = {"curve": "curves", "zone": "zones", "pivot": "pivots"}[kind]
            self.edit(f"Delete {kind}", lambda t: setattr(t, attr, [x for x in getattr(t, attr) if x.id != iid]))

    def selected_keyframe(self):
        return self.target.keyframe(self.selected) if self.selected else None
