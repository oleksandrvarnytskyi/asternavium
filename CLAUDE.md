# AsterAvium

Modular platform for astrology, numerology and traditional knowledge systems: deterministic calculation engines + structured knowledge base + AI interpretation layer.

## Commands

- Install: `uv sync`
- Test all: `uv run pytest`
- Test one: `uv run pytest tests/path/test_file.py::test_name -x`
- Lint + format: `uv run ruff check --fix . && uv run ruff format .`
- Type check: `uv run mypy src`
- Docs: `uv run sphinx-build -W docs docs/_build`

Run lint, type check and the relevant tests before declaring a task done. Fix failures; never silence them with `# type: ignore` or `# noqa` without a one-line justification.

## Architecture (do not violate)

Project structure is still taking shape; keep these principles until it is defined:

- Each tradition is an independent module; modules do not import from each other.
- Calculation code is pure and deterministic and never depends on the AI layer.
- Do not invent new layers, registries or abstractions without asking first.

## Domain rules

- The AI layer receives calculated results and retrieved knowledge as context. It must not compute positions or numbers itself, and must cite source/rule IDs where available. It states uncertainty and disagreement between schools instead of picking silently.
- Do not assume similarity between traditions implies shared origin.
- Time: store and compute in UTC with timezone-aware `datetime`; keep the original local time, tz name and location alongside. Use `zoneinfo`. Handle historical timezone/DST changes explicitly. Never use naive datetimes.
- Birth data (date, time, place, name) is personal data: do not log it, do not put it in error messages or telemetry, and exclude it from test fixtures that use real people. Use synthetic or public-figure-free fixtures.
- Check the license of any ephemeris/calculation library (e.g. Swiss Ephemeris is AGPL/commercial) before adding or bundling it. Ask if unclear.

## Python style

- Follow PEP 8 via ruff; line length 100; ruff and mypy settings live in `pyproject.toml` and are the source of truth.
- Full type hints on all public and internal functions. `mypy --strict` clean. Use modern syntax: `X | None`, `list[str]`, `type` aliases, `typing.Protocol`, `Self`, `Literal`, `Final`.
- Prefer `dataclass(frozen=True, slots=True)` or Pydantic models for data. Immutable by default.
- Pydantic v2 for all boundary validation (API, config, LLM structured output). Use `model_validate`, `ConfigDict(extra="forbid")`. No dicts as ad-hoc data structures across module boundaries.
- Use `Enum`/`StrEnum` for closed sets (planets, signs, houses, systems). No magic strings or numbers; name constants and keep them in one place.
- `pathlib` over `os.path`; f-strings; `logging` (never `print`) with lazy `%s` args.
- Functions do one thing, stay short, and avoid boolean flag parameters (use enums or separate functions). Prefer keyword-only args for 3+ parameters.
- Prefer composition and small Protocols over inheritance. Avoid deep class hierarchies and singletons/global state.
- Use `async def` for I/O-bound code (HTTP, DB, LLM calls); keep CPU-bound calculation sync and pure. Never block the event loop; no `asyncio.run` inside library code.
- Imports: absolute, grouped by ruff/isort, no wildcard imports, no circular imports (fix the design instead of importing locally).
- No dead code, commented-out code or unexplained TODOs. Comments explain *why*, not *what*.

## Core principles

Apply SOLID, KISS and DRY in all code; when they conflict, KISS wins.

- **S**ingle Responsibility: one reason to change per module, class and function.
- **O**pen/Closed: extend behavior via new implementations (Protocols, composition), not by editing stable code or adding `if tradition == ...` branches.
- **L**iskov Substitution: implementations must honor the contract of their Protocol/base type, including preconditions, postconditions and raised exceptions.
- **I**nterface Segregation: small, focused Protocols; callers depend only on what they use.
- **D**ependency Inversion: depend on abstractions; inject concrete dependencies from the composition root.
- **KISS**: choose the simplest solution that works and is readable; no speculative generality, clever tricks or premature optimization.
- **DRY**: one authoritative place for each piece of knowledge (constants, rules, schemas, formulas). Extract duplication once it appears a third time or when it encodes the same business rule; do not merge code that is only superficially similar.

## Design patterns (use when they fit, not by default)

- **Strategy / Protocol**: interchangeable calculation methods and house systems/ayanamsas.
- **Registry / Factory**: module and tradition discovery.
- **Repository**: all persistence and knowledge-base access behind an interface.
- **Adapter / Anti-corruption layer**: wrap third-party libraries (ephemeris, LLM SDKs) so they can be swapped and mocked.
- **Dependency injection**: pass dependencies explicitly via constructors/FastAPI `Depends`; no hidden imports of clients or settings inside functions.
- **Pipeline**: calculation -> enrichment -> interpretation as composable steps.
- Do not add abstraction for a single implementation without a concrete second use case. YAGNI.

