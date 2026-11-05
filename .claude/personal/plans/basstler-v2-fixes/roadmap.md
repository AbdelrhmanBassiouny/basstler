# basstler-v2-fixes — standing rules

- Each fix is its own bug pull request off main, fixing one root cause with a failing test first.
- Fix only what the report hit; anything larger belongs to basstler-v3.
- With no upstream_repository, maintenance board and restack use the clone's own remote as base source (as catch_up_checkout does with BaseSource.own_remote_of) and skip only promotion and upstream reads, saying so, instead of exiting 11. The gathering doc's stack pass then runs there. Bug PR off main.
