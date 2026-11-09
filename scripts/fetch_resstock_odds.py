"""Download ResStock's odds (housing_characteristics tables) for the preset's characteristics.

    uv run python scripts/fetch_resstock_odds.py

Saves NREL/resstock's project_national/housing_characteristics/<Characteristic>.tsv at the
template's tag into templates/resstock-odds/<tag>/, unchanged, for "From ResStock's odds" on
Building Characteristics (services/resstock_odds.py). Each row is one combination of the
characteristic's dependencies, with the share of homes taking each option and
`sampling_probability`, how common that combination is among ResStock's homes.
"""

from __future__ import annotations

import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "templates" / "projects" / "resstock" / "resstock-preset.yml"
URL = "https://raw.githubusercontent.com/NREL/resstock/{tag}/project_national/housing_characteristics/{name}.tsv"


def main() -> None:
    preset = yaml.safe_load(PRESET.read_text())
    tag = preset["source"]["tag"]
    out = ROOT / "templates" / "resstock-odds" / tag
    out.mkdir(parents=True, exist_ok=True)
    for characteristic in preset["characteristics"]:
        name = characteristic["name"]
        url = URL.format(tag=tag, name=urllib.parse.quote(name))
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed https URL
                (out / f"{name}.tsv").write_bytes(response.read())
        except OSError as exc:
            sys.exit(f"Could not download {url}: {exc}")
        print(f"{name}: saved")
    # the tables are ResStock's, redistributed unchanged under its license (the text after the template NOTICE's intro)
    license_text = (PRESET.parent / "NOTICE").read_text().split("\n\n", 1)[1]
    (out / "NOTICE").write_text(
        f"The .tsv files here are unchanged copies of ResStock {tag} project_national/housing_characteristics/,\n"
        f"from https://github.com/NREL/resstock, under its license:\n\n{license_text}"
    )


if __name__ == "__main__":
    main()
