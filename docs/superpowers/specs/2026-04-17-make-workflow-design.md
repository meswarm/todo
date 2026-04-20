# Make Workflow Design

## Goal

Provide a project-local `Makefile` so common workflows can be run as `make xxx`
from the repository root without manually remembering long commands.

The `Makefile` should only orchestrate commands. It must not silently create a
virtual environment or install dependencies during normal command execution.
When the environment is missing, it should fail fast with a clear instruction to
run `make init`.

## Commands

The project will expose these targets:

- `make help`: show available targets and brief descriptions
- `make init`: create `.venv` and install dependencies from `requirements.txt`
- `make run`: start the FastAPI app with the project virtualenv
- `make test`: run the test suite with the project virtualenv
- `make clean`: remove Python cache artifacts

`help` should be the default target so users can type plain `make` to see the
available workflow.

## Environment Checks

All targets except `init`, `help`, and `clean` should verify that the project
virtualenv exists by checking `.venv/bin/python`.

If the virtualenv is missing, the target should exit with a non-zero status and
print a concise actionable message such as:

`Virtualenv not initialized. Run: make init`

This keeps behavior explicit and avoids hidden environment mutation.

## Command Behavior

`init` will:

1. create `.venv` with `python3 -m venv .venv`
2. install dependencies with `.venv/bin/pip install -r requirements.txt`

`run` will execute:

`PYTHONPATH=. .venv/bin/python -m src.main`

`test` will execute:

`PYTHONPATH=. .venv/bin/python -m pytest tests/ -v`

`clean` will remove local cache directories such as `__pycache__`,
`.pytest_cache`, and `*.pyc` files, but it will not delete `.venv` or runtime
data.

## Documentation Changes

`README.md` will be updated so the primary setup path becomes:

1. `make init`
2. `make run`

The testing section will also use `make test` as the primary command while
keeping the underlying Python command obvious from the `Makefile`.

## Error Handling

The `Makefile` should prefer short, explicit failures over implicit recovery.
If a required executable is missing during `init` or command execution, the
shell error should surface naturally rather than being masked by complex logic.

## Verification

After implementation:

1. run `make help`
2. run `make test`
3. verify the updated README instructions match the actual targets
