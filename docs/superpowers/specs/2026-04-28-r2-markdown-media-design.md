# R2 Markdown Media Flow Design

## Background

The todo runtime is now Matrix-first, but the user client no longer relies on Matrix native attachment events as the primary media path. Instead, the client sends plain text messages whose Markdown content embeds `r2://...` links for images, videos, audios, and files.

The runtime must therefore treat Markdown text as the canonical input and use R2 as the default media transport.

## Goals

1. Remove Matrix native attachment flow as the default media ingestion path.
2. Parse Markdown-embedded `r2://...` links from user text messages.
3. Download embedded R2 objects into `downloads/` by media category when the corresponding `R2_DOWNLOAD_*` switches are enabled.
4. When `LLM_VISION_ENABLED=true`, automatically convert Markdown image links into multimodal image inputs for the LLM.
5. Preserve the user’s original Markdown text exactly when saving task `detail` or `completion_summary`.

## Non-Goals

1. Rewriting stored Markdown links into local file paths.
2. Using Matrix native media as a fallback storage backend.
3. Supporting arbitrary HTML embed formats as a first-step requirement.

## Supported Input Forms

The parser must support all of the following:

1. Markdown image links:

```md
![图片说明](r2://bucket/path/a.jpg)
```

2. Markdown normal links:

```md
[文件说明](r2://bucket/path/manual.pdf)
```

3. Bare R2 URIs:

```md
r2://bucket/path/a.jpg
```

The canonical user-facing format remains Markdown. Bare URIs are tolerated for robustness.

## Design Options

### Option A: Keep Matrix attachments as primary and add Markdown parsing as a side path

Pros:
- Smallest code change.
- Preserves old behavior.

Cons:
- Conflicts with the new client contract.
- Leaves two competing media paths in the runtime.
- Increases ambiguity around which content is canonical.

### Option B: Make Markdown-R2 the canonical path and demote Matrix attachments to non-default compatibility

Pros:
- Matches the client contract exactly.
- Keeps the user text as the source of truth.
- Makes storage and model input rules easier to reason about.

Cons:
- Requires parsing and download orchestration work.
- Some old attachment-oriented code becomes dead or compatibility-only.

### Option C: Strip all media handling from the runtime and send only raw Markdown to the model

Pros:
- Smallest runtime.
- No download complexity.

Cons:
- Breaks multimodal image understanding.
- Breaks local download caching behavior.
- Loses the media-aware workflow the product now requires.

## Recommendation

Use Option B.

Markdown text becomes the canonical user input. The runtime parses embedded `r2://...` links, optionally downloads them, and only uses those downloads as runtime enhancements. The saved task text remains unchanged.

## Architecture

### 1. Canonical Input

Incoming Matrix message text is the only canonical payload for task creation, updates, and completion summaries.

The system must preserve the raw user text exactly as received.

### 2. Markdown Media Parsing Layer

Add a dedicated parser module:

- `src/markdown_media.py`

Responsibilities:

1. Parse message text for:
   - `![alt](r2://...)`
   - `[label](r2://...)`
   - bare `r2://...`
2. Extract:
   - link kind
   - label / alt text
   - bucket + key
   - filename
   - inferred media category
3. Return structured metadata without mutating the original text.

Suggested model:

```python
@dataclass
class EmbeddedMedia:
    kind: Literal["image", "video", "audio", "file"]
    url: str
    label: str
    filename: str | None
    local_path: Path | None
```

### 3. R2 Download Layer

Extend the R2 layer with explicit R2 URI download support.

Recommended API:

```python
async def download_r2_uri(uri: str, kind: str) -> Path | None
```

Behavior:

1. Parse `r2://bucket/key`
2. Authenticate using existing R2 credentials
3. Download to:
   - `downloads/imgs`
   - `downloads/videos`
   - `downloads/audios`
   - `downloads/files`
4. Return the local path when successful

The runtime must not rewrite the original Markdown link after download.

