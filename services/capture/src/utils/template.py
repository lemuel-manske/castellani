KEY_FORMAT = "{{%s}}"


class Template:
    """
    A simple template class that allows for string replacement using a specific key format.
    """

    def __init__(self, of: str):
        self.it = of

    def r(self, key: str, value: str) -> "Template":
        self.it = self.it.replace(KEY_FORMAT % key, value)
        return self

    def __str__(self) -> str:
        return self.it


def template(of: str) -> Template:
    return Template(of)
