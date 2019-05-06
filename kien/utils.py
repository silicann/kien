from collections import namedtuple, Iterable, UserString
import contextlib
from functools import wraps
import importlib
import logging
import os
import inspect
import time
import math
import re
import shlex
from typing import Sequence, Callable, Union

import blessings
from .events import StopProcessingEvent
from .error import ShouldThrottleException


PATH_ATTRIBUTE = re.compile(r'^(?P<attr>[a-zA-Z_][a-zA-Z_0-9]*)$')
PATH_DICT = re.compile(r'^(?P<attr>[a-zA-Z_][a-zA-Z_0-9]*)\[[\"\'](?P<key>.+)[\"\']\]$')
PATH_INDEX = re.compile(r'^(?P<attr>[a-zA-Z_][a-zA-Z_0-9]*)\[(?P<index>\d+)\]$')
PATH_CALL = re.compile(r'^(?P<attr>[a-zA-Z_][a-zA-Z_0-9]*)\(\)$')
TAG_REGEX = re.compile(r'(?:<(?P<tag>[a-z]+)>)'
                       r'(?P<content>(?:<(?!/)|[^<])+)'
                       r'(?:</(?P<closing_tag>[a-z]+)>)')
TokenMismatch = namedtuple('TokenMismatch', ['token', 'exception', 'value'])

try:
    # contextlib.AbstractContextManager was introduced in Python 3.7
    AbstractContextManager = contextlib.AbstractContextManager
except AttributeError:
    AbstractContextManager = object


def tokenize_args(comment_characters=('#',)):
    def decorator(func):
        @wraps(func)
        def wrapper(command, *args, **kwargs):
            if isinstance(command, str):
                command = command.strip()
                if any(map(lambda c: command.startswith(c), comment_characters)):
                    raise StopProcessingEvent()
                command = shlex.split(command)
            return func(command, *args, **kwargs)
        return wrapper
    return decorator


def is_or_extends(item, cls):
    if isinstance(item, cls):
        return True
    item_type = type(item)
    return issubclass(item_type, cls)


def join_generator_string(glue: str = os.linesep, formatter: Callable = None):
    def _format(value):
        if formatter is None:
            return str(value)
        return formatter(str(value))

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            return glue.join(map(_format, result)) if isinstance(result, Iterable) \
                else _format(result)
        return wrapper
    return decorator


def columns(separator='\t', join_char=None):
    join_char = join_char or separator

    def get_column_width(rows, index):
        return [len(row[index]) for row in rows]

    def calculate_column_widths(lines):
        column_lengths = []
        for index in range(0, len(lines[0])):
            column_lengths.append(max(get_column_width(lines, index)))
        return column_lengths

    def fit_row(row: Sequence[str], column_widths: Sequence[int]):
        for index, column in enumerate(row):
            yield column.ljust(column_widths[index])

    def decorator(func):
        @join_generator_string(formatter=str.rstrip)
        @wraps(func)
        def wrapper(*args, **kwargs):
            rows = [line.split(separator) for line in func(*args, *kwargs).split(os.linesep)]
            column_widths = calculate_column_widths(rows)
            for row in rows:
                yield join_char.join(fit_row(row, column_widths))
        return wrapper
    return decorator


class _Stop(Exception):
    pass


