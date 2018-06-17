import os
import re
from collections import OrderedDict
from itertools import groupby
from textwrap import wrap, indent

from ..commands import create_commander, var, CommandResult, filter_root_commands, \
    filter_public_commands
from ..transformation import flatten, unique
from ..utils import join_generator_string, TaggedString
from ..utils import strip_tags, read_object_path
from ..error import CommandError

WRAP_WIDTH = 80

command = create_commander('help', description='List and describe all available commands.')


def _indent_no_first():
    first = [True]

    def callback(line):
        if not line.strip():
            return False
        if first[0]:
            first[0] = False
            return False
        else:
            return True
    return callback


def _wrap_indent(text, prefix, text_width=WRAP_WIDTH):
    wrapped_text = os.linesep.join(wrap(_str(text), width=text_width))
    return indent(wrapped_text, prefix)


def _str(text):
    return text.strip() if isinstance(text, str) else ''


def render_description(cmd, long_prefix='  - ',  text_width=WRAP_WIDTH):
    doc = re.sub(r'[ ]{2,}', '', _str(cmd.__doc__))
    _indent = '\t' + ' ' * len(long_prefix)

    if doc:
        lines = _wrap_indent(doc, _indent, text_width).split(os.linesep)
        lines[0] = lines[0].replace(_indent, '\t' + long_prefix)
        doc = os.linesep + os.linesep.join(lines)
    for token in cmd.tokens:
        if not token.name:
            continue
        if not token.description and not token.choices:
            continue
        token_name = strip_tags(str(token)) + ': '
        token_doc = os.linesep + _indent + token_name
        token_indent = _indent + ' ' * len(token_name)

        if token.description:
            description = os.linesep.join(wrap(token.description, text_width - len(token_indent)))
            token_description = indent(description, token_indent, _indent_no_first())
            token_doc += token_description
        if token.choices:
            if token.description:
                token_doc += os.linesep + token_indent
            token_doc += '%s' % ' | '.join(sorted(map(str, token.choices)))
        doc += token_doc

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
        yield TaggedString.help(_wrap_indent(root.__commander__.__doc__, ''))
    yield ''
    yield TaggedString.label('Supported Subcommands')
    public_commands = filter_public_commands(all_commands)
    sub_commands = [cmd for cmd in public_commands if is_command_root(root, cmd)]
    first = True
    for group, group_commands in groupby(sub_commands, key=lambda cmd: cmd.group):
        if first:
            first = False
        else:
            yield ''

        if group is not None:
            yield '\t%s' % TaggedString.label(group.name)
            if group.description:
                yield TaggedString.help(indent(os.linesep.join(wrap(group.description)), '\t  '))
        for cmd in group_commands:
            cmd_str = str(cmd)
            term_width = read_object_path(terminal, 'width', default=None)
            text_width = min(term_width, WRAP_WIDTH) if term_width else WRAP_WIDTH
            doc = render_description(cmd, text_width=text_width)
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
        yield CommandResult(describe_command_list(command_map))
    else:
        try:
            yield CommandResult(describe_command(commands, command_map[command]))
        except KeyError as exc:
            raise CommandError('No help for command "%s" available' % command) from exc


@command.inject(commands='__commands[]')
@command.transform(commands=[flatten, unique])
def find_root_commands(commands):
    root_commands = filter_root_commands(commands)
    command_map = OrderedDict(
        (str(cmd), cmd) for cmd in sorted(root_commands, key=lambda cmd: str(cmd))
    )
    return command_map
