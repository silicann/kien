import collections
import enum
from itertools import groupby
from typing import List, Sequence, Callable, Any, Optional, Iterator, Set
from blinker import signal
from .validation import validate, validate_value, one_of, ValidationError
from .transformation import transform, transform_value
from .utils import tokenize_args, join_generator_string, TokenMismatch, TaggedString, noop


class _Undefined:
    pass


class CommandResult:
    def __init__(self, success=True, message=None, data=None) -> None:
        self.success = success
        self.data = data

        if message is None:
            raise ValueError('message is required')
        self.message = message

    def __str__(self):
        return self.message


def _is_enum(choices):
    try:
        return issubclass(choices, enum.Enum)
    except TypeError:
        # "choices" is not a class (and thus not an enum)
        return False


class _Token:
    def __init__(self, value=_Undefined, name=None, is_optional=False,
                 greedy=False, transform=None, choices=None, description=None):
        """ specify possible value of a command string token

        @param choices: may be None, an enum or an iterable
        """
        # TODO: greedy should accept integers
        self.value = value
        self.name = name
        self.is_optional = is_optional
        self.greedy = greedy
        self.transform = transform
        self.description = description
        if choices is None:
            self.choices = set()
        elif _is_enum(choices):
            self.choices = {item.value for item in choices}
        else:
            self.choices = set(choices)

    def matches(self, value):
        if self.value is not _Undefined:
            return self.value == value
        if self.name and self.transform:
            # we trigger the token validation here to handle args that
            # have been misspelled and to provide command suggestions
            getattr(self.transform, 'validate', noop)(value)
        if self.name and self.choices:
            # if choices were defined we must validate that the provided
            # value actually is one of those choices
            validate_value(one_of(self.choices), value)
        return True

    def get_label(self, with_error=None):
        def format_greedy(name):
            return '[%s [...]]' % name

        def format_optional(name):
            name = TaggedString.error(name) if with_error else TaggedString.optional(name)
            return '[%s]' % name

        def get_name(token):
            if token.name:
                return token.name.upper()
            if token.value:
                return token.value
            else:
                raise ValueError('cannot derive name from token')

        token = get_name(self)

        if self.greedy:
            token = format_greedy(token)
        if self.is_optional:
            token = format_optional(token)
        if self.name and not self.is_optional:
            token = TaggedString.var(token)

        return token

    def __str__(self):
        return self.get_label()


class _Placeholder(_Token):
    pass


class _Group:
    def __init__(self, name, description=None):
        self.name = name
        self.description = description


def var(name, value=_Undefined, is_optional=False, transform=None, greedy=None,
        choices=None, description=None):
    return _Token(value, name, is_optional, greedy, transform, choices, description)


def optional(value):
    return _Placeholder(value, is_optional=True)


def group(name, description=None):
    return _Group(name, description)


def _find_token(tokens, index):
    if len(tokens) > index:
        return tokens[index]
    elif tokens[-1].greedy:
        return tokens[-1]
    else:
        raise IndexError('invalid token index')


class _MatchType(enum.Enum):
    NONE = None
    INVALID = 'invalid'
    PARTIAL = 'partial'
    EXACT = 'exact'

    def __str__(self):
        if self.value is _MatchType.NONE:
            raise NotImplementedError('please override the match type')
        return {
            _MatchType.INVALID: 'Invalid commands',
            _MatchType.PARTIAL: 'Partial matching commands',
            _MatchType.EXACT: 'Selected command'
        }[self]

    def __lt__(self, other):
        return self.value < other.value


class _CommandMatch:
    type = _MatchType.NONE

    def __init__(self, command):
        self.command = command


class _InvalidCommandMatch(_CommandMatch):
    type = _MatchType.INVALID


class _PartialCommandMatch(_CommandMatch):
    type = _MatchType.PARTIAL

    def __init__(self, command, token=None, token_mismatches: Sequence[TokenMismatch] = tuple()):
        super().__init__(command)
        self.token = token
        self.token_mismatches = token_mismatches


