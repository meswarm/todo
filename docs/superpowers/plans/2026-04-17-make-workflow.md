# Make Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-local `Makefile` so common setup, run, test, and cleanup workflows can be executed as `make xxx` from the repo root, with clear failure messages when the virtualenv has not been initialized.

**Architecture:** Keep the change minimal and local to the repository root. Put workflow orchestration and environment checks in a new `Makefile`, then update `README.md` so the documented primary path matches the new commands. Verification relies on running the `make` targets directly rather than adding test-only scaffolding for build tooling.

**Tech Stack:** GNU Make, Python virtualenv, existing `requirements.txt`, existing FastAPI app and pytest suite

---

### Task 1: Add Makefile targets and environment checks

**Files:**
- Create: `Makefile`
- Modify: none
- Test: command verification via `make help` and `make test`

- [ ] **Step 1: Create the Makefile with target layout and shared variables**

```make
.DEFAULT_GOAL := help

VENV_PYTHON := .venv/bin/python
VENV_PIP := .venv/bin/pip

.PHONY: help init check-venv run test clean
```

- [ ] **Step 2: Add the help target with self-documenting output**

```make
help:
	@echo "Available targets:"
	@echo "  make init   - Create .venv and install dependencies"
	@echo "  make run    - Start the Todo API"
	@echo "  make test   - Run the test suite"
	@echo "  make clean  - Remove Python cache files"
```

- [ ] **Step 3: Add the init target**

```make
init:
	python3 -m venv .venv
	$(VENV_PIP) install -r requirements.txt
```

- [ ] **Step 4: Add a reusable virtualenv check target**

```make
check-venv:
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Virtualenv not initialized. Run: make init"; \
		exit 1; \
	fi
```

- [ ] **Step 5: Add run and test targets that depend on the check**

```make
run: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m src.main

test: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m pytest tests/ -v
```

- [ ] **Step 6: Add a non-destructive clean target**

```make
clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
```

- [ ] **Step 7: Run help to verify the file parses correctly**

Run: `make help`

Expected: the command succeeds and prints the four documented workflow targets.

### Task 2: Update README to use make-based commands

**Files:**
- Create: none
- Modify: `README.md`
- Test: readback review plus command verification against the new `Makefile`

- [ ] **Step 1: Replace the quick-start commands with make-based setup**

```md
## 快速启动

```bash
# 1. 初始化虚拟环境并安装依赖
make init

# 2. 启动服务
make run
# 服务监听地址与端口以 .env.example / .env 中 TODO_PORT 为准（默认 48890）
```
```

- [ ] **Step 2: Replace the test section with the make-based command**

```md
## 运行测试

```bash
make test
```
```

- [ ] **Step 3: Add a short note explaining the environment boundary**

```md
说明：`make run`、`make test` 等命令不会自动创建虚拟环境；如果环境未初始化，请先执行 `make init`。
```

- [ ] **Step 4: Review the README for consistency**

Check that the documented commands are exactly `make init`, `make run`, and `make test`, and that no removed setup steps remain in the quick-start path.

### Task 3: Verify the workflow end to end

**Files:**
- Create: none
- Modify: none
- Test: `Makefile`, `README.md`

- [ ] **Step 1: Run the help target**

Run: `make help`

Expected: PASS, with the listed targets and no syntax errors.

- [ ] **Step 2: Run the test target**

Run: `make test`

Expected: PASS, pytest executes through `.venv/bin/python` and the test suite completes successfully.

- [ ] **Step 3: Check the missing-environment error path**

Run:

```bash
mv .venv .venv.bak
make test || true
mv .venv.bak .venv
```

Expected: `make test` fails with `Virtualenv not initialized. Run: make init`, then the original virtualenv is restored.

- [ ] **Step 4: Review changed files before handoff**

Confirm that only `Makefile`, `README.md`, and documentation files for the spec/plan were updated for this workflow change.
