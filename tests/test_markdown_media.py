from src.markdown_media import (
    EmbeddedMedia,
    extract_embedded_media_references,
    parse_embedded_media,
)


def test_parse_embedded_media_parses_images():
    parsed = parse_embedded_media("![avatar](r2://bucket/photos/avatar.png)")

    assert parsed == [EmbeddedMedia("image", "avatar", "r2://bucket/photos/avatar.png", "avatar.png")]


def test_parse_embedded_media_parses_links():
    parsed = parse_embedded_media("[Project Doc](r2://bucket/docs/project.pdf)")

    assert parsed == [
        EmbeddedMedia(
            "file",
            "Project Doc",
            "r2://bucket/docs/project.pdf",
            "project.pdf",
        )
    ]


def test_parse_embedded_media_parses_bare_r2_links():
    parsed = parse_embedded_media("log file: r2://bucket/logs/export.csv")

    assert parsed == [
        EmbeddedMedia(
            "file",
            "export.csv",
            "r2://bucket/logs/export.csv",
            "export.csv",
        )
    ]


def test_parse_embedded_media_works_with_duplicates_and_mixed_text():
    text = (
        "start ![cover](r2://bucket/media/cover.webp) "
        "then [manual](r2://bucket/docs/manual.m4a) "
        "and r2://bucket/raw/data.bin plus r2://bucket/raw/data.bin."
    )
    parsed = parse_embedded_media(text)

    assert parsed == [
        EmbeddedMedia(
            "image",
            "cover",
            "r2://bucket/media/cover.webp",
            "cover.webp",
        ),
        EmbeddedMedia(
            "audio",
            "manual",
            "r2://bucket/docs/manual.m4a",
            "manual.m4a",
        ),
        EmbeddedMedia(
            "file",
            "data.bin",
            "r2://bucket/raw/data.bin",
            "data.bin",
        ),
        EmbeddedMedia(
            "file",
            "data.bin",
            "r2://bucket/raw/data.bin",
            "data.bin",
        ),
    ]


def test_parse_embedded_media_defaults_unknown_extension_to_file():
    parsed = parse_embedded_media("backup: r2://bucket/archives/backup.zip")

    assert len(parsed) == 1
    assert parsed[0].kind == "file"


def test_extract_embedded_media_references_preserves_original_markdown():
    text = (
        "请处理 ![猫](r2://bucket/imgs/cat.png) "
        "参考 [录音](r2://bucket/audios/note.mp3) "
        "以及 r2://bucket/files/report.pdf."
    )

    refs = extract_embedded_media_references(text)

    assert refs == [
        "![猫](r2://bucket/imgs/cat.png)",
        "[录音](r2://bucket/audios/note.mp3)",
        "r2://bucket/files/report.pdf",
    ]
