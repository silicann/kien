class Event(Exception):
    pass


class ConsoleExitEvent(Event):
    """ signal a console termination request from the user """
