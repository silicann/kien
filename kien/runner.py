import argparse
import logging
import readline
import sys
from typing import Sequence
from blinker import signal
from .console import Console
from .events import ConsoleExitEvent, StopProcessingEvent
from .utils import autoload, failsafe
from .error import CommandError

logger = logging.getLogger('eliza-runner')

on_result = signal('result')
on_dispatch = signal('dispatch')
on_error = signal('error')


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
        parser.add_argument('--history', default=None,
                            help='Read history from and write it to the specified file')
        parser.add_argument('--ignore-eof', dest='ignore_eof', action='store_true',
                            help='Ignore the EOF control character (commonly: CTRL-D)')
        parser.add_argument('--failsafe', action='store_true',
                            help='keep the application running no matter what '
                                 'runtime exceptions are thrown')
        parser.add_argument('--failsafe-errors', action='store_true',
                            help='in case failsafe is enabled this option will log any unhandled '
                                 'exceptions that are encountered')
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
            self.console = console
            if self.cli_args.modules:
                autoload(self.commander, self.cli_args.modules)
            if self.cli_args.history is not None:
                readline.read_history_file(self.cli_args.history)

            def handle_unhandled_exception(exc, *args):
                if self.cli_args.failsafe_errors:
                    logger.error('unhandled exception', exc_info=exc, extra=dict(callargs=args))
                return True

            # start the application loop
            while True:
                @failsafe(enable=self.cli_args.failsafe, callback=handle_unhandled_exception)
                def _process_line():
                    return self._process_line(console, self.commander,
                                              ignore_end_of_file=self.cli_args.ignore_eof)
                try:
                    if not _process_line():
                        if self.cli_args.history is not None:
                            readline.write_history_file(self.cli_args.history)
                        break
                except KeyboardInterrupt:
                    # slow / long operations (or repetitions)
                    # may be interrupted (without quitting)
                    console.linefeed()

    def _process_line(self, console, commander, ignore_end_of_file) -> bool:
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
                on_dispatch.send(self, line=line)
                for result in commander.dispatch(line):
                    on_result.send(self, result=result)
                    console.send_data(result)
            except CommandError as exc:
                on_error.send(self, exc=exc)
                console.send_data(exc)
            except StopProcessingEvent:
                return True
            except ConsoleExitEvent:
                # the user requested to leave the terminal
                return False
        return True
