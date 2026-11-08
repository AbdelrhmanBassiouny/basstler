"""
The rules on the quality of the code, whatever the project.
"""

from __future__ import annotations

from typing import override

from basstler.class_property import classproperty
from basstler.code_rules.docstring_presence import MissingDocstringChecker
from basstler.code_rules.prose_length import ProseLengthChecker
from basstler.code_rules.rule import CodeReference, Section
from basstler.exceptions import DataclassException
from basstler.locations import PathEnumeration


class CodeQualityRules(Section):
    """
    The rules on the quality of the code, whatever the project.
    """


class RuleApplicationRules(Section):
    """
    The rules on when and how far the other rules apply.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    LEAVE_UNTOUCHED_CODE_ALONE = (
        "Existing code that breaks these rules stays as it is unless a change "
        "touches it or the user asks for the cleanup. When you modify a function or"
        " class, bring that function or class in line with these rules as part of "
        "the change, and leave code the change does not otherwise modify alone. If "
        "the cleanup renames a method and so changes the API, ask the user first"
    )

    ASK_BEFORE_DEPARTING_FROM_A_RULE = (
        "When a rule seems wrong for the case at hand - a failing test that is "
        "itself wrong, an exception that has to be caught, a value that genuinely "
        "has to live at module level - ask the user before departing from it; never"
        " decide the exception on your own"
    )


class RuleModellingRules(Section):
    """
    The rules on writing the rules themselves.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        """
        Nested under :class:`CodeQualityRules`, unlike :meth:`Section.parent`.
        """
        return CodeQualityRules

    SPLIT_OFF_THE_CHECKABLE_PART = (
        "When a script can check part of a rule, split the rule: the checkable "
        "part becomes a rule of its own that carries its checker, and the part "
        "only a person can judge stays a rule without one"
    )


class AskTheDeveloperRules(Section):
    """
    The rules on what to ask the developer instead of deciding.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    ASK_INSTEAD_OF_INVENTING_REASONS = (
        "When you are unsure why something was done or why a specific number was "
        "chosen, ask; never invent a reason and write it down as a comment"
    )

    ASK_ABOUT_TEST_ONLY_METHODS = (
        "When a method is never used outside of tests, ask whether it can be removed"
    )

    ASK_BEFORE_ADDING_DEPENDENCIES = "Before adding a new dependency, ask"

    SUGGEST_MORE_POWERFUL_PACKAGES = (
        "If a package could be replaced by a more powerful one, tell us"
    )

    ASK_BEFORE_WORKING_AROUND_A_DENIAL = (
        "When the permission system or its classifier denies a tool call, never "
        "work around the denial and never drop the step silently: ask the user to "
        "accept it, naming the exact action and why it is needed, and run it only "
        "once they agree"
    )


class TestingRules(Section):
    """
    The rules on tests.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules


class WritingTestsRules(Section):
    """
    The rules on writing tests.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return TestingRules

    WRITE_TESTS_WITH_PYTEST = (
        "Write tests with pytest: plain test functions or classes, pytest fixtures,"
        " `pytest.raises` and plain `assert`"
    )

    REUSE_FIXTURES = "Reuse the existing fixtures in `conftest.py`"

    WORK_TEST_DRIVEN = (
        "Work test-driven: prove a bug with a meaningful, failing test before "
        "fixing it. Every new feature and fix is covered by tests"
    )

    NEVER_MODIFY_A_FAILING_TEST = (
        "When fixing a failing test, never modify the test itself"
    )

    NAME_TEST_CLASSES_AFTER_BEHAVIOUR = (
        "Name test classes, and the mimic classes tests use, after the pattern or "
        "behaviour they exercise, not after the external class they stand in for"
    )

    KEEP_SNIPPETS_IN_FILES = (
        "Keep code snippets in separate files of the correct type and import or "
        "read them into the test; never embed them as strings"
    )


class AssertionsRules(Section):
    """
    The rules on what a test asserts.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return TestingRules

    ASSERT_EXACT_EXPECTED_VALUES = (
        "Assert equality to the expected value whenever it can be determined, never"
        " only a weaker check such as not-None or not-empty"
    )

    ASSERT_AGAINST_THE_DEFINITION = (
        "Assert against the definition, not a retyped copy of it: the enum member, "
        "the `classproperty`, or the value from the fixture the code under test "
        "consumed. Where a type distinguishes the case - a distinct exception "
        "class, an enum member - assert the type instead of matching message text. "
        "A retyped literal keeps passing when the original changes"
    )

    TEST_ONE_BEHAVIOUR = (
        "Each test checks the one behaviour it names and fails only for its own "
        "reason: assert exactly the values that behaviour determines, not "
        "incidental output such as the wording of an error message the test is not "
        "about. Where another test already asserts a value exactly, derive the "
        "expected value from the production code that computes it instead of "
        "hardcoding a second copy. Tests are independent of each other"
    )


