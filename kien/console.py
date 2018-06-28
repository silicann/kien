import curses
import json
# merely importing readline enable command history via "input"
# noinspection PyUnresolvedReferences
import readline  # noqa: F401
import sys
import termios

import blessings

from .command.set import OutputFormat
from .utils import strip_tags, render_tags


class Console:
    def __init__(self, output, prompt='> ', output_format=OutputFormat.HUMAN):
        self.output = output
        self._prompt = prompt
        self._show_echo = True
        self.terminal = None  # type: blessings.Terminal
        self.linesep = "\n\r"
        self.select_output_format(output_format)
        self._last_status = 0

    def __enter__(self):
        """ store the original settings of the terminal """
        try:
            self._original_console_attributes = termios.tcgetattr(self.output)
        except termios.error:
            # it may fail for piped output
            self._original_console_attributes = None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """ restore the original settings of the terminal """
        if self._original_console_attributes is not None:
            tcsetattr_flags = termios.TCSAFLUSH
            if hasattr(termios, 'TCSASOFT'):
                tcsetattr_flags |= termios.TCSASOFT
            termios.tcsetattr(self.output, tcsetattr_flags, self._original_console_attributes)

    def select_output_format(self, output_format):
        self._output_format = output_format

    def set_echo(self, enabled):
        if self._original_console_attributes is not None:
            attributes = termios.tcgetattr(self.output)
            if enabled:
                attributes[3] |= termios.ECHO
            else:
                attributes[3] &= ~termios.ECHO
            tcsetattr_flags = termios.TCSAFLUSH
            if hasattr(termios, 'TCSASOFT'):
                tcsetattr_flags |= termios.TCSASOFT
            termios.tcsetattr(self.output, tcsetattr_flags, attributes)
        self._show_echo = enabled

    def configure_auto(self, force_disable_style=False):
        """ disable echo for non-interactive sessions """
        self.set_echo(sys.stdin.isatty())
        if self.output.isatty() and not force_disable_style:
            try:
                self.terminal = blessings.Terminal(stream=self.output)
            except curses.error:
                self.terminal = None
        else:
            self.terminal = None

    def linefeed(self):
        if self._show_echo:
            print(file=self.output, end=self.linesep)

    def _format_output(self, s):
        if self.terminal and self.terminal.number_of_colors:
            return render_tags(s, self.terminal)
        else:
            return strip_tags(s)

    def send_data(self, result):
        status = getattr(result, 'status', self._last_status)
        error_code = getattr(result, 'code', None)
        if self._output_format not in OutputFormat:
            raise NotImplementedError('Unknown output format selected: {}'
                                      .format(self._output_format))

        if self._output_format is OutputFormat.HUMAN:
            content = self._format_output(str(result))
        else:
            if self._output_format is OutputFormat.JSON:
                serializer = json.dumps
            else:
                raise NotImplementedError('no serializer for output formatted: {}'
                                          .format(self._output_format))
            content = serializer({
                'data': result.data,
                'status': status,
                'code': error_code
            })

        self._last_status = status
        end = ('\x20' if result.success else '\x07') + '\0' + self.linesep
        print(content, file=self.output, end=end)

    def get_prompt(self):
        if self._output_format == OutputFormat.HUMAN and self._show_echo:
            prompt = self._prompt() if callable(self._prompt) else self._prompt
        else:
            prompt = None
        if prompt and self.terminal:
            def _format(formatter, text, placeholder='___PLACEHOLDER___'):
                format_begin, format_end = formatter(placeholder).split(placeholder)
                # readline will fail to correctly determine the length of the prompt
                # if the prompt uses color codes as is. \001 and \002 are readline
                # escape sequences that will ignore any output in between
                # see: https://stackoverflow.com/a/9468954
                return '\001{format_begin}\002{text}\001{format_end}\002'.format(
                    format_begin=format_begin, text=text, format_end=format_end
                )
            if self._last_status > 0:
                prompt = _format(self.terminal.red, prompt)
            else:
                prompt = _format(self.terminal.blue, prompt)
        return prompt
