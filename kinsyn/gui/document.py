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
        self.undo = QtGui.QUndoStack(self)
        self._merge_serial = 0

    def _set(self, target):
        self.target = target
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
        self._set(target.copy())
        self.selectionChanged.emit()

    def select(self, kid):
        if kid != self.selected:
            self.selected = kid
            self.selectionChanged.emit()

    def selected_keyframe(self):
        return self.target.keyframe(self.selected) if self.selected else None
