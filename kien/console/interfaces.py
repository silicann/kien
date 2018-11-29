import fcntl
import os
import signal
import sys
import termios
import urllib.parse


from ..utils import FragileStreamHandler


def _parse_value_from_string(value, target_type):
    if target_type is bool:
        if value.lower() in {"0", "off", "no", "false"}:
            return False
        elif value.lower() in {"1", "on", "yes", "true"}:
            return True
        else:
            raise ValueError
    elif target_type is int:
        # may raise ValueError
        return int(value)
    else:
        raise NotImplementedError


def get_interface_handler(specification, logger):
    if specification is None:
        return LocalInterface()
    parsed = urllib.parse.urlparse(specification)
    kwargs = dict(urllib.parse.parse_qsl(parsed.query))
    if parsed.scheme == "tty":
        parser_map = {"reconnect_on_hangup": bool, "baudrate": int}
        handler = TTYInterface
        args = (parsed.path, )
    elif parsed.scheme == "telnet":
        parser_map = {"port": int}
        if ":" in parsed.path:
            host, kwargs["port"] = parsed.path.split(":", 1)
        else:
            host = parsed.path
        handler = TelnetInterface
        args = (host, )
    # parse and convert values
    for key, target_type in parser_map.items():
        if key in kwargs:
            try:
                kwargs[key] = _parse_value_from_string(kwargs[key], target_type)
            except ValueError as exc:
                raise InvalidInterfaceSpecificationError(
                    "Failed to identify {} value of '{}': {}"
                    .format(target_type.__name__, key, kwargs[key])) from exc
    # create an instance of the handler
    try:
        return handler(logger, *args, **kwargs)
    except TypeError as exc:
        raise InvalidInterfaceSpecificationError("Failed to instantiate terminal handler ({}): {}"
                                                 .format(handler.__class__.__name__, exc)) from exc


class InvalidInterfaceSpecificationError(Exception):
    """ Indicate an invalid terminal specification (e.g. unknown scheme or missing arguments) """


