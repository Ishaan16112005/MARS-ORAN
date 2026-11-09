# Build the LaTeX paper

`main.tex` is the paper (IEEE conference template, `IEEEtran` class); the bibliography is embedded.
Its 16 PDF figures in `figures/` are produced by:

```bash
python src/edge_case_experiments.py     # ~4 min; writes results/extended/ and figures/extended/, copies PDFs here
python src/verify_paper_claims.py       # recomputes every number quoted in the text -> results/extended/paper_claims.json
```

Build locally (from this `paper/` folder):

```bash
tectonic main.tex                                   # Arch/CachyOS: sudo pacman -S tectonic
pdflatex main.tex && pdflatex main.tex              # TeX Live alternative
```

Overleaf: upload `../Overleaf_Source.zip` via New Project -> Upload Project (compiler: pdfLaTeX).
The earlier v2 manuscript is kept in `archive/` for reference only.
