import pytest

from myps import configutil


def test_load_config_with_table_entries(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[regexSkipPatterns]
system = '^/System/'
apps = '^/Applications/'

[regexKeepPatterns]
terminal = 'Terminal'
xcode = '[Xx]code'
        """.strip()
    )

    cfg = configutil.load_config(config_path)

    assert set(cfg.skip_patterns) == {"^/System/", "^/Applications/"}
    assert set(cfg.keep_patterns) == {"Terminal", "[Xx]code"}
    assert cfg.skip_re is not None
    assert cfg.skip_re.search("/System/Library/fseventsd")
    assert cfg.keep_re is not None
    assert cfg.keep_re.search(
        "/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal"
    )


def test_load_config_missing_returns_empty(tmp_path):
    missing = tmp_path / "missing.toml"
    cfg = configutil.load_config(missing)
    assert cfg.skip_patterns == []
    assert cfg.keep_patterns == []
    assert cfg.skip_re is None
    assert cfg.keep_re is None


def test_write_sample_config(tmp_path):
    target = tmp_path / "myps.toml"
    written = configutil.write_sample_config(target)

    assert written == target
    assert target.exists()
    content = target.read_text()
    assert "regexSkipPatterns" in content
    assert "regexKeepPatterns" in content

    with pytest.raises(FileExistsError):
        configutil.write_sample_config(target)