class ExternalServicesAndCIRules(Section):
    """
    The rules on tests that reach external services, and on CI.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return TestingRules

    EVERY_TEST_RUNS_IN_CI = (
        "Every added test is part of the CI suite. A test that needs live external "
        "calls or credentials CI does not have is skipped there (or removed, if "
        "new) so it cannot break the pipeline"
    )

    APPROVE_CI_CREDENTIALS = (
        "A test that needs credentials in CI must be approved by the user and have "
        "those credentials available in CI; otherwise it is skipped there"
    )

    MOCK_EXTERNAL_APIS = (
        "Mock external APIs; call one live only to download a dataset other tests need"
    )

    PAIR_LIVE_TESTS_WITH_MOCKED_ONES = (
        "A test that calls an external API live must have a skip condition so it "
        "does not run in CI, and must be paired with an equivalent mocked test that"
        " does"
    )


class RunningTestsRules(Section):
    """
    The rules on running tests.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return TestingRules

    RUN_TESTS_WITH_PYTEST = "Run tests with pytest"

    USE_THE_PROJECT_INTERPRETER = (
        "Always use the project's configured Python interpreter for tests and commands"
    )


class CodeStyleRules(Section):
    """
    The rules on code style.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    RUFF_CHECK_PASSES = (
        "`ruff check .` passes on every change. The rules it enforces are "
        "configured in `pyproject.toml` and not repeated here; never silence a "
        "finding with `noqa` or a new ignore without asking"
    )

    USE_DATACLASSES = (
        "Use dataclasses: pydantic dataclasses for data parsed from outside the "
        "program (an API response, a configuration file, a command's input), plain "
        "dataclasses everywhere else"
    )

    DIVIDE_FILES_INTO_SECTIONS = (
        "Divide every file, source and test, into sections with `# %% <short "
        "description>` headers (e.g. `# %% same-noun disambiguation`), never "
        "decorative box-drawing dividers"
    )

    GROUP_PRIMITIVES_INTO_DATACLASSES = (
        "A group of primitives that travels together, or a return type that keeps "
        "being repeated, becomes a dataclass"
    )

    NEVER_DUPLICATE_CODE = (
        "Never duplicate code. Never put methods in a catch-all module such as "
        "`utils.py`; move them onto the class that owns the behaviour"
    )

    ACCESS_ATTRIBUTES_DIRECTLY = (
        "Access attributes with `.`, never with `getattr`, and never wrap attribute"
        " access in try-except"
    )

    NEVER_REIMPLEMENT = (
        "Never reimplement what the codebase or an existing dependency already "
        "provides. When searching for it, never cut off the output of grep or other"
        " searches; narrow the search instead"
    )


class NamingRules(Section):
    """
    The rules on naming.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeStyleRules

    CORRECT_SIMPLE_DESCRIPTIVE_NAMES = (
        "Names are technically correct, simple and descriptive, in that order. An "
        "inaccurate name is worse than a vague one, because a reader who trusts it "
        "stops reading"
    )

    NAMES_READ_ON_THEIR_OWN = (
        "A name stays correct and understandable when read on its own, without its "
        "class or a keyword argument next to it - after `value = "
        "instance.attribute`, in a log line, in a traceback, or when passed on "
        "positionally. A `Pipe` field `size` says nothing once it leaves the class;"
        " `inner_diameter` does. A generic word that would fit anything never "
        "passes this test"
    )

    USE_PLAIN_WORDS = (
        "Use the plain word every reader already knows. Use a specialist, "
        "metaphorical or in-house term only where it is genuinely the precise word,"
        " never as shorthand between the people who were in the discussion"
    )

    USE_THE_DOMAIN_WORD = (
        "Where the domain or file format already has a word for something, use that"
        " word"
    )

    NEVER_ABBREVIATE = "Never abbreviate an identifier"

    NAME_WHAT_NOT_HOW = (
        "A name says *what* a thing is or does - never *how* it does it, *when* it "
        "runs, or the layer or mechanism it is built on. Keep it short"
    )

    NO_FOREIGN_VOCABULARY = (
        "A name whose meaning has to be looked up elsewhere is wrong. Never adopt "
        "another system's vocabulary as an identifier of ours: name the thing for "
        "what it is here, and explain a foreign shape in the docstring"
    )

    VERB_AND_NOUN_PHRASES = (
        "Methods are verb phrases for what they do; classes and attributes are noun"
        " phrases for what they are. Name a field for its subject, not for the "
        "shape of its value"
    )

    ONE_NAME_PER_OPERATION = (
        "One operation has one name throughout a module. Where callers depend on "
        "that name, declare it in a base class instead of leaving it a convention "
        "each class is trusted to follow"
    )

    NAME_ENUM_MEMBERS_FOR_THEIR_SITUATION = (
        "Name an enum member for the situation it means, not for the function it "
        "dispatches to or the text it renders"
    )

    NO_REPEATED_WORDS = (
        "Never repeat the enclosing type's name in its members, or the same word "
        "twice within one name"
    )

    NEVER_SHADOW_BOUND_NAMES = (
        "Never take an identifier the language or something in scope already binds:"
        " `Enum` reserves `name`, a parameter `field` shadows `dataclasses.field`, "
        "a field shadows a method of the same name. These fail at runtime or "
        "silently, not at import"
    )

    FINISH_RENAMES = (
        "A rename is finished only when every reader of the old name, docstrings "
        "and comments included, uses the new one and the tests pass. A mechanical "
        "rename across a file is exactly where a method and a field converge on one"
        " name"
    )

    SUSPECT_VAGUE_CODE = (
        "When no honest specific name exists, suspect the code, not your "
        "vocabulary: a thing that can only be described vaguely usually has no "
        "single subject (a container for whatever its caller passed, a function "
        "doing two jobs). Remove it instead of hunting for a better word"
    )


