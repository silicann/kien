from functools import update_wrapper, wraps
import re
from typing import Any


def validate(**fields):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for field, validator in fields.items():
                try:
                    field_value = kwargs[field]
                except KeyError:
                    continue
                try:
                    validate_value(validator, field_value)
                except ValidationError as exc:
                    exc.field = field
                    raise exc
            return func(*args, **kwargs)
        return wrapper
    return decorator


def validate_value(validator, value):
    if getattr(validator, '__is_validator', False):
        # syntactic sugar for uses of uninstantiated validators
        validator = validator()
    validator.validate(value)


class ValidationError(ValueError):
    def __init__(self, *args: Any, field=None) -> None:
        super().__init__(*args)
        self.field = field


class Validatable:
    @classmethod
    def validate(cls, value):
        raise NotImplementedError()


class _AbstractValidator(Validatable):
    def __call__(self, value):
        self.validate(value)

    def __or__(self, other):
        return _Or(self, other)

    def __and__(self, other):
        return _And(self, other)


class _MultipleValidator(_AbstractValidator):
    def __init__(self, validator) -> None:
        self.validator = validator

    def validate(self, values):
        for value in values:
            validate_value(self.validator, value)


class Validator(_AbstractValidator):
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def validate(self, value):
        self.func(*self.args, value, **self.kwargs)


class _Or(_AbstractValidator):
    def __init__(self, first, second):
        self.first = first
        self.second = second

    def validate(self, value):
        exceptions = []

        def try_value(validator):
            try:
                validate_value(validator, value)
                return True
            except ValidationError as exc:
                exceptions.append(exc)
                return False

        if try_value(self.first):
            return
        elif try_value(self.second):
            return
        else:
            raise ValidationError(' or '.join([str(exc) for exc in exceptions]))


class _And(_AbstractValidator):
    def __init__(self, first, second):
        self.first = first
        self.second = second

    def validate(self, value):
        validate_value(self.first, value)
        validate_value(self.second, value)


def simple_validator(func):
    def decorator(*args, **kwargs):
        validator = Validator(func, args, kwargs)
        update_wrapper(validator, func)
        return validator
    decorator.__is_validator = True
    return decorator


def list_of(validator):
    return _MultipleValidator(validator)


@simple_validator
def is_int(exact, value=None):
    if value is None:
        exact, value = None, exact
    try:
        value = int(value)
    except ValueError as exc:
        raise ValidationError('must be an integer') from exc

    if exact is not None and exact != value:
        raise ValidationError('must be exactly %d' % exact)


@simple_validator
def is_float(exact, value=None):
    if value is None:
        exact, value = None, exact
    try:
        value = float(value)
    except ValueError as exc:
        raise ValidationError('must be a float') from exc

    if exact is not None and exact != value:
        raise ValidationError('must be exactly %d' % exact)


@simple_validator
def is_gte(gte_value, value):
    if not float(value) >= gte_value:
        raise ValidationError('must be greater than or equal to %d' % gte_value)


@simple_validator
def is_gt(gt_value, value):
    if not float(value) > gt_value:
        raise ValidationError('must be greater than %d' % gt_value)


@simple_validator
def is_lte(lte_value, value):
    if not float(value) <= lte_value:
        raise ValidationError('must be less than or equal to %d' % lte_value)


@simple_validator
def is_lt(lt_value, value):
    if not float(value) < lt_value:
        raise ValidationError('must be less than %d' % lt_value)


@simple_validator
def is_between(min, max, value):
    if not (min < float(value) < max):
        raise ValidationError('must be between %d and %d' % (min, max))


@simple_validator
def is_equal(eq_value, value):
    if not eq_value == value:
        raise ValidationError('must be equal to %s' % str(eq_value))


@simple_validator
def identity(id_value, value):
    if id_value is not value:
        raise ValidationError('must be same as %s' % str(id_value))


@simple_validator
def length(value, min=None, max=None, exact=None):
    value_length = len(value)
    if exact is not None and value_length != exact:
        raise ValidationError('length must be %d' % exact)
    if min is not None and value_length < min:
        raise ValidationError('length must be greater than %d' % min)
    if max is not None and value_length > max:
        raise ValidationError('length must be less than %d' % max)


@simple_validator
def one_of(choices, value):
    if value not in choices:
        raise ValidationError('must be one of: %s' % ', '.join(sorted(map(str, choices))))


@simple_validator
def regex(expr, value, message=None):
    if re.fullmatch(expr, value) is None:
        raise ValidationError(message if message is not None else 'has invalid format')
