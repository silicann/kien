from collections import OrderedDict
from itertools import groupby
from operator import itemgetter
import os
import re
from textwrap import indent, wrap

from ..commands import (
    CommandResult,
    create_commander,
    filter_public_commands,
    filter_root_commands,
    var,
)
from ..error import CommandError
from ..transformation import flatten, unique
from ..utils import join_generator_string, strip_tags, TaggedString

command = create_commander("help", description="List and describe all available commands.")


def _indent_no_first():
    first = True

    def callback(line):
        nonlocal first

        if not line.strip():
            return False
        if first:
            first = False
            return False
        else:
            return True

    return callback


def _wrap_indent(text: str, prefix: str, text_width: int):
    paragraph_separator = os.linesep * 2
    paragraphs = [
        os.linesep.join(wrap(_str(paragraph), width=text_width))
        for paragraph in text.split(paragraph_separator)
    ]
    return indent(paragraph_separator.join(paragraphs), prefix)


def _str(text):
    return text.strip() if isinstance(text, str) else ""


def _render_description(cmd, text_width, long_prefix="  - "):
    doc = re.sub(r"[ ]{2,}", "", _str(cmd.__doc__))
    _indent = "\t" + " " * len(long_prefix)

    if doc:
        lines = _wrap_indent(doc, _indent, text_width).split(os.linesep)
        lines[0] = lines[0].replace(_indent, "\t" + long_prefix)
        doc = os.linesep + os.linesep.join(lines)
    for token in cmd.tokens:
        if not token.name:
            continue
        if not token.description and not token.choices:
            continue
        token_name = strip_tags(str(token)) + ": "
        token_doc = os.linesep + _indent + token_name
        token_indent = _indent + " " * len(token_name)

        if token.description:
            description = os.linesep.join(wrap(token.description, text_width - len(token_indent)))
            token_description = indent(description, token_indent, _indent_no_first())
            token_doc += token_description
        if token.choices:
            if token.description:
                token_doc += os.linesep + token_indent
            try:
                choices = list(token.choices.items())
            except AttributeError:
                token_doc += "%s" % " | ".join(sorted(map(str, token.choices)))
            else:
                choices.sort(key=itemgetter(0))
                for index, [key, value] in enumerate(choices):
                    if index:
                        token_doc += os.linesep + token_indent
                    token_doc += "{}: {}".format(key, value)
        doc += token_doc

    return TaggedString.help(doc) if doc else ""


@join_generator_string()
def describe_command_list(commands: dict):
    yield TaggedString.label("Supported Commands")
    for label, command in commands.items():
        yield "\t%s" % label
    yield 'Use "%s" for a detailed help on individual commands' % str(help_command)


@join_generator_string()
@command.inject(output_width="output_width")
def describe_command(all_commands, root, output_width=80):
    yield TaggedString.header("%s command" % str(root))
    if root.__commander__.__doc__:
        yield TaggedString.help(_wrap_indent(root.__commander__.__doc__, "", output_width))
    yield ""
    yield TaggedString.label("Supported Subcommands")
    public_commands = filter_public_commands(all_commands)
    sub_commands = [cmd for cmd in public_commands if is_command_root(root, cmd)]
    first = True
    for group, group_commands in groupby(sub_commands, key=lambda cmd: cmd.group):
        if first:
            first = False
        else:
            yield ""

        if group is not None:
            yield "\t%s" % TaggedString.label(group.name)
            if group.description:
                yield TaggedString.help(indent(os.linesep.join(wrap(group.description)), "\t  "))
        for cmd in group_commands:
            cmd_str = str(cmd)
            doc = _render_description(cmd, output_width)
            yield "\t{}{}\n".format(cmd_str, doc)


def is_command_root(root, command):
    if root is command:
        return True

    if command.parent is None:
        return False
    else:
        return is_command_root(root, command.parent)


@command("help", is_abstract=True)
def help():
    """Shows available commands and documentation"""
    pass


@command(var("command", is_optional=True), parent=help)
@command.inject(commands="__commands[]")
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


@command.inject(commands="__commands[]")
@command.transform(commands=[flatten, unique])
def find_root_commands(commands):
    root_commands = filter_root_commands(commands)
    command_map = OrderedDict(
        (str(cmd), cmd) for cmd in sorted(root_commands, key=lambda cmd: str(cmd))
    )
    return command_map
