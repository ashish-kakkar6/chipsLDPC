PYTHON ?= python3
SPHINXBUILD ?= $(PYTHON) -m sphinx
SOURCEDIR := source
BUILDDIR := _build

.PHONY: help html check-assets linkcheck clean

help:
	@printf "Targets:\n"
	@printf "  make html  - build the HTML documentation\n"
	@printf "  make check-assets - check saved figures and data\n"
	@printf "  make linkcheck - check documentation links\n"
	@printf "  make clean - remove generated documentation\n"

check-assets:
	$(PYTHON) figures/build_tanner.py --check
	$(PYTHON) figures/build_architecture.py --check
	$(PYTHON) figures/publish_bb144.py --check

html: check-assets
	$(SPHINXBUILD) -n -b html -W --keep-going $(SOURCEDIR) $(BUILDDIR)/html

linkcheck:
	$(SPHINXBUILD) -n -b linkcheck -W --keep-going $(SOURCEDIR) $(BUILDDIR)/linkcheck

clean:
	rm -rf $(BUILDDIR)