class _ExactCommandMatch(_CommandMatch):
    type = _MatchType.EXACT


class AmbiguousCommandError(RuntimeError):
    def __init__(self, matches: Sequence[_ExactCommandMatch], *args: Any) -> None:
        self.matches = matches
        super().__init__(*args)


class _CommandMatches:
    # todo should probably be a UserList
    def __init__(self, matches: Sequence[_CommandMatch]):
        self.matches = matches

    def describe(self, args, discard_invalid=True) -> str:
        @join_generator_string()
        def _render() -> str:
            yield 'provided args:'
            yield '\t%s' % ' '.join(args)
            yield ''
            exclude = (_MatchType.INVALID, ) if discard_invalid else None
            match_groups = self._filter_matches(exclude=exclude, group=True)
            for match_type, matches in match_groups:
                yield '%s' % str(match_type)
                for match in matches:
                    token_mismatches = getattr(match, 'token_mismatches', None)
                    yield '\t%s' % match.command.get_label(with_errors=token_mismatches)
        return _render()

    def _filter_matches(self, include=None, exclude=None, group=False) -> List[_CommandMatch]:
        def _pluck_type(m):
            return m.type

        def _filter(match):
            if include and _pluck_type(match) in include:
                return True
            if exclude and _pluck_type(match) in exclude:
                return False

        matches = sorted(filter(_filter, self.matches), key=_pluck_type)
        return groupby(matches, key=_pluck_type) if group else matches

    def find_suggestable_matches(self, resolve, args):
        matches = self._filter_matches(include=(_MatchType.EXACT, _MatchType.PARTIAL))
        if matches:
            return matches
        elif not matches and len(args) >= 2:
            new_args = args[:-1]
            return resolve(new_args).find_suggestable_matches(resolve, new_args)
        else:
            return []

    def suggestion(self, resolve, args) -> str:
        @join_generator_string()
        def _render() -> str:
            yield 'Could not find the command for "%s"' % ' '.join(args)
            matches = self.find_suggestable_matches(resolve, args)

            if matches:
                yield 'Did you mean one of:'
                for match in matches:
                    yield '\t%s' % match.command.get_label()
        return _render()

    @property
    def exact_match(self) -> Optional[_ExactCommandMatch]:
        matches = [match for match in self.matches if isinstance(match, _ExactCommandMatch)]
        if len(matches) > 1:
            raise AmbiguousCommandError(matches)
        elif len(matches) == 1:
            return matches[0]
        else:
            return None


