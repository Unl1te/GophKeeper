import os
import sys

import pytest

import cli


def test_no_args_shows_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py"])
    cli.main()
    assert "available commands" in capsys.readouterr().out


def test_help_flags_show_help(monkeypatch, capsys):
    for flag in ("-h", "--help"):
        monkeypatch.setattr(sys, "argv", ["cli.py", flag])
        cli.main()
        assert "available commands" in capsys.readouterr().out


def test_unknown_command_uses_prog_name(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cli.py", "bogus"])
    with pytest.raises(SystemExit):
        cli.main()
    out = capsys.readouterr().out
    assert "Unknown command" in out
    assert "python cli.py help" in out


def test_help_text_uses_binary_name_when_frozen(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gophkeeper"])
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cli.help()
    out = capsys.readouterr().out
    assert "gophkeeper <command>" in out
    assert "python cli.py" not in out


def test_list_prints_metadata(capsys):
    cli._print_items(
        [
            {
                "id": 1,
                "type": "text",
                "version": 1,
                "updated_at": "2026-01-01T00:00:00Z",
                "metadata": {"note": "github"},
            },
            {
                "id": 2,
                "type": "text",
                "version": 1,
                "updated_at": "2026-01-01T00:00:00Z",
                "metadata": {},
            },
        ]
    )
    out = capsys.readouterr().out
    assert "Metadata" in out  # column header
    assert "note=github" in out  # metadata makes items distinguishable


def test_dotenv_loads_env_from_cwd(monkeypatch, tmp_path):
    """cli reads config via load_dotenv(find_dotenv(usecwd=True)); verify a cwd .env is picked up."""
    from dotenv import find_dotenv, load_dotenv

    (tmp_path / ".env").write_text("GK_TEST_DOTENV=works\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GK_TEST_DOTENV", raising=False)
    try:
        load_dotenv(find_dotenv(usecwd=True))
        assert os.environ.get("GK_TEST_DOTENV") == "works"
    finally:
        os.environ.pop("GK_TEST_DOTENV", None)