def throttle(frequency=None, limit=None):
    """
    throttle the frequency and limit the maximum number of calls of a function
    :param frequency: frequency of calls in hertz, defaults to infinity
    :param limit: total number of calls, defaults to infinity, must be > 0
    :raises _Stop: if limit has been reached
    :return: callable
    """
    frequency = math.inf if frequency is None else frequency
    calls_per_second = 1 / frequency
    # because variable scopes in python are pretty much useless for closures
    # we’re using single-element lists here
    last_call = [None]
    call_count = [0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_time = time.time()
            if last_call[0] is None or last_call[0] + calls_per_second < current_time:
                last_call[0] = current_time
                call_count[0] += 1
                result = func(*args, **kwargs)
                if inspect.isgenerator(result):
                    yield from result
                else:
                    yield result

            if call_count[0] == limit:
                raise throttle.Stop()
        return wrapper
    return decorator


throttle.Stop = _Stop


def enum_value_list(enum):
    return [item.value for item in tuple(enum)]


def _tagged_string(tag):
    @classmethod
    def func(cls, s):
        return str(cls(s, tag))
    func.__name__ = tag
    return func


class TaggedString(UserString):
    def __init__(self, seq, tag):
        super().__init__(seq)
        self.tag = tag

    def __str__(self):
        return '<{tag}>{token}</{tag}>'.format(token=self.data, tag=self.tag)

    @classmethod
    def __getattr__(cls, item):
        return lambda s: _tagged_string(item)(cls, s)

    optional = _tagged_string('optional')
    var = _tagged_string('var')
    error = _tagged_string('error')
    help = _tagged_string('help')
    label = _tagged_string('label')
    header = _tagged_string('header')


def strip_tags(s):
    # we don’t process html here but our own simple one-line strings
    # if you were to use this for html you are a bad bad dog
    return re.sub(r'<[^<]+?>', '', s)


def render_tags(s, terminal: blessings.Terminal):
    def _replace_tag(match):
        tag, content, closing_tag = match.groups()
        if tag != closing_tag:
            raise ValueError('tag mismatch in content')
        replaced_value = {
            'optional': terminal.dim,
            'var': terminal.bold_white,
            'error': terminal.red,
            'label': terminal.bold,
            'help': terminal.italic_dim,
            'header': lambda s: terminal.bold(s.upper()),
        }[tag](content)
        return replaced_value

    # normally re.sub would replace all occurrences in our
    # text but tags may be nested so we better be safe and
    # replace tags as long as we find some
    while re.search(TAG_REGEX, s):
        s = re.sub(TAG_REGEX, _replace_tag, s)
    return s


def autoload(commander, modules: Sequence[str]):
    compositions = []
    for module_name in modules:
        module = importlib.import_module(module_name)
        compositions.append(module.command)
    commander.compose(*compositions)


def noop(*args, **kwargs):
    """ a function that does nothing except accepting everything you throw at it """
    pass


def _undefined_result(obj_key):
    return ValueError('unsupported path key "{}"'.format(obj_key))


def read_object_path(obj, obj_path, default=_undefined_result):
    def _default(exc=None):
        # raises the passed exception if no default value was provided
        # or returns the default value or None in case there’s no
        # exception
        if exc:
            if default is _undefined_result:
                raise exc
            else:
                return default
        else:
            return None if default is _undefined_result else default

    # if the object is None to begin with we just return the default
    if obj is None:
        return _default()

    # try to split one path token from the path and in case that
    # fails assume that the object_path is an attribute name
    try:
        obj_key, new_obj_path = obj_path.split('.', 1)
    except ValueError:
        obj_key, new_obj_path = obj_path, None
    result = _undefined_result

    # try to match one of the key regular expressions
    for matcher in (PATH_ATTRIBUTE, PATH_DICT, PATH_INDEX, PATH_CALL):
        match = re.match(matcher, obj_key)

        # continue with the next regex if we got no match
        if not match:
            continue

        # as all property keys refer to an attribute first
        # lets extract that attribute right now
        try:
            attr = getattr(obj, match.group('attr'))
        except AttributeError as exc:
            return _default(exc)

        if matcher == PATH_ATTRIBUTE:
            # we matched an attribute and already got that
            result = attr
            break
        elif matcher == PATH_DICT:
            # object key referred to a dictionary
            try:
                result = attr[match.group('key')]
            except KeyError as exc:
                return _default(exc)
            break
        elif matcher == PATH_INDEX:
            # object key referred to a sequence
            try:
                result = attr[match.group('index')]
            except IndexError as exc:
                return _default(exc)
            break
        elif matcher == PATH_CALL:
            # object key referred to a function call
            try:
                result = attr()
            except TypeError as exc:
                return _default(exc)
            break

    # none of the matchers matched, so raise an exception
    # if no default has been provided
    if result == _undefined_result:
        return _default(_undefined_result(obj_key))

    # there’s no new object key to process. that’s it!
    if new_obj_path is None:
        return result
    # show must go on. we read the next object key
    # from the result of this run
    else:
        return read_object_path(result, new_obj_path)


def failsafe(exc_type=Exception, enable=True, callback=None):
    """ keep a function from failing
    :param exc_type: the exception type that should be catched
    :param enable: if exception handling should be enabled
    :param callback: an optional callback for processing and on-failure return value
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if enable:
                try:
                    return func(*args, **kwargs)
                except exc_type as exc:
                    if callback:
                        return callback(exc, args, kwargs)
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorator


class FragileStreamHandler(logging.StreamHandler):
    """ simple wrapper around StreamHandler that handles broken output targets gracefully

    This is relevant for interfaces, that may disconnect at any time (e.g. a USB gadget interface).
    Here we need to ignore logging errors.
    """

    def handleError(self, record):
        # silently ignore logging errors
        pass


class CommandExecutionContext(AbstractContextManager):
    """
    Provides a reentrant context manager for controlling the flow of results
    generated by commands.

    It can be used to dynamically intercept exceptions raised by code that
    processes the command results and implement features like back-pressure
    on terminal interface devices.
    """

    ID = '__keen_command_execution_context__'

    def __init__(self):
        self.interceptors = []

    @contextlib.contextmanager
    def intercept(self, interceptor):
        self.interceptors.append(interceptor)
        yield interceptor
        self.interceptors.remove(interceptor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for interceptor in self.interceptors:
            if interceptor.handle(exc_type, exc_val, exc_tb) is True:
                return True
        return False


class BackPressure:
    """
    Base implementation for BackPressure compatible with the interface defined
    by the RunnerContext for intercepting exceptions raised during command result
    processing.
    """
    def handle(self, exc_type, *args):
        # back-pressure is signaled by the internal ShouldThrottleException
        # as a result from a BlockingIOError on the device that is used
        # to write the data to an interface. If we receive a ShouldThrottleException
        # data was written too fast, and we need to increase the back-pressure on
        # the command generating the output.
        if exc_type is not None and issubclass(exc_type, ShouldThrottleException):
            return self.increase()

    def __enter__(self):
        return self

    def __call__(self, iterable: Iterable) -> Iterable:
        """
        :param iterable: The iterable to apply back-pressure on
        """
        raise NotImplementedError()

    def increase(self) -> bool:
        """
        :return: whether or not back-pressure was applied successfully
        """
        raise NotImplementedError()


class RateLimitBackPressure(BackPressure):
    """
    A naive back-pressure implementation that simply drops
    some results when back-pressure increases. By default it
    increases its rate limit by 1 every time the output interfaces
    is blocking, resulting in a reduced data flow.
    """
    def __init__(self, rate_modifier: Union[int, Callable] = 1) -> None:
        """
        :param rate_modifier: controls the change of the rate limit whenever
                              back-pressure is increased. Either an int that
                              is simply added to the existing limit or a callable
                              that receives the current rate limit as only value.
        """
        self.rate_limit = 1
        self.rate_modifier = rate_modifier if callable(rate_modifier) \
            else lambda rate_limit: max(1, rate_limit + rate_modifier)

    def __call__(self, iterable: Iterable) -> Iterable:
        for index, result in enumerate(iterable):
            if index % self.rate_limit == 0:
                yield result

    def increase(self):
        self.rate_limit = self.rate_modifier(self.rate_limit)
        from .runner import logger
        logger.info('Applying back-pressure to command generator. '
                    'Increasing rate limit to %d.' % self.rate_limit)
        return True


def back_pressure(commander, strategy: BackPressure = RateLimitBackPressure):
    """
    Decorator that implements back-pressure for commands. As back pressure always
    means that the amount of data that is generated by the command MUST be reduced
    it should only be used if the command generates results that can be dropped arbitrarily
    or if the back pressure strategy can adequately decide which results are insignificant.

    :param commander: the commander used to register the command
    :param strategy: the back-pressure strategy that should be used to reduce the output flow
    """
    from .commands import require

    def decorator(func):
        @wraps(func)
        @commander.inject(require(CommandExecutionContext, CommandExecutionContext.ID))
        def wrapper(*args, **kwargs):
            context = kwargs.pop(CommandExecutionContext.ID)
            with context.intercept(strategy()) as handler:
                yield from handler(func(*args, **kwargs))
        return wrapper
    return decorator
