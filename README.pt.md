# br-maps

🇧🇷 Português | [🇺🇸 English](README.md)

Arquivos GeoJSON das malhas territoriais oficiais do Brasil, mantidos automaticamente atualizados a partir do [IBGE](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html).

Um workflow do GitHub Actions executa diariamente, baixa os shapefiles mais recentes do servidor FTP do IBGE, converte para GeoJSON e commita as alterações neste repositório. Arquivos grandes são armazenados via [Git LFS](https://git-lfs.com).

## Dados

Todos os arquivos ficam em `data/latest/` e seguem o padrão de nome `{escopo}_{tipo}.geojson`.

### Escopos

| Prefixo | Descrição |
|---|---|
| `BR` | Brasil (nível nacional) |
| `AC` `AL` `AM` `AP` `BA` `CE` `DF` `ES` `GO` `MA` `MG` `MS` `MT` `PA` `PB` `PE` `PI` `PR` `RJ` `RN` `RO` `RR` `RS` `SC` `SE` `SP` `TO` | Cada uma das 27 Unidades da Federação |

### Tipos

| Sufixo | Descrição |
|---|---|
| `_Municipios` | Limites municipais — maior granularidade |
| `_RG_Imediatas` | Regiões Geográficas Imediatas — agrupamentos de municípios com relações funcionais cotidianas (deslocamento, saúde, comércio) |
| `_RG_Intermediarias` | Regiões Geográficas Intermediárias — agrupamentos de Regiões Imediatas em torno de cidades de maior influência |
| `_UF` | Limite estadual |
| `_Regioes` | Grandes Regiões (Norte, Nordeste, Centro-Oeste, Sudeste, Sul) — apenas nível Brasil |

**Exemplos para Minas Gerais:**

```
data/latest/MG_Municipios.geojson         # 853 municípios
data/latest/MG_RG_Imediatas.geojson       # ~94 regiões imediatas
data/latest/MG_RG_Intermediarias.geojson  # ~12 regiões intermediárias
data/latest/MG_UF.geojson                 # contorno do estado (1 polígono)
```

### Hierarquia geográfica (menor → maior)

```
Município → RG Imediata → RG Intermediária → UF → Grande Região → Brasil
```

## Fonte

Todos os shapefiles são obtidos do FTP oficial do IBGE:

```
https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_{ano}/
```

O ano é detectado automaticamente. Se o IBGE não publicou atualizações desde a última execução, nenhum commit é feito (detecção de mudanças via headers HTTP + SHA256).

## Executando localmente

```bash
# Instalar dependências (Python 3.12+)
pip install -r scripts/requirements.txt

# Baixar e converter todos os arquivos
python scripts/download_convert.py
```

Os arquivos são gravados em `data/latest/`. O progresso e eventuais erros são exibidos no stdout. O script é incremental — execuções subsequentes só rebaixam arquivos que foram alterados na origem.

## Automação

O workflow `.github/workflows/update-maps.yml` executa todos os dias às 06:00 UTC e também pode ser disparado manualmente pela aba **Actions**.

Não requer segredos — utiliza o `GITHUB_TOKEN` padrão com permissão `contents: write`.

## Licença

Dados geográficos © [IBGE](https://www.ibge.gov.br). Os scripts deste repositório estão licenciados sob a licença MIT.