class DesignPrinciplesRules(Section):
    """
    The rules on design.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    OBJECT_ORIENTED_AND_SOLID = (
        ("Use strictly object-oriented design and always apply the SOLID principles:"),
        (
            (
                "Single Responsibility: each class and method does one thing. If a "
                "method has cyclomatic complexity in the hundreds, refactor"
            ),
            "Open/Closed: open for extension, closed for modification",
            (
                "Liskov Substitution: subtypes are substitutable for their base "
                "types without breaking behaviour"
            ),
            (
                "Interface Segregation: many small interfaces over one large one. "
                "An interface is an explicit superclass or mixin, never a "
                "`Protocol`"
            ),
            (
                "Dependency Inversion: depend on abstractions, not concrete "
                "implementations"
            ),
        ),
    )

    MODULAR_AND_DECOUPLED = "Keep code modular and decoupled"

    NO_YAGNI = "Eliminate YAGNI smells"

    HARD_TO_MISUSE_INTERFACES = "Make interfaces hard to misuse"

    MODEL_RELATIONSHIPS_IN_THE_SOURCE = (
        "Model the relationship between related concepts in the source, never only "
        "in a test that checks two separate definitions agree: derive one from the "
        "other, or unify them into one concept when that is the cleaner design by "
        "SOLID and the domain's semantics"
    )

    ASSOCIATE_OR_SUBCLASS_FIRST = (
        "Before writing a new class, look for an existing class it can hold as a "
        "field or subclass, and use it; when related classes share fields or "
        "behaviour, give them a common base"
    )


class MethodsRules(Section):
    """
    The rules on methods.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return DesignPrinciplesRules

    EXTRACT_METHODS_THAT_EARN_THEIR_ABSTRACTION = (
        "Every method hides what actually runs from the reader, so extract one only"
        " when its abstraction is worth more than reading the executed code in "
        "place"
    )

    ONE_LEVEL_OF_ABSTRACTION = (
        "Keep every statement in a method on the same level of abstraction: a "
        "method either strings together named steps or carries out one step's "
        "detail, never both"
    )

    NO_FORWARDING_METHODS = (
        "Never write a method that only forwards to or renames another call. A "
        "one-line method is allowed only when it implements an abstract method or a"
        " `classproperty`, caches its result, or removes duplication - and in the "
        "last case, first try to abstract the duplicated code itself"
    )

    INLINE_SINGLE_CALLER_METHODS = (
        "A method with a single caller must earn its place under these rules; "
        "otherwise inline it"
    )

    GUARD_CLAUSES = (
        "Reduce nesting and complexity with guard clauses: handle alternative "
        "outputs first by inverting conditions and returning early, so the main "
        "branch holds the main output and the biggest compute. A single level of "
        "abstraction never justifies deep nesting; split the method instead"
    )


