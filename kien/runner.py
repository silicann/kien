import argparse
import logging
import os
import readline
import sys
from typing import Sequence

import blinker

from .console import Console
from .console.interfaces import InterfaceManager
from .events import ConsoleExitEvent, StopProcessingEvent
from .utils import autoload, failsafe, FragileStreamHandler, CommandExecutionContext
from .error import CommandError, ShouldThrottleException

logger = logging.getLogger('eliza-runner')

on_result = blinker.signal('result')
on_dispatch = blinker.signal('dispatch')
on_error = blinker.signal('error')

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def initialize_pid_file(path):
    """ create a PID file and take care, that it is safely removed when the program exits """
    def cleanup_pid_file():
        """ remove the PID file, if it contains the current process ID

        This prevents our child processes (which inherit our exit caller via "atexit") from
        removing the parent's PID file.
        """
        try:
            with open(path, 'r') as pid_file:
                stored_pid = int(pid_file.read())
        except (OSError, ValueError):
            pass
        else:
            if stored_pid == os.getpid():
                try:
                    os.unlink(path)
                except OSError:
                    pass

    with open(path, 'w') as pid_file:
        pid_file.write(str(os.getpid()))


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
        parser.add_argument('--interface', dest='interfaces', action='append',
                            help=('Bind to the given interface(s) and use these for input and '
                                  'output'))
        parser.add_argument('--pid-file', default=None, type=str, help='write process pid to file')
        parser.add_argument('--log-level', dest='log_level', choices=tuple(LOG_LEVELS),
                            default='warning', help='select log verbosity')
        parser.add_argument('--log-filename-by-process', dest='log_filename_by_process', type=str,
                            help=('Store log messages of forked child processes in separate files '
                                  '(e.g. "/var/log/kien/process-%%d.log"). '
                                  'Log storage per process is disabled by default.'))
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
        logger.setLevel(LOG_LEVELS[self.cli_args.log_level])
        logger.addHandler(FragileStreamHandler(sys.stderr))

        # write pid file if requested (we assume that no later forks will happen)
        if self.cli_args.pid_file:
            initialize_pid_file(self.cli_args.pid_file)

        if not self.cli_args.interfaces:
            # Default to the local terminal via stdin/stdout.
            # Implicitly assume, that we do not need the process manager.
            return
        else:
            # Handle all wanted interfaces with a process manager.
            # allow the empty string for "use current stdin/stdout"
            terminal_dev_specifications = set(None if iface == "" else iface
                                              for iface in self.cli_args.interfaces)
            logger.info("Initializing InterfaceManager")
            interface_manager = InterfaceManager(logger)
            # This method call returns once with a fork for each wanted interface.
            # The manager process itself never returns.
            logger.info("Running InterfaceManager")
            interface_manager.run(terminal_dev_specifications,
                                  log_filename_by_process=self.cli_args.log_filename_by_process)

    def run(self) -> None:
        self.configure()

        with Console(lambda: sys.stdout, prompt=self.prompt) as console:
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
                # Process results generated by dispatching the provided input line.
                # A new CommandExecutionContext is created for every execution and
                # delegates flow control back to the called generator.
                context = CommandExecutionContext()
                with commander.provide(CommandExecutionContext, context) and context:
                    on_dispatch.send(self, line=line)
                    for result in commander.dispatch(line):
                        # As CommandExecutionContext is a reentrant context manager we can
                        # use it multiple times. In this case we want to give the
                        # dispatched callback control over the dispatch mechanism as well
                        # as console write operations
                        with context:
                            on_result.send(self, result=result)
                            console.send_data(result)
            except ShouldThrottleException as exc:
                logger.error('The output interface could not write data fast enough and the '
                             'command sending the data didn’t implement a back-pressure '
                             'mechanism to decrease the data flow. The command was aborted.',
                             exc_info=exc)
                on_error.send(self, exc=exc)
                console.send_data(exc)
            except CommandError as exc:
                on_error.send(self, exc=exc)
                console.send_data(exc)
            except StopProcessingEvent:
                return True
            except ConsoleExitEvent:
                # the user requested to leave the terminal
                return False
        return True
