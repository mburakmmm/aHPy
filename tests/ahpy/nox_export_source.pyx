def identity(value, /):
    return value


def text(str value, /):
    return value


cdef class Box:
    cdef object value

    def __cinit__(self, value, /):
        self.value = value

    def identity(self, value, /):
        return value
