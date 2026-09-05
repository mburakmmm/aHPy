"""qualified "module" documentation
ikinci satır"""


def answer():
    """answer documentation"""
    return 42


def selam_ç():
    return 43


def closure_unicode(value, /):
    içerik = value

    def oku_ç():
        return içerik

    return oku_ç()


cdef class QualifiedBox:
    """qualified box documentation"""

    def answer(self):
        """box answer documentation"""
        return 42

    def değer(self):
        return 44

    property başlık:
        """birinci "satır" \ yolu
        ikinci satır"""
        def __get__(self):
            return 46


cdef class DeğerKutusu:
    cdef public object içerik

    def __init__(self, içerik=None):
        self.içerik = içerik

    def answer(self):
        return 45
