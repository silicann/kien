# kien release changelog

1. UNRELEASED

1. v0.4.1
    * FIX: raise an exception if a dependency injection failed at runtime

1. v0.4.0
  
   * BREAK: signature of CommandResult changed, 
            errors should now be handled via `raise CommandError`
   * BREAK: `Console.send_error` is no longer part of the public API. Use `send_data`
   * FEATURE: add json output-format support
   * FEATURE: add `--failsafe-errors` option to runner that outputs errors 
              if `--failsafe` has been set
   * FEATURE: enable comments prefixed with the `#` character. Comments carry the last
              command status like they do in shells.

1. v0.3.0
  
   * FEATURE: add `failsafe` decorator in utils module
   * FEATURE: add `--failsafe` option to runner keeping the application from exiting
   * FEATURE: output of a result is now terminated with two additional characters.
              The first character is a space (0x20) or a bell (0x07) character depending
              on the success of the command. The second is a null (0x00) character marking
              the end of the result output.
   * FEATURE: add `--history` option for command history support
   * FEATURE: various improvements for integrated help command
   * FEATURE: subclassed Runner instances now have access to the console object
