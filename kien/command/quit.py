from .. import create_commander
from ..events import ConsoleExitEvent

command = create_commander('quit')


@command('exit')
def exit():
    """ exit the interpreter """
    raise ConsoleExitEvent()


@command('quit')
def quit():
    """ exit the interpreter """
    raise ConsoleExitEvent()