class ErrorsRules(Section):
    """
    The rules on raising and modelling errors.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return DesignPrinciplesRules

    NEVER_TRY_EXCEPT = (
        "Never use try-except; a program in an illegal state raises an appropriate "
        "exception"
    )

    ONE_EXCEPTION_TYPE_PER_FAILURE = (
        "Define a few exception types, one per kind of failure (a git command that "
        "fails, a GitHub request that is refused, a configuration that does not "
        "parse), each a dataclass carrying what the reader needs to fix it. Never a"
        " new class for every place that raises"
    )

    PLACE_IN_THE_CLOSEST_MODULE = (
        (
            "Put each exception in the `exceptions.py` closest to the code that "
            "raises it:"
        ),
        (
            (
                "An exception raised only within one subpackage goes in that "
                "subpackage's `exceptions.py`; create the file if the subpackage "
                "has none"
            ),
            (
                "An exception raised across several subpackages goes in the "
                "`exceptions.py` of their nearest common package"
            ),
        ),
    )

    SUBCLASS_THE_BASE_EXCEPTION = (
        f"Custom exceptions subclass {CodeReference(DataclassException).path}, "
        "implementing its `error_message` and `suggest_correction`"
    )


class ConstantsAndClassLevelValuesRules(Section):
    """
    The rules on constants and values declared on a class.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return DesignPrinciplesRules

    TRUE_CONSTANTS_AT_MODULE_LEVEL = (
        "A true constant - a value no caller would change, such as a limit an "
        "external API sets - is a plain module-level `UPPER_CASE` constant"
    )

    FIXED_SETS_AS_ENUMS = "A fixed set of related values is a module-level enum"

    CHANGEABLE_DEFAULTS_AS_PARAMETERS_OR_FIELDS = (
        "A default a caller may want to change is a parameter of the method that "
        "uses it if only that method does, otherwise a dataclass field with that "
        "default. For example, a `Heater` takes `target_temperature: float = 20.0` "
        "as a field instead of declaring `DEFAULT_TARGET_TEMPERATURE = 20.0`"
    )

    PER_SUBCLASS_VALUES_AS_CLASSPROPERTIES = (
        "A value each subclass declares for itself is a "
        f"{CodeReference(classproperty).path}"
    )

    NO_MUTABLE_MODULE_STATE = (
        "Never keep mutable state at module level. `ClassVar` is allowed only for "
        "state that explicitly has to be shared and mutable across every instance "
        "of a class. This almost never applies"
    )


