def answer():
    return 42


cdef class Box:
    cdef public object value

    def __init__(self, value, /):
        self.value = value

    def identity(self):
        return self.value
