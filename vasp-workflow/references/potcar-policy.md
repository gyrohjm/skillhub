# POTCAR Policy

Default POTCAR functional is `PBE`.

Use a private local catalog when available:

```text
references/potcar-catalog.local.json
```

That file is ignored by git. Do not commit or publish real POTCAR contents or
private licensed paths.

If the catalog is missing, incomplete, or ambiguous, ask the user to confirm the
POTCAR path or element-specific label before generating or submitting inputs.
The Agent may default the functional to PBE, but it must not silently choose the
concrete POTCAR label/path when multiple choices are plausible.

Default cluster POTCAR roots:

```text
nmg: /home/jmhe/app/pot
phoenix, phoenix-gpu-a100, phoenix-gpu-g3: /home/jmhe/app/pot_database
generic: no default; require --potcar or --potcar-root
```

For standard `vwf prepare relax|scf|band|dos`, prefer an explicit `--potcar`
when the user has already selected a concatenated file. Otherwise the helper may
search the profile default root or `--potcar-root`, parse POSCAR element order,
and concatenate one uniquely matched `POTCAR` per element. Use
`--potcar-label ELEMENT=LABEL` for labels such as `Si_GW` or `O_s`.

If an element is missing or more than one candidate exists, stop and show the
missing element or candidate paths. Do not guess.

Every submit review must show:

- functional, normally `PBE`;
- element order as used by POSCAR/POTCAR;
- POTCAR labels or `TITEL` lines;
- source path;
- auto-resolution root and per-element component paths when generated;
- SHA256 hash;
- statement that POTCAR content must not be committed to public repositories.

Suggested private catalog shape:

```json
{
  "default_functional": "PBE",
  "potcars": [
    {
      "functional": "PBE",
      "element": "Si",
      "label": "Si",
      "title": "PAW_PBE Si 05Jan2001",
      "path": "/private/path/to/PBE/Si/POTCAR",
      "sha256": "<sha256>"
    }
  ]
}
```

For multi-element systems, concatenate POTCAR files in the same element order as
POSCAR and report each component label/title/hash when possible.
