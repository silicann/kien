# kien release changelog

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
* FEATURE: Regex decorator now supports an optional message.

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
