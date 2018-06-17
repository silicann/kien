class Event(Exception):
    pass


class ConsoleExitEvent(Event):
    """ signal a console termination request from the user """


class StopProcessingEvent(Event):
    """ signal that a command should not be processed further

    Once received no further processing will occur for a dispatched command.
    Makes the console carry its last assigned error code instead of assigning
    a new one.
    """