class BaseInterface:
    """ interface implementations are supposed to reconfigured sys.stdin and sys.stdout

    The details of the interfaces should be hidden well, in order to allow its users to keep using
    the builtins "input()" and "print()".
    """

    def __init__(self, logger):
        self.logger = logger

    def connect(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class LocalInterface(BaseInterface):
    """ communicate directly with stdin and stdout """

    def connect(self):
        pass

    def close(self):
        pass

    def __str__(self):
        return ("Local")


class TTYInterface(BaseInterface):

    def __init__(self, logger, path, baudrate=115200, reconnect_on_hangup=True):
        super().__init__(logger)
        self.path = path
        self.baudrate = baudrate
        self.is_initialized = False
        self.reconnect_on_hangup = reconnect_on_hangup
        if self.baudrate is not None:
            # Try to import the module early: errors in "connect" are much harder to debug, since
            # they are running in a separate process without stderr.
            import serial
            try:
                self.baudrate_tcattr_value = serial.Serial.BAUDRATE_CONSTANTS[self.baudrate]
            except KeyError:
                InvalidInterfaceSpecificationError("Non-standard baudrates are not supported: {}"
                                                   .format(self.baudrate))

    def connect(self):
        def _sighup_handler(sig, frame):
            self.logger.info("Received SIGHUP: reconnecting to %s", self)
            self.connect()
        if not self.is_initialized:
            # execute all preparations (e.g. forking) for acquiring our terminal later on
            self._become_session_leader()
            if self.reconnect_on_hangup:
                # survive a SIGHUP signal, if requested (useful for USB interfaces)
                self.logger.info("Registring SIGHUP handler for reconnect")
                signal.signal(signal.SIGHUP, _sighup_handler)
            self.is_initialized = True
        self._acquire_controlling_terminal()

    def close(self):
        sys.stdin.close()
        sys.stdout.close()

    @staticmethod
    def _become_session_leader():
        """ replicate the effect of the helper program 'setsid ...' """
        try:
            os.setsid()
        except PermissionError:
            # We need to fork in order to be able to create our own session group.
            if os.fork() != 0:
                # the parent process may die
                sys.exit()
            else:
                os.setsid()

    def _acquire_controlling_terminal(self):
        """ fork the process in order to become session leader and replace stdin/stdout/stderr

        The result should be comparable with running the program via "setsid -w agetty ...".
        """
        # TODO: the flags are just copied from agetty's behaviour
        self.logger.debug("Opening target terminal: %s", self.path)
        dev = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_LARGEFILE)
        self.logger.debug("Closing stdin and stdout")
        for handle in (sys.stdin, sys.stdout):
            try:
                handle.close()
            except OSError:
                # For unknown reasons this seems to happen for stdout from time to time.
                # How to reproduce: disconnect the USB peer in a USB gadget setup for a short very
                # period.
                self.logger.info("Failed to close handle: %s", handle)
        self.logger.debug("Disabling controlling terminal")
        fcntl.ioctl(dev, termios.TIOCSCTTY, 0)
        # duplicate the open handle to stdin and stdout
        self.logger.debug("Assigning terminal to stdin and stdout")
        os.dup2(dev, 0)
        os.dup2(dev, 1)
        # replace the text-based stdin/stdout handles
        sys.stdin = open(0, "rt", buffering=1)
        sys.stdout = open(1, "wt", buffering=1)
        # apply some useful settings for an interactive terminal
        self.logger.debug("Applying interactive terminal settings")
        term_settings = termios.tcgetattr(dev)
        # output: new line should also include a carriage return
        term_settings[3] = term_settings[3] | termios.ONLCR
        if self.baudrate is not None:
            term_settings[4] = self.baudrate_tcattr_value
            term_settings[5] = self.baudrate_tcattr_value
        termios.tcsetattr(dev, termios.TCSADRAIN, term_settings)
        os.close(dev)

    def __str__(self):
        return ("TTY (dev={}, baudrate={:d}, reconnect_on_hangup={})"
                .format(self.path, self.baudrate, self.reconnect_on_hangup))


class TelnetInterface(BaseInterface):

    def __init__(self, logger, host, port=None):
        super().__init__(logger)
        raise NotImplementedError