class _Command:
    def __init__(self, fn, tokens: List[_Token], parent, is_abstract, group, inject, is_disabled):
        self.fn = fn
        self.tokens = tokens
        self.parent = parent
        self.is_abstract = is_abstract
        self._group = group
        self.inject = inject
        self._is_disabled = is_disabled

    def __call__(self, args, require):
        fn_args = _build_args(self.all_tokens, args)
        inject_args = _build_inject_args(self.all_injections, require)
        try:
            return self.fn(**fn_args, **inject_args)
        except ValidationError as exc:
            if exc.field:
                for token in self.all_tokens:
                    if token.name == exc.field:
                        exc.field = token
                        break
            raise exc

    def __str__(self):
        return ' '.join([str(token) for token in self.all_tokens])

    def match(self, args):
        if not self.is_executable:
            return _InvalidCommandMatch(self)

        tokens = self.all_tokens
        invalid_tokens = []

        for index, arg in enumerate(args):
            # first try to find a matching token for this arg
            try:
                token = _find_token(tokens, index)
            except IndexError:
                # we have more args than this command has tokens
                # so this is clearly invalid. greedy tokens have
                # already been taken into account
                return _InvalidCommandMatch(self)

            try:
                # see if the token matches the arg
                if not token.matches(arg):
                    # if the token does not match we can assume
                    # that this command is not valid
                    return _InvalidCommandMatch(self)
            except ValidationError as exc:
                # if the token matching raises a ValidationError
                # this command might still be valid, but a variable
                # was provided in an incorrect format
                invalid_tokens.append(TokenMismatch(token, exc, arg))

        # we made sure that the provided args match the defined tokens
        # but we may have more tokens. if one of the left over tokens
        # is not optional this command is a partial match
        for token in tokens[len(args):]:
            if not token.is_optional:
                return _PartialCommandMatch(self, token, invalid_tokens)

        if invalid_tokens:
            return _PartialCommandMatch(self, None, invalid_tokens)
        else:
            return _ExactCommandMatch(self)

    def mount(self, parent):
        self.parent = parent

    def get_label(self, with_errors: Sequence[TokenMismatch] = None):
        def find_error(token):
            if with_errors is None:
                return None
            else:
                for mismatch in with_errors:
                    if token == mismatch.token:
                        return mismatch.exception
            return None

        return ' '.join(
            token.get_label(with_error=find_error(token))
            for token in self.all_tokens
        )

    @property
    def is_disabled(self):
        return self._is_disabled(self) if callable(self._is_disabled) \
            else bool(self._is_disabled)

    @property
    def is_executable(self):
        return not self.is_abstract and not self.is_disabled

    @property
    def group(self):
        if self._group:
            return self._group
        if self.parent:
            return self.parent.group
        else:
            return None

    @property
    def all_tokens(self):
        if self.parent:
            return self.parent.all_tokens + self.tokens
        else:
            return self.tokens

    @property
    def all_injections(self):
        if self.parent:
            return self.parent.all_injections + self.inject
        else:
            return self.inject


def _build_inject_args(injections, require):
    result_args = {}
    for injector in injections:
        generator = require(injector.key)
        result_args[injector.inject_as] = list(generator) if injector.collect else next(generator)
    return result_args


def _build_args(tokens, args: Sequence):
    args = list(args)
    result_args = {}
    for token in tokens:
        # we might still have optional tokens but no more args so we
        # stop the processing once we depleted our args
        if len(args) == 0:
            break

        if token.name:
            arg = args[0:] if token.greedy else args.pop(0)
            if token.transform and isinstance(arg, collections.Iterable) and \
                    not isinstance(arg, str):
                result = list(map(lambda x: transform_value(token.transform, x), arg))
            elif token.transform:
                result = transform_value(token.transform, arg)
            else:
                result = arg
            result_args[token.name] = result
        else:
            args.pop(0)
    return result_args


class _Injection:
    def __init__(self, key, inject_as, collect) -> None:
        self.key = key
        self.inject_as = inject_as or key
        self.collect = collect


def require(key=None, inject_as=None, collect=False):
    return _Injection(key, inject_as, collect)


