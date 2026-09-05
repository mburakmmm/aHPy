def closure_roundtrip(value, /):
    captured = value

    def read_capture():
        return captured

    return read_capture()
