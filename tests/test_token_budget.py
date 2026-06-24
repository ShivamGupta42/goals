from pathlib import Path

from goals.token_budget import TokenUsage, transcript_token_usage


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_missing_file_is_zero(tmp_path: Path) -> None:
    usage = transcript_token_usage(tmp_path / "nope.jsonl")
    assert usage.total == 0


def test_sums_usage_across_turns(tmp_path: Path) -> None:
    transcript = _write(
        tmp_path / "t.jsonl",
        [
            '{"type":"assistant","message":{"usage":{"input_tokens":10,"output_tokens":5}}}',
            '{"type":"assistant","message":{"usage":{"input_tokens":20,"output_tokens":7,'
            '"cache_creation_input_tokens":3,"cache_read_input_tokens":100}}}',
        ],
    )
    usage = transcript_token_usage(transcript)
    assert usage.input_tokens == 30
    assert usage.output_tokens == 12
    assert usage.cache_creation_input_tokens == 3
    assert usage.cache_read_input_tokens == 100
    assert usage.total == 145


def test_ignores_blank_and_malformed_lines(tmp_path: Path) -> None:
    transcript = _write(
        tmp_path / "t.jsonl",
        [
            "",
            "not json at all",
            '{"type":"user","message":{"content":"hi"}}',  # no usage
            '{"type":"assistant","message":{"usage":{"output_tokens":9}}}',
        ],
    )
    assert transcript_token_usage(transcript).total == 9


def test_reads_top_level_usage_shape(tmp_path: Path) -> None:
    transcript = _write(tmp_path / "t.jsonl", ['{"usage":{"output_tokens":4}}'])
    assert transcript_token_usage(transcript).total == 4


def test_booleans_do_not_inflate_count(tmp_path: Path) -> None:
    # ``true`` is an int subclass in Python; it must not be counted as 1 token.
    transcript = _write(
        tmp_path / "t.jsonl",
        ['{"message":{"usage":{"output_tokens":true,"input_tokens":5}}}'],
    )
    assert transcript_token_usage(transcript) == TokenUsage(input_tokens=5)


def test_negative_values_contribute_zero(tmp_path: Path) -> None:
    # A negative field must not subtract from the total and hold the ceiling off.
    transcript = _write(
        tmp_path / "t.jsonl",
        ['{"message":{"usage":{"input_tokens":-999999,"output_tokens":7}}}'],
    )
    assert transcript_token_usage(transcript) == TokenUsage(output_tokens=7)