def create_commander(name, description=None):
    commands = []
    context = {}
    static_context = {
        '__commands': commands
    }

    require_signal = signal('require')

    def _collect_commands():
        return filter_public_commands(commands)

    def _resolve_commands(args) -> _CommandMatches:
        return _CommandMatches([cmd.match(args) for cmd in _collect_commands()])

    def _require(key) -> Iterator[Any]:
        if key in static_context:
            yield static_context[key]
        if key in context:
            value, is_getter = context[key]
            yield value() if is_getter else value
        for response in require_signal.send(key):
            receiver, value = response
            if value is not None and receiver is not _require:
                yield from value

    class _provide:
        def __init__(self, key, obj, is_getter=False) -> None:
            self.key = key
            self.obj = obj
            context[key] = (obj, is_getter)

        def __enter__(self):
            pass

        def __exit__(self, *exc):
            if self.key not in context:
                return
            if self.obj is context[self.key][0]:
                context.pop(self.key)

    class Commander:
        provide = _provide

        def __init__(self, name):
            self.name = name
            self.__doc__ = """%s""" % (description or '')
            self.__class__.__name__ = name

        @staticmethod
        def validate(**kwargs):
            return validate(**kwargs)

        @staticmethod
        def transform(**kwargs):
            return transform(**kwargs)

        @staticmethod
        @tokenize_args
        def dispatch(args, simulate=False) -> Iterator[CommandResult]:
            resolved_commands = _resolve_commands(args)

            if simulate:
                yield CommandResult(message=resolved_commands.describe(args))
            elif resolved_commands.exact_match:
                try:
                    yield from resolved_commands.exact_match.command(args, require=_require)
                except ValidationError as exc:
                    yield CommandResult(
                        False,
                        message='Invalid argument{}: {}'.format(
                            ' for field ' + str(exc.field) if exc.field else '', str(exc))
                    )
            else:
                yield CommandResult(False, resolved_commands.suggestion(_resolve_commands, args))

        @classmethod
        def fire(cls, args):
            return list(cls.dispatch(args))

        @staticmethod
        def inject(**requires) -> Callable:
            requires = _normalize_injections(requires)

            def decorator(fn):
                def inner(*args, **kwargs):
                    injections = _build_inject_args(requires, _require)
                    fargs, fkwargs = _fit_args(fn, args, _merge_dicts(injections, kwargs))
                    return fn(*fargs, **fkwargs)
                inner.__name__ = fn.__name__
                inner.__doc__ = fn.__doc__
                return inner
            return decorator

        def __call__(self, *tokens, parent=None, is_abstract=False, group=None, inject=None,
                     is_disabled=False) -> Callable:
            tokens = _normalize_tokens(tokens)
            injections = _normalize_injections(inject)

            def decorator(fn):
                fn_command = _Command(fn, tokens, parent, is_abstract,
                                      group, injections, is_disabled)
                fn_command.__name__ = fn.__name__
                fn_command.__doc__ = fn.__doc__
                fn_command.__commander__ = self
                commands.append(fn_command)
                return fn_command
            return decorator

        def compose(self, *commanders) -> 'Commander':
            for commander in commanders:
                commander.extend(commands, _require)
            return self

        def extend(self, your_commands, your_require) -> 'Commander':
            your_commands.extend(commands)
            require_signal.connect(your_require)
            return self

        def __str__(self):
            return name

    return Commander(name)


def _merge_dicts(*dicts):
    result = {}
    for d in dicts:
        result.update(d)
    return result


def _fit_args(fn, args, kwargs):
    args = list(args)
    fn_args = fn.__code__.co_varnames[:fn.__code__.co_argcount]
    for index, arg in enumerate(fn_args):
        if arg in kwargs:
            args.insert(index, kwargs.pop(arg))
    return args, kwargs


def _normalize_tokens(tokens) -> List[_Token]:
    result = []
    for token in tokens:
        if not isinstance(token, _Token):
            token = _Token(value=token)
        result.append(token)

    return result


def _normalize_injections(injections) -> List[_Injection]:
    result = []

    if injections is None:
        return result

    def normalize_require(key):
        if key.endswith('[]'):
            return key[:-2], True
        else:
            return key, False

    if isinstance(injections, dict):
        for inject_as, value in injections.items():
            if isinstance(value, _Injection):
                value.key = value.inject_as = inject_as
                result.append(require(value.key, inject_as, collect=value.collect))
            else:
                value, collect = normalize_require(value)
                result.append(require(value, inject_as, collect))
    else:
        for injection in injections:
            if not isinstance(injection, _Injection):
                try:
                    key, inject_as = injection.split(':')
                    key, collect = normalize_require(key)
                except ValueError:
                    key, collect = normalize_require(injection)
                    inject_as = key
                injection = require(key, inject_as, collect)
            result.append(injection)
    return result


def filter_public_commands(commands) -> List[_Command]:
    return [command for command in commands if command.is_executable]


def filter_root_commands(commands) -> Set[_Command]:
    return set([command for command in commands if command.parent is None])
