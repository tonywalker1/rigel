"""Tests for the Rigel CLI driver (Plan 08).

Tests call main(argv) and check exit code + stdout/stderr.
"""

import pytest
from io import StringIO
from unittest.mock import patch

from rigel.driver import main


class TestRunSubcommand:
    def test_run_simple(self, tmp_path):
        f = tmp_path / "hello.rgl"
        f.write_text("(let x 42) x")
        assert main(["run", str(f)]) == 0

    def test_run_with_println(self, tmp_path, capsys):
        f = tmp_path / "hello.rgl"
        f.write_text('(handle (println "hello") (io (msg) msg))')
        assert main(["run", str(f)]) == 0
        assert "hello" in capsys.readouterr().out

    def test_run_stdin(self, capsys):
        with patch("sys.stdin", StringIO("(+ 1 2)")):
            assert main(["run", "-"]) == 0

    def test_run_file_not_found(self, capsys):
        assert main(["run", "nonexistent.rgl"]) == 1
        assert "file not found" in capsys.readouterr().err

    def test_run_parse_error(self, tmp_path, capsys):
        f = tmp_path / "bad.rgl"
        f.write_text("(let)")
        assert main(["run", str(f)]) == 1
        assert capsys.readouterr().err  # some error on stderr

    def test_run_type_error(self, tmp_path, capsys):
        f = tmp_path / "bad.rgl"
        f.write_text("(+ x 1)")
        assert main(["run", str(f)]) == 1
        assert "undefined" in capsys.readouterr().err


class TestCheckSubcommand:
    def test_check_valid(self, tmp_path):
        f = tmp_path / "ok.rgl"
        f.write_text("(let x 42) x")
        assert main(["check", str(f)]) == 0

    def test_check_error(self, tmp_path, capsys):
        f = tmp_path / "bad.rgl"
        f.write_text("(+ x 1)")
        assert main(["check", str(f)]) == 1
        assert "undefined" in capsys.readouterr().err


class TestCompileSubcommand:
    def test_compile_stub(self, tmp_path, capsys):
        f = tmp_path / "test.rgl"
        f.write_text("42")
        assert main(["compile", str(f)]) == 1
        assert "not yet implemented" in capsys.readouterr().err


class TestFlags:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        assert "0.1.0" in capsys.readouterr().out

    def test_no_args(self, capsys):
        assert main([]) == 1

    def test_dump_ast(self, tmp_path, capsys):
        f = tmp_path / "test.rgl"
        f.write_text("(let x 42)")
        assert main(["run", "--dump-ast", str(f)]) == 0
        assert "LetForm" in capsys.readouterr().err

    def test_dump_ir(self, tmp_path, capsys):
        f = tmp_path / "test.rgl"
        f.write_text("(let x 42)")
        assert main(["run", "--dump-ir", str(f)]) == 0
        assert "TLetForm" in capsys.readouterr().err
