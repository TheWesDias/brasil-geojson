# br-maps

GeoJSON files for Brazil's official territorial meshes, automatically kept up to date from [IBGE](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html).

A GitHub Actions workflow runs daily, downloads the latest shapefiles from IBGE's FTP server, converts them to GeoJSON, and commits any changes to this repository. Large files are stored via [Git LFS](https://git-lfs.com).

## Data

All files live under `data/latest/` and are named `{scope}_{type}.geojson`.

### Scopes

| Prefix | Description |
|---|---|
| `BR` | Brazil (national) |
| `AC` `AL` `AM` `AP` `BA` `CE` `DF` `ES` `GO` `MA` `MG` `MS` `MT` `PA` `PB` `PE` `PI` `PR` `RJ` `RN` `RO` `RR` `RS` `SC` `SE` `SP` `TO` | Each of the 27 states (Unidades da Federação) |

### Types

| Suffix | Description |
|---|---|
| `_Municipios` | Municipality (county) boundaries — finest granularity |
| `_RG_Imediatas` | Immediate Geographic Regions — clusters of municipalities sharing daily functional ties (commuting, healthcare, commerce) |
| `_RG_Intermediarias` | Intermediate Geographic Regions — groups of Immediate Regions centered on major cities |
| `_UF` | State boundary |
| `_Regioes` | Macro-regions (Norte, Nordeste, Centro-Oeste, Sudeste, Sul) — Brazil level only |

**Example files for Minas Gerais:**

```
data/latest/MG_Municipios.geojson         # 853 municipalities
data/latest/MG_RG_Imediatas.geojson       # ~94 immediate regions
data/latest/MG_RG_Intermediarias.geojson  # ~12 intermediate regions
data/latest/MG_UF.geojson                 # state outline (1 polygon)
```

### Geographic hierarchy (smallest → largest)

```
Município → RG Imediata → RG Intermediária → UF → Grande Região → Brasil
```

## Source

All shapefiles are sourced from IBGE's official FTP:

```
https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_{year}/
```

The year is detected automatically. If IBGE hasn't published updates since the last run, no commit is made (change detection uses HTTP cache headers + SHA256).

## Running locally

```bash
# Install dependencies (Python 3.12+)
pip install -r scripts/requirements.txt

# Download and convert all files
python scripts/download_convert.py
```

Output is written to `data/latest/`. Progress and any errors are logged to stdout. The script is incremental — subsequent runs only re-download files that changed upstream.

## Automation

The workflow `.github/workflows/update-maps.yml` runs every day at 06:00 UTC and can also be triggered manually from the **Actions** tab.

It requires no secrets — it uses the default `GITHUB_TOKEN` with `contents: write` permission.

## License

Geographic data © [IBGE](https://www.ibge.gov.br). Scripts in this repository are MIT licensed.
