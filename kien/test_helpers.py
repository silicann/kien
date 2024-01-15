"""helpers for writing tests for kien itself or for software using kien"""

import contextlib
import functools
import io
import os
import threading
import time
import unittest
from typing import Callable, Iterator

from kien.console import Console
from kien.runner import ConsoleRunner


class KienTestRunner:
    """A kien processor for injecting messages and retrieving responses

    Example usage:

        runner = KienTestRunner(my_commander)
        with runner.get_input_resolver() as input_resolver:
            response = input_resolver("hello")
            print(response)
    """

    END_OF_RESPONSE_STRING = "\0"

    def __init__(self, commander, prompt="> "):
        self._commander = commander
        self._prompt = prompt

    @contextlib.contextmanager
    def get_input_resolver(self) -> Iterator[Callable[[str], str]]:
        """return a function for retrieving the response for a request string

        This function and its environment is partly based on threads in order allow
        running the requester and the handler (both are not implemented in async) in
        the same process.
        """

        def get_unbuffered_pipe():
            return (
                os.fdopen(fd, mode, buffering=1) for fd, mode in zip(os.pipe(), "rw")
            )

        kien_input_reader, kien_input_writer = get_unbuffered_pipe()
        kien_output_reader, kien_output_writer = get_unbuffered_pipe()
        console_factory = functools.partial(
            Console,
            kien_output_writer,
            prompt=self._prompt,
            source=kien_input_reader,
        )
        runner = ConsoleRunner(self._prompt, console_factory=console_factory)
        runner.commander = self._commander
        should_stop_event = threading.Event()

        thread = threading.Thread(
            target=lambda: runner.run(should_stop=should_stop_event.is_set)
        )
        thread.start()
        # wait a bit until kien is ready
        runner.wait_for_readiness()

        def resolve_input(incoming: str, timeout: float = 3) -> str:
            """send a message and wait for its response

            This function is executed in a new thread.
            """
            kien_input_writer.write(incoming + runner.console.linesep)
            if timeout is not None:
                timeout_until = time.monotonic() + timeout
            response = io.StringIO()

            def wait_for_response():
                while (timeout is None) or (time.monotonic() < timeout_until):
                    received = kien_output_reader.read(1)
                    if not received:
                        time.sleep(timeout / 1000)
                        continue
                    try:
                        end_position = received.index(self.END_OF_RESPONSE_STRING)
                    except ValueError:
                        # still waiting for the end
                        response.write(received)
                    else:
                        response.write(received[:end_position])
                        break

            thread = threading.Thread(target=wait_for_response)
            thread.start()
            thread.join()
            return response.getvalue()

        try:
            yield resolve_input
        finally:
            # signal the console runner to stop after the next line of input
            should_stop_event.set()
            # force the runner to process an line in order to finish the loop
            kien_input_writer.write(runner.console.linesep)
            thread.join()
            # close all open pipe-related streams
            for open_file in (
                kien_input_writer,
                kien_output_reader,
                kien_input_reader,
                kien_output_writer,
            ):
                try:
                    open_file.close()
                except OSError:
                    pass


class KienTest(unittest.TestCase):
    """base class for tests involving a kien processor"""

    # every instance needs to overwrite this with its own commander
    commander = None

    def setUp(self):
        assert (
            self.commander is not None
        ), f"Missing 'commander' value in KienTest instance ({self})"
        self._runner = KienTestRunner(self.commander)

    def get_response(self, request: str) -> str:
        with self._runner.get_input_resolver() as input_resolver:
            return input_resolver(request)
