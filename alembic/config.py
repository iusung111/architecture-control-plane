class Config:
    def __init__(self, path: str | None = None):
        self.path = path
        self._options: dict[str, str] = {}

    def set_main_option(self, key: str, value: str) -> None:
        self._options[key] = value

    def get_main_option(self, key: str, default: str | None = None) -> str | None:
        return self._options.get(key, default)
