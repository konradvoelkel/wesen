wesen
=====

Wesen - little game where players have to program the behavior of their Wesens to defeat the other players (like CoreWars)


History
=====
  * 2003 version 0.1 for Python 2
  * 2013 version 0.6 for Python 3
  * 2026 version 0.7 for Python > 3.7

Run/Install/Build
=====

First you need freeglut (external non-python dependency for OpenGL), e.g.
```sh
sudo apt install freeglut3-dev
```

Using `uv`:
```sh
git clone https://github.com/konradvoelkel/wesen.git
cd wesen
uv venv
uv sync
uv run wesen
```

The GUI starts paused; press space.


Write a wesen
=====

Put a source of your own in `~/.wesen/sources` — either a single file
`MyWesen.py` or a folder `MyWesen/main.py` — and play it against the
sources shipped with the game:

```sh
uv run wesen -s MyWesen,Dwarf,Rincewind
```

`-p DIR` adds another folder to look in. `SOURCES.md` is the guide: the
whole API, the rules that matter, and what the existing sources do.


Develop
=====

```sh
uv run ruff check && uv run ruff format --check
uv run mypy src
uv run python -m unittest discover -s tests -t . -p '*.py'
```

`OVERVIEW.md` maps the codebase. The same three commands run in CI.
