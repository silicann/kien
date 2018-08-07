import enum
from .. import create_commander, var, CommandResult
from ..transformation import to_bool, to_enum


class OutputFormat(enum.Enum):
    HUMAN = 'human'
    JSON = 'json'


command = create_commander('set', description='Change properties of the console interface.')


@command('set', is_abstract=True, inject=['console'])
def set_state():
    pass


@command('echo', var('state', transform=to_bool, choices=('on', 'off')), parent=set_state)
def set_echo(console, state):
    """ enable/disable any output of prompts or typed text """
    console.set_echo(state)
    yield CommandResult('Echo is now {}'.format('enabled' if state else 'disabled'))


@command('output-format', var('format', choices=OutputFormat), parent=set_state)
@command.transform(format=to_enum(OutputFormat))
def set_output_format(console, format: OutputFormat):
    """ switch the response output format """
    console.select_output_format(format)
    yield CommandResult('Output format set to "{}"'.format(format.value))
