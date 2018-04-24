import collections
import itertools
import re

from .validation import validate_value, one_of

TRUE_CHOICES = ('true', '1', 'on', 'yes', 'enable')
FALSE_CHOICES = ('false', '0', 'off', 'no', 'disable')


def transform(**fields):
    def decorator(fn):
        def inner(*args, **kwargs):
            transformed_kwargs = {}
            for field, transformator in fields.items():
                try:
                    transformed_kwargs[field] = transform_value(transformator, kwargs.pop(field))
                except KeyError:
                    transformed_kwargs[field] = None
            return fn(*args, **transformed_kwargs, **kwargs)
        inner.__name__ = fn.__name__
        inner.__doc__ = fn.__doc__
        return inner
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


class Transformable:
    @classmethod
    def transform(cls, value):
        raise NotImplementedError()


class Transformator(Transformable):
    def __init__(self, fn, args, kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def transform(self, value):
        return self.fn(*self.args, value, **self.kwargs)

    def __call__(self, value):
        self.transform(value)


def simple_transformator(fn):
    def decorator(*args, **kwargs):
        transformator = Transformator(fn, args, kwargs)
        transformator.__name__ = fn.__name__
        transformator.__doc__ = fn.__doc__
        return transformator
    decorator.__is_transformator = True
    return decorator


@simple_transformator
def to_bool(value, choices={TRUE_CHOICES, FALSE_CHOICES}):
    true_values, false_values = choices
    validate_value(one_of(true_values + false_values), value)
    if value in true_values:
        return True
    elif value in false_values:
        return False
    else:
        assert False, 'got a value that is neither truthy nor falsy'


@simple_transformator
def from_regex(expr, value, convert_to=tuple):
    match = re.match(expr, value)

    args, kwargs = [], {}
    for index in range(1, match.re.groups + 1):
        args.append(match[index])
    for group, index in match.re.groupindex.items():
        kwargs[group] = match[index]

    return convert_to(*args, **kwargs)


@simple_transformator
def to_enum(enum, value):
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
