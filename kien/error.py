class CommandError(RuntimeError):
    """ raised if an error occurred while executing a command """

    def __init__(self, message, data=None, status=1, code=None) -> None:
        super().__init__()
        self.message = message
        self.data = data
        self.success = False
        self.status = status
        self.code = code

    def __str__(self):
        return self.message


class ParseError(CommandError):
    """ raised in case of an invalid command """


class ItemNotFoundError(CommandError):
    """ raised if a variable reference was not found """


class InjectionError(CommandError):
    """ raised if a dependency injection failed """
