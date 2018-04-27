from kien import create_commander, var, CommandResult
from kien.command import help, quit
from kien.runner import ConsoleRunner

command = create_commander('destiny’s child')


@command('say', 'my', 'name', var('name'))
def say_my_name(name):
    message = 'baby, i mean {}, i love you'.format(name)
    yield CommandResult(True, message, dict(name=name, message=message))


class MyRunner(ConsoleRunner):
    def configure(self) -> None:
        super().configure()
        root = create_commander('root')
        root.compose(command, help.command, quit.command)
        self.commander = root


if __name__ == '__main__':
    try:
        runner = MyRunner()
        runner.run()
    except KeyboardInterrupt:
        pass