class StructuredDataRules(Section):
    """
    The rules on structured data over literals.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return DesignPrinciplesRules

    PREFER_STRUCTURED_DATA = (
        "Structured data is the default over bare strings, hardcoded values and "
        "meaningless numbers: reach for the structured form first and justify the "
        "literal, never the other way round"
    )

    FIXED_NAMES_AS_STRING_ENUMS = (
        "A string that names a fixed thing - a state, a label, a filename, an "
        "environment variable, a command flag, a status - is a `StrEnum` member. A "
        "value spelled in two places has no single source to rename, and nothing "
        "fails when the two drift apart"
    )

    PAYLOAD_KEYS_ONLY_IN_THE_MODEL = (
        "A payload is a dataclass, and its keys are spelled only inside that "
        "dataclass: as its field names where they match the payload, otherwise "
        "inside the method that parses or writes it. Never declare an enum of "
        "payload keys for other code to read, and never declare one key in two "
        "places"
    )

    TYPED_ENUM_VALUES = (
        "When the values are more than text - paths, numbers - give the enum values"
        " of that type, mixing the type in (`IntEnum`, `StrEnum`)"
    )

    NO_MAGIC_NUMBERS = (
        "A magic number becomes an enum member, a field default or a named "
        "constant; a bare literal that carries meaning is unreadable where it is "
        "used and unsearchable everywhere else"
    )

    PARSE_EXTERNAL_DATA_AT_THE_BOUNDARY = (
        "Data whose shape someone else controls - an API response, a configuration "
        "file - is parsed into pydantic dataclasses at the boundary, so it is "
        "validated once and the field names and the access path into the payload "
        "are written once"
    )

    NO_POSITIONAL_TUPLES = (
        "A tuple whose positions carry meaning becomes a dataclass, or an enum when"
        " the positions are a fixed set of alternatives rather than fields"
    )

    LONG_LITERALS_IN_FILES = (
        "A long literal document - a query, a template, a schema - lives in a file "
        "of its own type and is read in, never embedded as a string"
    )

    PATH_ENUMS_SUBCLASS_PATH_ENUMERATION = (
        f"A path enum subclasses {CodeReference(PathEnumeration).path}, so every "
        "path derived from a member is a plain `Path`; its members' `name` is the "
        "path's last component, so read the member name as `_name_`"
    )


class TypeHintsRules(Section):
    """
    The rules on type hints.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    ACCURATE_TYPE_HINTS = (
        "Type hints are accurate: `Any` where the value genuinely is anything, "
        "never as a shortcut"
    )

    BOUND_GENERIC_PARAMETERS = (
        "When each class in a family declares the type it handles, carry that type "
        "as a bound generic parameter, not a `ClassVar`, so it is part of the "
        "signature and cannot disagree with a separate attribute: bind it in each "
        "member (`class MemberOfFamily(Family[ConcreteType])`)"
    )