### 4. Download Switches

The parser should always recognize R2 links, but downloading is controlled by the existing switches:

- `R2_DOWNLOAD_IMAGES`
- `R2_DOWNLOAD_VIDEOS`
- `R2_DOWNLOAD_AUDIOS`
- `R2_DOWNLOAD_FILES`

Rules:

1. If a switch is `false`, do not download that category.
2. If a switch is `false`, keep the link only as text context.
3. If all switches are `false`, the message is treated as plain Markdown text from the model’s perspective.

## LLM Input Rules

### Vision Disabled

If `LLM_VISION_ENABLED=false`:

1. The original Markdown remains in the text prompt.
2. Parsed media metadata may be used for logging or local caching only.
3. No image content is promoted into multimodal model input.

### Vision Enabled

If `LLM_VISION_ENABLED=true` and the embedded media is an image:

1. If image download is allowed and succeeds, convert the local image into the existing multimodal input format used by `LLMEngine`.
2. Preserve the original Markdown in the text body.
3. Add the local image as a runtime enhancement, not a text replacement.

Videos, audios, and files remain text-only context in this iteration.

## Storage Rules

These rules are strict and non-negotiable:

1. Task `detail` must preserve the original user Markdown exactly.
2. Task `completion_summary` must preserve the original user Markdown exactly.
3. R2 links must never be rewritten to:
   - local paths
   - temporary URLs
   - Matrix URLs
4. Returned content shown back to the user must still contain the original `r2://...` links so the client can render and download them correctly.

## Matrix Attachment Policy

Matrix native attachment flow is no longer the primary media path.

Required behavior:

1. Text messages are fully supported.
2. Markdown-embedded `r2://...` links are the default media path.
3. Native Matrix attachment download/upload behavior should be removed from the main prompt composition path.

Compatibility handling:

If a Matrix native attachment event appears unexpectedly, the runtime may ignore it or log it as unsupported, but it should not be used as the normal file ingestion path.

## Integration Points

### `src/agent.py`

Refactor `_compose_prompt()` so that it:

1. Takes raw text as the primary input.
2. Parses embedded R2 links from text.
3. Downloads media conditionally by category switch.
4. Adds image multimodal inputs only when vision is enabled.
5. Leaves the original Markdown unchanged.

### `src/matrix_client.py`

Native attachment flow should no longer be treated as the main content ingestion path.

The message handler contract should remain text-first.

### `src/skills.py` and Prompt Layer

Prompt / skills should clarify:

1. Embedded Markdown R2 links are valid task content.
2. If image understanding is available, the model should use it.
3. The model must not ask users to retype file descriptions when the task text already contains embedded media links.

## Error Handling

1. If an R2 link is malformed:
   - keep original text
   - do not fail the whole message
   - log a warning
2. If a download fails:
   - keep original text
   - continue processing the message
   - skip multimodal injection for that media item
3. If a file category cannot be inferred:
   - classify as `file`
4. If vision is enabled but the image cannot be downloaded:
   - fall back to text-only handling

## Testing

Required coverage:

1. Markdown parser recognizes:
   - image links
   - normal links
   - bare R2 URIs
2. Category switches block downloads correctly.
3. Enabled switches download into the correct `downloads/*` directories.
4. Vision-enabled image Markdown becomes multimodal LLM input.
5. Vision-disabled image Markdown remains text-only.
6. Saved task `detail` preserves original Markdown exactly.
7. Saved `completion_summary` preserves original Markdown exactly.
8. Matrix native attachment content is no longer required for this flow.

## Rollout Notes

After implementation:

1. Restart the runtime.
2. Verify that a message like:

```md
![草帽](r2://linux-storage/todo/imgs/example.jpg)
明天要买这个
```

can be interpreted correctly.
3. Verify that the image is downloaded only if `R2_DOWNLOAD_IMAGES=true`.
4. Verify that the stored task text still contains the original Markdown.
