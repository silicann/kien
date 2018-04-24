from collections import OrderedDict
from itertools import groupby
import os
from textwrap import wrap, indent
from ..commands import create_commander, var, CommandResult, filter_root_commands, \
    filter_public_commands
from ..transformation import flatten, unique
from ..utils import strip_tags, read_object_path
from ..utils import join_generator_string, TaggedString

WRAP_WIDTH = 80

command = create_commander('help', description='List and describe all available commands.')


def render_description(cmd, prefix=' - ', long_prefix='  - ',
                       wrap_width=WRAP_WIDTH, text_width=WRAP_WIDTH):
    doc = cmd.__doc__.strip() if cmd.__doc__ else ''
    _indent = '\t' + ' ' * len(long_prefix)
    choice_vars = [token for token in cmd.tokens if token.name and token.choices]

    if doc:
        if len(doc) > wrap_width:
            lines = indent(os.linesep.join(wrap(doc, text_width)), _indent).split(os.linesep)
            lines[0] = lines[0].replace(_indent, '\t' + long_prefix)
            doc = os.linesep + os.linesep.join(lines)
        else:
            doc = prefix + doc
    if choice_vars:
        for token in choice_vars:
            doc += os.linesep + _indent
            doc += '{}: (choices: {})'.format(
                strip_tags(str(token)),
                ', '.join(sorted(map(str, token.choices)))
            )

    return TaggedString.help(doc) if doc else ''


@join_generator_string()
def describe_command_list(commands: dict):
    yield TaggedString.label('Supported Commands')
    for label, command in commands.items():
        yield '\t%s' % label
    yield 'Use "%s" for a detailed help on individual commands' % str(help_command)


@join_generator_string()
@command.inject(terminal='terminal')
def describe_command(terminal, all_commands, root):
    yield TaggedString.header('%s command' % str(root))
    if root.__commander__.__doc__:
        yield TaggedString.help(indent(root.__commander__.__doc__.strip(), '  '))
    yield ''
    yield TaggedString.label('Supported Commands')
    public_commands = filter_public_commands(all_commands)
    sub_commands = [cmd for cmd in public_commands if is_command_root(root, cmd)]
    first = True
    for group, group_commands in groupby(sub_commands, key=lambda cmd: cmd.group):
        if first:
            first = False
        else:
            yield ''

        if group is not None:
            yield '\t%s:' % TaggedString.label(group.name)
            if group.description:
                yield TaggedString.help(indent(os.linesep.join(wrap(group.description)), '\t\t'))
        for cmd in group_commands:
            cmd_str = str(cmd)
            term_width = read_object_path(terminal, 'width', default=None)
            wrap_width = term_width - len(cmd_str) - 10 if term_width else WRAP_WIDTH
            text_width = min(term_width, WRAP_WIDTH) if term_width else WRAP_WIDTH
            doc = render_description(cmd, wrap_width=wrap_width, text_width=text_width)
            yield '\t%s%s' % (cmd_str, doc)


def is_command_root(root, command):
    if root is command:
        return True

    if command.parent is None:
        return False
    else:
        return is_command_root(root, command.parent)


@command('help', is_abstract=True)
def help():
    """ Shows available commands and documentation """
    pass


@command(var('command', is_optional=True), parent=help)
@command.inject(commands='__commands[]')
@command.transform(commands=[flatten, unique])
def help_command(commands, command=None):
    root_commands = filter_root_commands(commands)
    command_map = OrderedDict(
        (str(cmd), cmd) for cmd in sorted(root_commands, key=lambda cmd: str(cmd))
    )
    if command is None:
        yield CommandResult(message=describe_command_list(command_map))
    else:
        try:
            yield CommandResult(message=describe_command(commands, command_map[command]))
        except KeyError:
            yield CommandResult(False, 'No help for command "%s" available' % command)


@command.inject(commands='__commands[]')
@command.transform(commands=[flatten, unique])
def find_root_commands(commands):
    root_commands = filter_root_commands(commands)
    command_map = OrderedDict(
        (str(cmd), cmd) for cmd in sorted(root_commands, key=lambda cmd: str(cmd))
    )
    return command_map