class DocumentationRules(Section):
    """
    The rules on docstrings and comments.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    DOCUMENT_EVERY_CONSTRUCT = (
        "Every module, class, function and field has a docstring. A field's "
        "docstring goes directly below the field, not in the class docstring. A "
        "method implementing an abstract method is exempt: the abstract method's "
        "docstring is enough",
        (),
        MissingDocstringChecker(),
    )

    MEANINGFUL_DOCUMENTATION = (
        "Documentation is written in reStructuredText and says something the name "
        "and the type hints do not: a module's or class's responsibility, a "
        "function's contract, a field's unit or meaning"
    )

    OVERRIDES_INHERIT_DOCSTRINGS = (
        "An implementation of an abstract method has no docstring and inherits the "
        "base one. An override of an implemented method documents only what differs "
        "from the base and references the overridden method with `:meth:`"
    )

    DOCSTRINGS_STATE_THE_CONTRACT = (
        (
            "A docstring states what the code does and its contract, short and to "
            "the point. It never contains:"
        ),
        (
            "how the code does it",
            (
                "the ways a caller can supply a value (for example, that it may "
                "also be given as a query instead of a concrete object)"
            ),
            (
                'the current callers or consumers ("used by X and Y") - that goes '
                "stale and reads as exhaustive"
            ),
            (
                "justification of design decisions, comparison with rejected or "
                "hypothetical designs, or review and implementation history"
            ),
            "type information - the type hints carry it",
        ),
    )

    SHORT_COMMENTS = (
        "Keep docstrings and comments short and never write walls of text. Comments"
        " are meaningful and DRY; remove comments that restate the code"
    )

    SHORTEST_DOCSTRINGS = (
        "Make every docstring as short as it can be: one line where one line says "
        "it. A module's or class's docstring states its responsibility in a sentence "
        "or two; it never lists every step it takes or every case it handles - those "
        "belong to the methods that take them"
    )

    SPHINX_ROLES = (
        "Reference code with Sphinx roles (`:func:`, `:class:`, `:attr:`, "
        "`:meth:`), never with plain backticks, and use directives such as `.. "
        "note::` and `.. warning::` for notes and warnings"
    )

    NO_CAPITALS_FOR_EMPHASIS = (
        "Never use all-caps words for emphasis in docstrings or comments; use RST "
        "emphasis (`*word*`). Genuine identifiers, acronyms and enum/constant names"
        " (`UUID`, `WHERE`, `Definiteness.DEFINITE`) are exempt"
    )

    FORMAT_WITH_THE_HOOK = (
        "Always format modified Python files with `ruff format` followed by "
        "docformatter, through the repository's pre-commit hook "
        "(`scripts/format_docstrings.py`)"
    )

    SHORT_DOCSTRINGS = (
        f"A docstring holds at most {ProseLengthChecker.docstring_lines} lines of "
        "prose, field lists and literal blocks aside, and a comment block at most "
        f"{ProseLengthChecker.comment_lines} lines",
        (),
        ProseLengthChecker(),
    )


class VersionControlRules(Section):
    """
    The rules on commits, pushes and pull requests.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return CodeQualityRules

    AUTHOR_AS_THE_HUMAN = (
        "Author commits as the human user running the tool, with their own "
        "configured git `user.name` and `user.email`. Never author or amend a "
        "commit as an assistant, and never credit one as author or co-author: no "
        "`Co-Authored-By:` trailer for an assistant, no `noreply@anthropic.com` or "
        "similar as author or committer"
    )

    ACKNOWLEDGE_ASSISTANCE_PLAINLY = (
        "A short plain line in the commit message body acknowledging assistant "
        "help, such as `Made with AI assistance`, is encouraged. Never name the "
        "model or the AI service"
    )

    RULES_APPLY_TO_EVERYONE = "These rules apply to every contributor and every tool"

    NEVER_PUSH_UPSTREAM = (
        "When you work in a fork, never push to the upstream repository - no "
        "branch, no tag, whatever the reason. Push only to the fork; work reaches "
        "upstream only through a pull request opened from the fork. Before any "
        "push, read the full, untruncated `git remote -v` output and confirm the "
        "target remote is the fork"
    )

    LEAVE_UPSTREAM_PULL_REQUESTS_ALONE = (
        "Never comment on or modify pull requests on the upstream repository unless"
        " the user has explicitly allowed it - through existing personal notes or "
        "instructions, or by accepting when you ask"
    )
