import argparse
import sys
from typing import Sequence
from .console import Console
from .events import ConsoleExitEvent
from .utils import autoload
from .error import ParseError, ItemNotFoundError


class ConsoleRunner:
    def __init__(self) -> None:
        self.cli_args = None
        self.console = None
        self.commander = None

    @property
    def prompt(self):
        return '# '

    def get_arg_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.add_argument('--disable-style', dest='disable_style', action='store_true',
                            help='Disable terminal styling (colors).')
        parser.add_argument('--autoload', dest='modules', action='append',
                            help='autoload a module for the interpreter')
        parser.add_argument('--ignore-eof', dest='ignore_eof', action='store_true',
                            help='Ignore the EOF control character (commonly: CTRL-D)')
        parser.add_argument('--simulate', dest='simulate', action='store_true',
                            help='Show which command would have been executed instead of '
                                 'executing it')
        return parser

    def parse_args(self, args: Sequence[str] = None) -> argparse.Namespace:
        args = sys.argv[1:] if args is None else args
        return self.get_arg_parser().parse_args(args)

    def configure(self) -> None:
        self.cli_args = self.parse_args()

    def run(self) -> None:
        self.configure()

        with Console(sys.stdout, prompt=self.prompt) as console:
            console.configure_auto(force_disable_style=self.cli_args.disable_style)
            if self.commander is None:
                raise RuntimeError('You must configure a commander before starting run')
            self.commander.provide('console', console)
            self.commander.provide('terminal', console.terminal)
            if self.cli_args.modules:
                autoload(self.commander, self.cli_args.modules)

            while True:
                try:
                    if not self._process_line(console, self.commander,
                                              ignore_end_of_file=self.cli_args.ignore_eof):
                        break
                except KeyboardInterrupt:
                    # slow / long operations (or repetitions) may be interrupted (without quitting)
                    console.linefeed()

    @staticmethod
    def _process_line(console, commander, ignore_end_of_file) -> bool:
        """ return False if the user signalled exit/quit/EOF """
        prompt = console.get_prompt()
        try:
            if prompt:
                line = input(prompt)
            else:
                line = input()
            console.output.write('\r')
        except EOFError:
            console.linefeed()
            if ignore_end_of_file:
                # silently ignore EOF
                return True
            else:
                # request exit
                return False
        if line:
            try:
                for result in commander.dispatch(line):
                    console.send_data(result)
            except (ItemNotFoundError, ParseError) as exc:
                console.send_error(str(exc))
            except ConsoleExitEvent:
                # the user requested to leave the terminal
                return False
            except OSError as exc:
                # catch remaining (sadly) uncaught exceptions
                console.send_error("An undefined error occured: {}".format(exc))
        return True
