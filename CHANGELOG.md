# kien release changelog

## v0.17.0

* FEATURE: Allow to *not* use STDIN for reading the input.
* FEATURE: Add minimal test environment for unittests of applications using kien.


## v0.16.0

* FEATURE: Loads of packaging improvements.


## v0.15.2

* FIX:     Properly declared dependencies for pip-based installation.


## v0.15.1

* FIX:     Decouple terminal output width handling from help text generation.


## v0.15.0

* FEATURE: Allow command parent to be specified as first positional argument.
* FEATURE: Support paragraphs (defined line wrapping) in help texts.


## v0.14.0

* FEATURE: Allow command handlers to omit yielding a `CommandResult` if no response is required.


## v0.13.1

* FIX:     Remove previously generated PID file when exiting the process.


## v0.13.0

* FIX:     Proper help message for log output filename selection.
* FIX:     Emit the line feed only for human-readable output.
* FIX:     Do not emit a hard-coded `\r` after reading an input line.
* FEATURE: Introduce `CommandExecutionContext` for improved exception handling.
* FEATURE: Introduce `back_pressure` indication for controlling data flow.


## v0.12.4

* FIX:     Prevent input editors from emitting a line break after long lines by increasing the
           windows width of the terminal.
* BREAK:   Change default line separator from `\n\r` to `\n`.


## v0.12.3

* FIX:     Emit validation error messages with a stable sorting of exepected inputs.


## v0.12.2

* FIX:     Compatibility with Python before v3.6.


## v0.12.1

* FIX:     Deterministic processing of boolean values.


## v0.12.0

* FIX:     Remove trailing padding whitespace in column-style output.
* FEATURE: Add optional "formatter" parameter to "join_generator_string".


## v0.11.1

* FIX:     `regex` validator will always match the full string
           (replaced `re.match` with `re.fullmatch`)

## v0.11.0

* FEATURE: Add "--log-level" commandline parameter.
* FEATURE: Add "--log-filename-by-process" commandline parameter.
* FIX:     Improve various details of SIGHUP (disconnect/connect) handling.

## v0.10.0

* FEATURE: Manage connections on different interfaces with a single startup process
           (spawning forked processes for each interface).
* FEATURE: Add support for writing and remove a PID file.
* FEATURE: Allow configuration of baudrate.

## v0.9.1

* FIX:     Force inclusion of package metadata.

## v0.9.0

* FEATURE: The new `--tty` option accepts a device and will setup a proper terminal on it.
           When it’s used in conjunction with the `--reconnect-on-hangup` flag it can
           also be used for USB devices that would terminate after the `SIGHUP` process
           signal that is emitted, after a physical USB connection has been severed. 

## v0.8.0

* FEATURE: Command keywords can be aliased from now on. See the `keyword` function.
* FEATURE: `to_enum` transform now accepts a static map of enum to alias values. 
           Combined with the new `keyword` function this allows for easy 
           command aliases.  

## v0.7.0

* FIX:     `set echo` command now lists possible values for `STATE` variable.
* FEATURE: The command decorator now uses the decorated function as lookup object for 
           any unknown attributes that are referenced.
* FEATURE: `regex` validator now supports an optional message.

## v0.6.0

* FIX:     Kien uses `functools.wraps` for decorators now.
* FEATURE: Improve command suggestions for partial command matches with too few arguments
* FEATURE: Transforms can request the transformation context with the `takes_transform_context` 
           decorator now. This is helpful for transforms that are dependent on the result of
           transforms that ran before.

## v0.5.0

* FIX:     The inject mechanism correctly handles default arguments now.
* FIX:     If the last command didn’t carry a status code keep the one that was issued before.
* FEATURE: Take exact argument matches into account when displaying command suggestions.
* FEATURE: Add `on_result`, `on_dispatch` and `on_error` event hooks.

## v0.4.1

* FIX:     Raise an exception if a dependency injection failed at runtime.

## v0.4.0
  
* BREAK:   Signature of CommandResult changed, errors should now be handled 
           via `raise CommandError`.
* BREAK:   `Console.send_error` is no longer part of the public API. Use `send_data`.
* FEATURE: Add json output-format support.
* FEATURE: Add `--failsafe-errors` option to runner that outputs errors
           if `--failsafe` has been set.
* FEATURE: enable comments prefixed with the `#` character. Comments carry the last 
           command status like they do in shells.

## v0.3.0
  
* FEATURE: Add `failsafe` decorator in utils module.
* FEATURE: Add `--failsafe` option to runner keeping the application from exiting.
* FEATURE: Output of a result is now terminated with two additional characters.
           The first character is a space (`0x20`) or a bell (`0x07`) character depending
           on the success of the command. The second is a null (`0x00`) character marking
           the end of the result output.
* FEATURE: Add `--history` option for command history support.
* FEATURE: Various improvements for integrated help command.
* FEATURE: Subclassed Runner instances now have access to the console object.
