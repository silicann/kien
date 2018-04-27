import random

from kien import create_commander, var, CommandResult
from kien.command import help, quit
from kien.runner import ConsoleRunner
from kien.validation import regex, is_int

THEIR_NAMES = (
    'Beyoncé Knowles',
    'Kelly Rowland',
    'Michelle Williams',
    'LaTavia Roberson',
    'LeToya Luckett',
    'Farrah Franklin',
)

command = create_commander('destiny’s child')


@command('say', is_abstract=True)
def say_base():
    # did we mention that you can define arbitrary abstract commands?
    # why? because you can define otherwise recurring keywords and variables.
    # isn’t that nice?!
    pass


@command('my', 'name', var('name', is_optional=True), parent=say_base)
@command.inject(names='members')
@command.validate(name=regex(r'^[a-z]+$') | is_int(11))
def say_my_name(names, name=None):
    if name is None:
        name = random.choice(names)
    message = 'baby, i mean {}, i love you'.format(name)
    yield CommandResult(True, message, dict(name=name, message=message))


class MyRunner(ConsoleRunner):
    @property
    def prompt(self):
        return 'i have a prompt # '

    def configure(self) -> None:
        super().configure()
        root = create_commander('root')
        root.compose(command, help.command, quit.command)
        root.provide('members', THEIR_NAMES)
        self.commander = root


if __name__ == '__main__':
    try:
        runner = MyRunner()
        runner.run()
    except KeyboardInterrupt:
        pass
