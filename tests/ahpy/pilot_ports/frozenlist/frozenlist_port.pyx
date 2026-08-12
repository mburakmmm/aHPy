# Licensed under the Apache License, Version 2.0.
# Derived from aio-libs/frozenlist at the commit recorded in PORTING.md.


cdef class FrozenList:
    cdef bint _frozen
    cdef object _items

    def __init__(self, items=None):
        self._frozen = False
        if items is None:
            self._items = []
        else:
            self._items = list(items)
        return

    @property
    def frozen(self):
        return bool(self._frozen)

    def _check_frozen(self):
        if self._frozen:
            raise RuntimeError("Cannot modify frozen list.")
        return None

    def freeze(self):
        self._frozen = True
        return None

    def snapshot(self):
        return list(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def __setitem__(self, index, value):
        self._check_frozen()
        self._items[index] = value
        return

    def __delitem__(self, index):
        self._check_frozen()
        del self._items[index]
        return

    def __len__(self):
        return len(self._items)

    def __contains__(self, item):
        return item in self._items

    def insert(self, position, item):
        self._check_frozen()
        self._items.insert(position, item)
        return None

    def append(self, item):
        self._check_frozen()
        self._items.append(item)
        return None

    def pop(self, index=-1):
        self._check_frozen()
        return self._items.pop(index)

    def clear(self):
        self._check_frozen()
        self._items.clear()
        return None

    def extend(self, items):
        self._check_frozen()
        self._items.extend(list(items))
        return None

    def reverse(self):
        self._check_frozen()
        self._items.reverse()
        return None

    def index(self, item):
        return self._items.index(item)

    def count(self, item):
        return self._items.count(item)

    def remove(self, item):
        self._check_frozen()
        self._items.remove(item)
        return None

    def __repr__(self):
        return "<FrozenList(frozen={}, {!r})>".format(
            bool(self._frozen), self._items)

    def __hash__(self):
        if self._frozen:
            return hash(tuple(self._items))
        raise RuntimeError("Cannot hash unfrozen list.")


cdef class DerivedFrozenList(FrozenList):
    def inherited_size(self):
        return len(self._items)
