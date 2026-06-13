Docstring drift:
- the module docstring still describes raw dict-shaped runtime rows even though the current code now uses a typed runtime row boundary in memory

Owning code surface:
- the production runtime contract and the nearby processor or alert-rule helpers that use it

Recommended updates:
- update the module docstring to describe the current typed runtime-row seam
- keep function docstrings focused on current purpose and boundary, not the old dict-heavy implementation detail

Low-value wording to remove:
- comments or docstrings that restate assignment-level mechanics
- repeated wording that explains export-edge dict payloads in every helper

Best next code-doc pass:
- adjust the nearest module and function docstrings only
- reread the owning tests once if the boundary wording still feels ambiguous
