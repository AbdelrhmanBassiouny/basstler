# cyclopts-migration - standing rules

- Follow basstler.stack (#131) and basstler.plan (#142): each command is a function whose docstring is its help, option names come from the module's StrEnum, and the tokens are passed as sys.argv[1:] with result_action="return_value".
- Commands, options and exit statuses do not change; usage errors exit 2, and a refusal is a CommandFailure caught once in main.