## Docstrings (Sphinx / reST style)

Required on every public module, class, function and method. Concise and technical: one summary line in the imperative mood, then only what is not obvious from the signature. No restating of types already in annotations beyond the `:param:` description, no filler, no examples unless non-trivial.

```python
def julian_day(moment: datetime, *, calendar: Calendar = Calendar.GREGORIAN) -> float:
    """Convert an aware datetime to a Julian day number (UT).

    :param moment: Timezone-aware instant; converted to UTC internally.
    :param calendar: Calendar used for dates before the Gregorian reform.
    :returns: Julian day number including the fractional day.
    :raises ValueError: If ``moment`` is naive.
    """
```

Rules:
- Use `:param name:`, `:type name:` only when annotations are insufficient, `:returns:`, `:rtype:` only when not annotated, `:raises Exc:`.
- Document units and conventions (degrees vs radians, 0-360 range, tropical vs sidereal, tz) for every numeric parameter and return value.
- Calculation functions also state the algorithm/source reference and known limits in a short `.. note::` when relevant.
- Class docstring describes purpose and invariants; attributes via `:ivar:` or Pydantic `Field(description=...)`. `__init__` is not documented separately.
- Private helpers need a one-line docstring only if the name is not self-explanatory.
- Keep docstrings in English. Build with `-W` so docstring errors fail CI.

## Error handling

- Define a domain exception hierarchy rooted at `BaseAppError` (e.g. `CalculationError`, `InvalidBirthDataError`, `KnowledgeSourceError`). Raise specific exceptions; never bare `except:` or swallow errors.
- Validate input at boundaries; trust validated types internally. Fail fast with actionable messages that contain no personal data.
- Wrap external failures (LLM, DB, HTTP) at adapter level and translate to domain errors. Use timeouts and bounded retries with backoff on all network calls.

## AI / LLM code

- All LLM calls go through a single provider-agnostic adapter in `ai/`. Prompts live in versioned template files, not inline strings.
- Use structured (schema-validated) output for anything consumed by code. Validate and handle malformed responses.
- Ground answers in retrieved knowledge and calculated results; pass source IDs through and return them with the answer.
- Never send raw personal data to a model unless required for the task; minimize and document what is sent.
- Add evaluation cases (golden inputs, expected citations, refusal/disclaimer behaviour) for prompt changes. Mock the LLM in unit tests; never call a live model in the default test run.
- Never hardcode API keys or model names; read from settings.

## Testing

- pytest, with tests mirroring `src/` layout. Arrange-Act-Assert, one behavior per test, descriptive names (`test_<unit>_<behavior>_<condition>`).
- Calculation modules: validate against authoritative reference data (published ephemerides, textbook worked examples) with explicit numeric tolerances; include edge cases (polar latitudes, DST changes, midnight, leap years, pre-Gregorian dates, unusual name characters/transliteration).
- Use `pytest.mark.parametrize` and property-based tests (Hypothesis) for pure functions.
- Mock only at boundaries (adapters). No network in unit tests. Keep tests deterministic and independent.
- New code needs tests; bug fixes need a regression test first. Aim for >=90% coverage on `calculation/` and `core/`.

## Configuration, security, dependencies

- Configuration via `pydantic-settings` and environment variables; secrets never in code, logs or git. Provide `.env.example`.
- Pin dependencies through `uv.lock`; add new dependencies only when justified, and prefer well-maintained, permissively licensed packages.
- Parameterized queries only; validate and size-limit all user input, including text sent to the AI layer. Guard against prompt injection from user text and retrieved documents (treat both as data, not instructions).
- Structured JSON logging with request IDs; no PII in logs.

## Git and workflow

- Small, focused changes. Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Before starting a non-trivial feature, outline the plan (affected modules, interfaces, tests) and confirm if requirements are ambiguous. Ask rather than guess when a calculation convention or tradition-specific rule is unclear.
- Do not modify unrelated files, reformat code you did not change, or rename public APIs without being asked.
- Update docs and docstrings in the same change as the code.

## Do not

- Do not compute astrological/numerological values inside LLM prompts or the AI layer.
- Do not hardcode tradition-specific constants outside its module.
- Do not use naive datetimes, floats for exact numerology arithmetic where integers suffice, or mutable default arguments.
- Do not add features, modules or abstractions that were not requested.
