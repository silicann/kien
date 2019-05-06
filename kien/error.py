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


class ShouldThrottleException(CommandError):
    """
    Raised if the transport interface was unable to write data fast enough
    and raised a BlockingIOError. The command generating the data should
    reduce its output.
    """

    def __init__(self) -> None:
        super().__init__('The command was aborted because the output interface '
                         'was unable to write data fast enough. Please choose '
                         'an interface with higher throughput like USB if available.',
                         None, 1, 'KIEN.interface.data_overflow')
