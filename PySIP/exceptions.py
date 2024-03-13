
class SIPTransferException(Exception):
    def __init__(self, code, description):
        super().__init__(f"{code}: {description}")
        self.code = code
        self.description = description


class NoPasswordFound(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class NoSupportedCodecsFound(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class AudioStreamError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
