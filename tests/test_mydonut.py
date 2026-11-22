import pytest

from mydonut import __version__, cli


def test_version_string():
    assert __version__.count(".") == 2


@pytest.mark.parametrize("theme", list(cli.THEMES))
@pytest.mark.parametrize("anim", list(cli.ANIMATIONS))
def test_render_every_theme_and_animation(theme, anim):
    torus = cli.Torus("low")
    s = cli.Settings(theme=theme, animations=[anim], stars=True, cycle=0.2)
    chars, rgb = cli.render_cells(torus, s, 1.3, 60, 20)
    assert chars.shape == (60 * 20,)
    assert (chars != " ").any()
    cli.compose(chars, rgb, 60, 20)


def test_parse_args_combines_animations():
    s = cli.parse_args(["--animation", "spin,pulse", "--theme", "ice", "--size", "9"])
    assert s.animations == ["spin", "pulse"]
    assert s.theme == "ice"
    assert s.size == cli.LIMITS["size"][1]        # clamped


def test_parse_args_rejects_unknown_animation():
    with pytest.raises(SystemExit):
        cli.parse_args(["--animation", "nope"])


def test_arrow_keys_are_decoded():
    assert cli._parse_unix_keys("q\x1b[A\x1b[Dt") == ["q", "UP", "LEFT", "t"]


def test_reset_restores_defaults():
    s, initial = cli.Settings(), cli.Settings()
    for key in "casbluh":
        cli.handle_key(key, s, initial)
    assert s != initial
    cli.handle_key("r", s, initial)
    assert s == initial


def test_list_survives_closed_pipe(tmp_path):
    import subprocess, sys
    r = subprocess.run(
        f"{sys.executable} -m mydonut --list | head -1",
        shell=True, capture_output=True, text=True,
    )
    assert "Traceback" not in r.stderr
