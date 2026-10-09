# make build   - draws all sprites and pre-solves the snake games into dist/ (needs Python 3 + Pillow)
DIST := dist

.PHONY: build clean

build:
	mkdir -p $(DIST)
	cp arcade/*.py $(DIST)/
	cd $(DIST) && for s in ../build/build_font.py ../build/build_core.py ../build/g_*_build.py ../build/gen_games.py; do \
		PYTHONPATH=../build:. python3 $$s || exit 1; done

clean:
	rm -rf $(DIST)
