import collections
from functools import update_wrapper, wraps
import itertools
import re
from typing import Callable, Hashable, Iterable, Mapping, Pattern

from .validation import validate_value, one_of

TRUE_CHOICES = ('true', '1', 'on', 'yes', 'enable')
FALSE_CHOICES = ('false', '0', 'off', 'no', 'disable')


def transform(**fields):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            transformed_kwargs = {}
            for field, transformator in fields.items():
                try:
                    transformed_kwargs[field] = transform_value(transformator, kwargs.pop(field))
                except KeyError:
                    transformed_kwargs[field] = None
            return func(*args, **transformed_kwargs, **kwargs)
        return wrapper
    return decorator


def transform_value(transformator, value):
    if isinstance(transformator, collections.Iterable):
        transformators = transformator
    else:
        transformators = [transformator]

    for transformator in transformators:
        if getattr(transformator, '__is_transformator', False):
            # syntactic sugar for uses of uninstantiated transformers
            transformator = transformator()
        value = getattr(transformator, 'transform', transformator)(value)

    return value


class BuildTimeTransformContext:
    _indicator_name = '__takes_transform_context'

    def __init__(self, value, kwargs) -> None:
        self.value = value
        self.kwargs = kwargs

    @classmethod
    def takes_context(cls, func):
        return getattr(func, cls._indicator_name, False) is True

    @classmethod
    def decorate(cls, func, auto_spread):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if auto_spread and len(args) >= 1 and isinstance(args[-1], cls):
                args = list(args)
                context = args.pop()  # type: BuildTimeTransformContext
                return func(*args, context.value, **context.kwargs, **kwargs)
            else:
                return func(*args, **kwargs)
        setattr(wrapper, cls._indicator_name, True)
        return wrapper


def takes_transform_context(auto_spread=True):
    def decorator(func):
        return BuildTimeTransformContext.decorate(func, auto_spread)
    return decorator


class Transformable:
    @classmethod
    def transform(cls, value):
        raise NotImplementedError()


class Transformator(Transformable):
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def transform(self, value):
        return self.func(*self.args, value, **self.kwargs)

    def __call__(self, value):
        self.transform(value)


def simple_transformator(func):
    def decorator(*args, **kwargs):
        transformator = Transformator(func, args, kwargs)
        update_wrapper(transformator, func)
        return transformator
    decorator.__is_transformator = True
    return decorator


@simple_transformator
def to_bool(value, choices=(TRUE_CHOICES, FALSE_CHOICES)):
    true_values, false_values = choices
    validate_value(one_of(true_values + false_values), value)
    if value in true_values:
        return True
    elif value in false_values:
        return False
    else:
        assert False, 'got a value that is neither truthy nor falsy'


@simple_transformator
def from_regex(expr: Pattern, value: str, convert_to: Callable = tuple):
    """
    Takes a regular expression and converts named groups to **kwargs and
    unnamed groups to *args and calls convert_to with them.

    :param expr: the regular expression that will be used to match value
    :param value: the value the arguments should be extracted from
    :param convert_to: the callable that receives *args and **kwargs
    :return:
    """
    match = re.match(expr, value)

    args, kwargs = [], {}
    # when calling .group() the index 0 always returns the full match
    # the actual user defined groups are stored for index 1 - n
    for index in range(1, match.re.groups + 1):
        args.append(match.group(index))
    for group, index in match.re.groupindex.items():
        kwargs[group] = match.group(index)

    return convert_to(*args, **kwargs)


@simple_transformator
def to_enum(enum, value, static_map: Mapping[Hashable, Iterable[str]] = None):
    """
    Converts a literal value to a value from an enum.

    :param enum: the enum the value should be converted to
    :param value: a value that should be mapped to the provided enum
    :param static_map: a static mapping for aliases that should be respected while
                       converting to the enum. Expects an enum value mapped to a
                       an Iterable of str.
    :return: returns the enum value or None
    """
    if static_map is not None:
        for enum_value, mappings in static_map.items():
            if value in mappings:
                value = enum_value
                break
    if value is None:
        return None
    for item in tuple(enum):
        if value == item or value == item.value:
            return item


@simple_transformator
def flatten(value):
    # returning an iterator would be fine, but may
    # cause confusion because once the variable content
    # has been accessed the content is gone
    return list(itertools.chain(*value))


@simple_transformator
def unique(value):
    # we don’t use a set here, because we want to preserve
    # the item order inside the iterable
    result = []
    for item in value:
        if item not in result:
            result.append(item)
    return result