class InterfaceManager:

    def __init__(self, logger):
        self.running_interface_processes = {}
        self.logger = logger

    def run(self, wanted_interfaces, log_filename_by_process=None):
        """ fork processes for each wanted interface

        This function returns for the child processes (i.e.: they may continue using stdin/stdout).
        The parent process (the interface manager) stays alive and never returns.
        """
        if not self.run_and_stop_interfaces(
                wanted_interfaces, log_filename_by_process=log_filename_by_process):
            # we are a managed interface process - simply return
            return
        # we are the manager
        # Ignore all signals that we want to listen for, but store their previous handlers.
        original_signal_handlers = {}
        for one_signal in {signal.SIGUSR1, signal.SIGHUP, signal.SIGTERM, signal.SIGCHLD}:
            # The signal handler signal.SIG_IGN is not appropriate: it would prevent "sigwaitinfo"
            # below from capturing these signals.
            original_signal_handlers[one_signal] = signal.signal(one_signal, lambda *args: None)
        should_finish = False
        while not should_finish:
            try:
                signal_info = signal.sigwaitinfo(set(original_signal_handlers))
            except KeyboardInterrupt:
                self.logger.info("Received CTRL-C")
                should_finish = True
                continue
            if signal_info.si_signo == signal.SIGTERM:
                self.logger.info("Received termination signal")
                should_finish = True
            elif signal_info.si_signo == signal.SIGCHLD:
                # a child process signals its termination
                matched_specs = {spec for spec, pid in self.running_interface_processes.items()
                                 if pid == signal_info.si_pid}
                for spec in matched_specs:
                    self.logger.info("A child signals its termination: %d %s",
                                     signal_info.si_pid, spec)
                    self.running_interface_processes.pop(spec)
                    # in any case: retrieve its result (otherwise it will end up as a zombie)
                    os.waitpid(signal_info.si_pid, os.WNOHANG)
                if not self.running_interface_processes:
                    self.logger.info("All child processes are gone. Going home, too.")
                    should_finish = True
            elif signal_info.si_signo == signal.SIGUSR1:
                # print all currently running processes
                for spec, pid in self.running_interface_processes.items():
                    print("{:d}\t{}".format(pid, spec))
            elif signal_info.si_signo == signal.SIGHUP:
                # Parse the wanted set of interfaces from a given text file and update the list of
                # running processes appropriately.
                raise NotImplementedError(
                    "The 'update interfaces from file' feature is not supported, yet.")
            else:
                raise NotImplementedError("Received unknown signal")
        # kill all child processes
        self.run_and_stop_interfaces(set())
        sys.exit(0)

    def run_and_stop_interfaces(self, wanted_interfaces, log_filename_by_process=None):
        """ kill old processes or start new ones

        @param wanted_interfaces: list of text-based interface specifications
        @param log_filename_by_process: filename template (including "%d" for the PID) to be used
            as a location for storing log message of all child processes. Disabled if undefined.
        """
        running_set = set(self.running_interface_processes)
        obsolete_interfaces = running_set.difference(wanted_interfaces)
        new_wanted_interfaces = wanted_interfaces.difference(running_set)
        if obsolete_interfaces:
            self.logger.info("Terminating processes of obsolete interfaces: %s",
                             obsolete_interfaces)
        # kill obsolete child processes
        for obsolete in obsolete_interfaces:
            child_pid = self.running_interface_processes.pop(obsolete)
            try:
                os.kill(child_pid, signal.SIGTERM)
            except OSError:
                self.logger.warning("Failed to kill obsolete child process: %d (%s)",
                                    child_pid, obsolete)
        # parse the specifications first (reduced risk of leaving a broken mess)
        if new_wanted_interfaces:
            self.logger.info("Starting processes for new interfaces: %s", new_wanted_interfaces)
        interface_handlers = {}
        for new_spec in new_wanted_interfaces:
            try:
                handler = get_interface_handler(new_spec, self.logger)
            except InvalidInterfaceSpecificationError as exc:
                self.logger.error("Failed to parse interface specification ('%s'): %s",
                                  new_spec, exc)
                sys.exit(1)
            else:
                interface_handlers[new_spec] = handler
        # start new processes and memorize their PIDs
        for spec, handler in interface_handlers.items():
            child_pid = os.fork()
            if child_pid == 0:
                # we are the child
                # Release the (shared) error output file.
                sys.stderr.close()
                try:
                    os.close(2)
                except OSError:
                    pass
                sys.stderr = open(os.path.devnull, "wt")
                # connect to our target interface
                handler.connect()
                # optionally redirect stderr for logging
                if log_filename_by_process:
                    sys.stderr.close()
                    sys.stderr = open(log_filename_by_process % os.getpid(), "wt")
                # our logging handler also influences the logging handler of the interface
                self.reconfigure_logging()
                self.logger.info("Spawned process %d for interface: %s", os.getpid(), handler)
                # there is nothing more to be prepared by us - the logic handler may take over
                return False
            else:
                # we are the parent
                self.running_interface_processes[spec] = child_pid
        # only the parent ends up here
        return True

    def reconfigure_logging(self):
        """ remove all existing log handlers and add a stream handler to stderr (if open) """
        self.logger.debug("Reconfiguring logging")
        for handler in self.logger.handlers:
            self.logger.removeHandler(handler)
        if sys.stderr.closed:
            # there is no output target available - do nothing
            pass
        else:
            self.logger.addHandler(FragileStreamHandler(sys.stderr))
        self.logger.debug("Finished reconfiguring logging")
