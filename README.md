wesen
=====

Wesen - little game where players have to program the behavior of their Wesens to defeat the other players (like CoreWars)


History
=====
  * 2003 version 0.1 for Python 2
  * 2013 version 0.2 for Python 3
  * 2026 version 0.3 for Python > 3.7

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
