# fmt: off
import curses
import fcntl
import json

# merely importing readline enable command history via "input"
# noinspection PyUnresolvedReferences
import readline  # noqa: F401
import struct
import sys
import termios
import tty
import typing

# fmt: on
from io import UnsupportedOperation

import blessings

from ..command.set import OutputFormat
from ..error import ShouldThrottleException
from ..utils import render_tags, strip_tags

# The size of unsigned short is platform-dependent, but guaranteed to be at least two
# bytes.
# As struct.pack seems to enforce portability across architectures, we use a value
# that is always going to fit in that.
UNSIGNED_SHORT_MAX = 65535
TERMINAL_SIZE_MAX = struct.pack("HHHH", UNSIGNED_SHORT_MAX, UNSIGNED_SHORT_MAX, 0, 0)

IndirectIO = typing.Callable[[], typing.TextIO] | typing.TextIO


class Console:
    def __init__(
        self,
        output: IndirectIO,
        prompt: str = "> ",
        output_format: OutputFormat = OutputFormat.HUMAN,
        source: IndirectIO = sys.stdin,
    ):
        """initialize a console environment

        @param output: output file (e.g. sys.stdout) or callable returning such a file
        @param prompt: the prompt string to be output in front of every line
            (with "echo" enabled)
        @param output_format: the initial output format to be used by the interface
        """
        self._given_output = output
        self._given_source = source
        self._prompt = prompt
        self._show_echo = True
        self.terminal = None  # type: blessings.Terminal
        self.linesep = "\n"
        self.select_output_format(output_format)
        self._last_status = 0

    @property
    def output(self):
        """allow the use of a callable as an "output" source

        This ability is relevant for files, that may be replaced during runtime
        (e.g. disconnected USB gadget host).
        """
        if callable(self._given_output):
            return self._given_output()
        else:
            return self._given_output

    @property
    def source(self) -> typing.TextIO:
        """allows to define a callable as an "input" source"""
        if callable(self._given_source):
            return self._given_source()
        else:
            return self._given_source

    def read_input_line(self) -> str:
        """emit the prompt (if non-empty) to output and read one input line from source

        May raise EOFError.
        Return the received string without the trailing line separator.
        """
        prompt = self.get_prompt()
        if prompt:
            self.output.write(prompt)
            self.output.flush()
        source = self.source
        if source == sys.stdin:
            return input()
        else:
            # generic text IO
            received = source.readline()
            if not received:
                raise EOFError
            return received.rstrip(self.linesep)

    def __enter__(self):
        """store the original settings of the terminal"""
        try:
            self._original_console_attributes = termios.tcgetattr(self.output)
        except (termios.error, UnsupportedOperation):
            # it may fail for piped output
            self._original_console_attributes = None
        # Increase window size as seen from the kernel to its maximum value.
        # This will prevent the canonical line editor from inserting a \r character
        # (carriage return) after it reached the window with, causing the line not to
        # wrap, but to overwrite any input that already has been provided (technically
        # it is not overwritten, as the input buffer will still append new data, but
        # that is not entirely transparent to the user).
        # At the point of this change this did not seem to cause any problems with the
        # clients on the other end, as they simply wrap the canonical editor line into
        # the next line which is, in contrast to the inserted carriage return, exactly
        # what we want.
        try:
            fcntl.ioctl(self.output, termios.TIOCSWINSZ, TERMINAL_SIZE_MAX)
        except (OSError, UnsupportedOperation):
            pass
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """restore the original settings of the terminal"""
        if self._original_console_attributes is not None:
            tcsetattr_flags = termios.TCSAFLUSH
            if hasattr(termios, "TCSASOFT"):
                tcsetattr_flags |= termios.TCSASOFT  # type: ignore
            termios.tcsetattr(
                self.output, tcsetattr_flags, self._original_console_attributes
            )

    def select_output_format(self, output_format):
        self._output_format = output_format

    def set_echo(self, enabled):
        if self._original_console_attributes is not None:
            attributes = termios.tcgetattr(self.output)
            if enabled:
                attributes[tty.LFLAG] |= termios.ECHO
            else:
                attributes[tty.LFLAG] &= ~termios.ECHO
            tcsetattr_flags = termios.TCSAFLUSH
            try:
                tcsetattr_flags |= termios.TCSASOFT  # type: ignore
            except AttributeError:
                # TCASOFT is not supported on all platforms
                pass
            termios.tcsetattr(self.output, tcsetattr_flags, attributes)
        self._show_echo = enabled

    def configure_auto(self, force_disable_style=False):
        """disable echo for non-interactive sessions"""
        self.set_echo(self.source.isatty())
        if self.output.isatty() and not force_disable_style:
            try:
                self.terminal = blessings.Terminal(stream=self.output)
            except curses.error:
                self.terminal = None
        else:
            self.terminal = None

    def linefeed(self):
        if self._output_format is OutputFormat.HUMAN:
            self.output.write(self.linesep)
            self.output.flush()

    def _format_output(self, s):
        if self.terminal and self.terminal.number_of_colors:
            return render_tags(s, self.terminal)
        else:
            return strip_tags(s)

    def send_data(self, result):
        status = getattr(result, "status", self._last_status)
        error_code = getattr(result, "code", None)
        if self._output_format not in OutputFormat:
            raise NotImplementedError(
                "Unknown output format selected: {}".format(self._output_format)
            )

        if self._output_format is OutputFormat.HUMAN:
            content = self._format_output(str(result))
        else:
            if self._output_format is OutputFormat.JSON:
                serializer = json.dumps
            else:
                raise NotImplementedError(
                    "no serializer for output formatted: {}".format(self._output_format)
                )
            content = serializer(
                {"data": result.data, "status": status, "code": error_code}
            )

        self._last_status = status
        end = ("\x20" if result.success else "\x07") + "\0"

        try:
            self.output.write(content + end)
            self.output.flush()
            self.linefeed()
        except BlockingIOError as exc:
            raise ShouldThrottleException() from exc

    def get_prompt(self) -> str | None:
        if self._output_format == OutputFormat.HUMAN and self._show_echo:
            prompt = self._prompt() if callable(self._prompt) else self._prompt
        else:
            prompt = None
        if prompt and self.terminal:

            def _format(formatter, text, placeholder="___PLACEHOLDER___"):
                format_begin, format_end = formatter(placeholder).split(placeholder)
                # readline will fail to correctly determine the length of the prompt
                # if the prompt uses color codes as is. \001 and \002 are readline
                # escape sequences that will ignore any output in between
                # see: https://stackoverflow.com/a/9468954
                return "\001{format_begin}\002{text}\001{format_end}\002".format(
                    format_begin=format_begin, text=text, format_end=format_end
                )

            if self._last_status > 0:
                prompt = _format(self.terminal.red, prompt)
            else:
                prompt = _format(self.terminal.blue, prompt)
        return prompt
