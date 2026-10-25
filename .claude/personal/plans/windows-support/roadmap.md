# windows-support - standing rules

- Each fix is a bug PR off main with the bug label, fixing one root cause, proven first by a failing test that mocks the platform where Linux CI cannot reproduce it.
- No fix introduces a new bare program name in a subprocess call: a program is resolved to a full path once, on the class that owns running it.
