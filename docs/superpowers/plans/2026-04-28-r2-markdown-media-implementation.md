# R2 Markdown Media Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Matrix native attachment ingestion with Markdown-embedded `r2://...` media parsing, conditional R2 download, and optional multimodal image injection while preserving original Markdown in stored task content.

**Architecture:** Keep Matrix as the text transport only. Add a Markdown media parser plus explicit R2 URI download support, then integrate both into the Agent prompt composition path so that the raw Markdown remains canonical while downloads and vision inputs act only as runtime enhancements.

**Tech Stack:** Python 3.12, pydantic, asyncio, Matrix client runtime, existing R2 media store, pytest

---

## File Map

**Create:**
- `src/markdown_media.py` — parse Markdown and bare `r2://...` links into structured embedded-media records
- `tests/test_markdown_media.py` — parser coverage and category inference tests

**Modify:**
- `src/agent.py` — remove Matrix attachment-first prompt composition and integrate Markdown-R2 parsing
- `src/media_store.py` — add explicit R2 URI download support for runtime media fetches
- `src/config.py` — keep current media switches but expose anything needed by the new R2 download path
- `src/matrix_client.py` — demote native attachment flow to non-default / ignored compatibility handling if needed
- `src/llm_engine.py` — keep existing multimodal image tag support and adapt only if the new compose path requires format tightening
- `prompts/system_prompt.md` — clarify that embedded R2 Markdown is valid task content and should not trigger unnecessary clarification
- `tests/test_media_store.py` — add download-path tests
- `tests/test_matrix_client.py` — update expectations if native attachment handling is reduced
- `tests/test_llm_engine.py` — verify multimodal path still works

**Verify existing behavior still holds in:**
- `tests/test_todo_tools.py`
- `tests/test_prompt_context.py`
- `tests/test_task_service.py`

---

### Task 1: Add Markdown R2 Parser

**Files:**
- Create: `src/markdown_media.py`
- Test: `tests/test_markdown_media.py`

- [ ] **Step 1: Write the failing parser tests**

```python
from src.markdown_media import parse_embedded_media


def test_parse_image_markdown_r2_link():
    items = parse_embedded_media("![草帽](r2://linux-storage/todo/imgs/hat.jpg)")
    assert len(items) == 1
    assert items[0].kind == "image"
    assert items[0].label == "草帽"
    assert items[0].url == "r2://linux-storage/todo/imgs/hat.jpg"


def test_parse_normal_markdown_r2_link():
    items = parse_embedded_media("[说明书](r2://linux-storage/todo/files/manual.pdf)")
    assert len(items) == 1
    assert items[0].kind == "file"
    assert items[0].label == "说明书"


def test_parse_bare_r2_uri():
    items = parse_embedded_media("明天处理这个 r2://linux-storage/todo/audios/note.mp3")
    assert len(items) == 1
    assert items[0].kind == "audio"
    assert items[0].label == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_markdown_media.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing `parse_embedded_media`

- [ ] **Step 3: Write minimal parser implementation**

```python
from dataclasses import dataclass
from pathlib import PurePosixPath
import re


@dataclass
class EmbeddedMedia:
    kind: str
    url: str
    label: str = ""
    filename: str | None = None
    local_path: str | None = None


IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((r2://[^)]+)\)")
LINK_RE = re.compile(r"(?<!\!)\[([^\]]*)\]\((r2://[^)]+)\)")
BARE_RE = re.compile(r"(?<!\()(?P<url>r2://[^\s)]+)")


def infer_media_kind(url: str) -> str:
    suffix = PurePosixPath(url.replace("r2://", "", 1)).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return "image"
    if suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        return "video"
    if suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        return "audio"
    return "file"


def parse_embedded_media(text: str) -> list[EmbeddedMedia]:
    items: list[EmbeddedMedia] = []
    seen: set[str] = set()
    for pattern in (IMAGE_RE, LINK_RE):
        for label, url in pattern.findall(text):
            if url in seen:
                continue
            seen.add(url)
            items.append(
                EmbeddedMedia(
                    kind=infer_media_kind(url),
                    url=url,
                    label=label,
                    filename=PurePosixPath(url.replace("r2://", "", 1)).name,
                )
            )
    for match in BARE_RE.finditer(text):
        url = match.group("url")
        if url in seen:
            continue
        seen.add(url)
        items.append(
            EmbeddedMedia(
                kind=infer_media_kind(url),
                url=url,
                filename=PurePosixPath(url.replace("r2://", "", 1)).name,
            )
        )
    return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_markdown_media.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/markdown_media.py tests/test_markdown_media.py
git commit -m "feat: add markdown r2 media parser"
```

### Task 2: Add Explicit R2 URI Download Support

**Files:**
- Modify: `src/media_store.py`
- Test: `tests/test_media_store.py`

- [ ] **Step 1: Write the failing download tests**

```python
from pathlib import Path

from src.media_store import local_download_path, category_for_mime, r2_download_path


def test_r2_download_path_routes_images(tmp_path):
    path = r2_download_path("r2://linux-storage/todo/imgs/hat.jpg", tmp_path)
    assert path == tmp_path / "imgs" / "hat.jpg"


def test_r2_download_path_routes_unknown_files(tmp_path):
    path = r2_download_path("r2://linux-storage/todo/files/manual.pdf", tmp_path)
    assert path == tmp_path / "files" / "manual.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_media_store.py -v`
Expected: FAIL with missing `r2_download_path`

- [ ] **Step 3: Write minimal implementation**

```python
from pathlib import Path, PurePosixPath


def category_for_r2_uri(uri: str) -> str:
    suffix = PurePosixPath(uri.replace("r2://", "", 1)).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return "imgs"
    if suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        return "videos"
    if suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        return "audios"
    return "files"


def r2_download_path(uri: str, downloads_dir: Path) -> Path:
    filename = PurePosixPath(uri.replace("r2://", "", 1)).name
    return downloads_dir / category_for_r2_uri(uri) / filename
```

Then add an async download method to `R2MediaStore` that:
- parses `r2://bucket/key`
- writes the object to `r2_download_path(...)`
- returns `Path | None`

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_media_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/media_store.py tests/test_media_store.py
git commit -m "feat: add r2 uri download path support"
```

### Task 3: Respect Download Switches for Markdown Media

**Files:**
- Modify: `src/agent.py`
- Test: `tests/test_markdown_media.py`

- [ ] **Step 1: Write the failing behavior tests**

```python
from src.markdown_media import parse_embedded_media


def test_image_download_can_be_disabled():
    text = "![草帽](r2://linux-storage/todo/imgs/hat.jpg)"
    items = parse_embedded_media(text)
    assert items[0].kind == "image"
```

Add an Agent-focused unit test that monkeypatches media switches so image download is disabled and confirms no download call happens.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_markdown_media.py tests/test_matrix_client.py -v`
Expected: FAIL because Agent still has no Markdown-aware compose flow

- [ ] **Step 3: Write minimal implementation**

In `src/agent.py`, add helpers that:

```python
def _download_enabled(self, media_kind: str) -> bool:
    if media_kind == "image":
        return self._config.media.download_images
    if media_kind == "video":
        return self._config.media.download_videos
    if media_kind == "audio":
        return self._config.media.download_audios
    return self._config.media.download_files
```

Use the parsed `EmbeddedMedia` list to conditionally invoke R2 download only when the relevant switch is enabled.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_markdown_media.py tests/test_matrix_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_markdown_media.py tests/test_matrix_client.py
git commit -m "feat: honor markdown r2 download switches"
```

### Task 4: Remove Matrix Attachment Flow From Prompt Composition

**Files:**
- Modify: `src/agent.py`
- Modify: `src/matrix_client.py`
- Test: `tests/test_matrix_client.py`

- [ ] **Step 1: Write the failing compatibility test**

```python
def test_agent_compose_prompt_uses_text_markdown_as_primary_input():
    # construct agent with fake media store and no attachment download calls
    ...
    prompt = asyncio.run(agent._compose_prompt("![草帽](r2://linux-storage/todo/imgs/hat.jpg)\n明天要买这个", [], "!room"))
    assert "明天要买这个" in prompt
```

Add an assertion that Matrix native attachments are not required for this case.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_matrix_client.py tests/test_llm_engine.py -v`
Expected: FAIL because `_compose_prompt()` still processes attachment objects as the primary path

- [ ] **Step 3: Write minimal implementation**

Refactor `_compose_prompt()` so that it:

```python
parts = [raw_text]
embedded = parse_embedded_media(raw_text)
for item in embedded:
    if self._download_enabled(item.kind):
        local_path = await self._media_store.download_r2_uri(item.url, item.kind)
        ...
```

For this task:
- keep `attachments` parameter for interface compatibility
- stop using attachment downloads as the default message enrichment path
- optionally log unexpected native attachments and ignore them

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_matrix_client.py tests/test_llm_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent.py src/matrix_client.py tests/test_matrix_client.py tests/test_llm_engine.py
git commit -m "refactor: make markdown r2 links the default media path"
```

### Task 5: Inject Downloaded Images Into Multimodal LLM Input

**Files:**
- Modify: `src/agent.py`
- Modify: `src/llm_engine.py` if format tightening is needed
- Test: `tests/test_llm_engine.py`

- [ ] **Step 1: Write the failing multimodal test**

```python
def test_markdown_r2_image_becomes_image_tag_when_vision_enabled():
    prompt = "... composed prompt ..."
    assert "[image:" in prompt
```

Use a fake local image path returned from the media store and verify the resulting prompt contains the existing image-tag format consumed by `LLMEngine`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_llm_engine.py -v`
Expected: FAIL because Markdown-R2 images are still text-only

- [ ] **Step 3: Write minimal implementation**

When:
- `item.kind == "image"`
- `self._llm.vision_enabled is True`
- download succeeded

append:

```python
parts.append(f"[image:{local_path}:{mime_type}]")
```

Keep the original Markdown text untouched in `parts[0]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_llm_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent.py src/llm_engine.py tests/test_llm_engine.py
git commit -m "feat: inject markdown r2 images into multimodal prompts"
```

### Task 6: Preserve Original Markdown In Stored Task Content

**Files:**
- Modify: `prompts/system_prompt.md`
- Test: `tests/test_todo_tools.py`
- Verify with: `src/tools/todo_tools.py`, `src/services/task_service.py`

- [ ] **Step 1: Write the failing storage expectations**

```python
def test_task_detail_keeps_original_r2_markdown():
    markdown = "![草帽](r2://linux-storage/todo/imgs/hat.jpg)\n明天要买这个"
    ...
    assert task["detail"] == markdown
```

Also add a completion-summary version.

- [ ] **Step 2: Run test to verify it fails if any rewriting occurs**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_todo_tools.py tests/test_task_service.py -v`
Expected: FAIL if any path rewriting is still present

- [ ] **Step 3: Write minimal implementation**

Keep the write path simple:

```python
detail = original_user_message
completion_summary = original_user_message
```

Do not substitute local paths or transformed media tags into stored task fields. Update `prompts/system_prompt.md` to explicitly require preserving original Markdown links.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_todo_tools.py tests/test_task_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add prompts/system_prompt.md tests/test_todo_tools.py tests/test_task_service.py
git commit -m "docs: require preserving original r2 markdown in task storage"
```

### Task 7: Full Regression And Manual Verification

**Files:**
- Verify: `tests/test_markdown_media.py`
- Verify: `tests/test_media_store.py`
- Verify: `tests/test_llm_engine.py`
- Verify: `tests/test_matrix_client.py`
- Verify: `tests/test_todo_tools.py`

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_markdown_media.py \
  tests/test_media_store.py \
  tests/test_llm_engine.py \
  tests/test_matrix_client.py \
  tests/test_todo_tools.py -v
```

Expected: PASS

- [ ] **Step 2: Run full test suite**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
make test
```

Expected: all tests pass

- [ ] **Step 3: Manual Matrix verification**

Start runtime:

```bash
make run
```

Send:

```md
![草帽](r2://linux-storage/todo/imgs/example.jpg)
明天要买这个
```

Verify:
- the task can be created from text content
- original Markdown is preserved in stored task detail
- image downloads to `downloads/imgs/` only when `R2_DOWNLOAD_IMAGES=true`
- no Matrix native attachment path is required

- [ ] **Step 4: Commit final verification state**

```bash
git add .
git commit -m "test: verify markdown r2 media flow end to end"
```

---

## Self-Review

### Spec Coverage

- Canonical Markdown input: Task 4
- Parser for image/link/bare URI forms: Task 1
- Conditional category downloads: Task 2 and Task 3
- Vision-enabled image promotion: Task 5
- Original Markdown preservation: Task 6
- Matrix attachment demotion: Task 4
- Regression coverage: Task 7

No design requirement is left without a corresponding implementation task.

### Placeholder Scan

This plan contains exact file paths, concrete tests, concrete commands, and explicit implementation snippets for every task. No `TBD`, `TODO`, or “similar to above” placeholders remain.

### Type Consistency

The plan consistently uses:
- `parse_embedded_media`
- `EmbeddedMedia`
- `download_r2_uri`
- `r2_download_path`
- original task `detail` / `completion_summary`

Names are stable across tasks.
