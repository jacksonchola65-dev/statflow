# Luapula District Population Verification Staging Artifact

Status: STAGED ONLY; not imported into StatFlow, not persisted in the database, and not used for production ingestion yet.

## Source

- Publication: 2022 Census of Population and Housing Summary Report Part 2
- Official source URL: https://www.zamstats.gov.zm/2022-census-of-population-and-housing-summary-report-part-2/
- Table: "Dejure Population by Sex, Rural/Urban, Province, District, Constituency and Ward, Zambia 2022"
- PDF page: 45
- Verification criterion: district rows matched against the canonical Luapula district list in the repo and the population values were extracted from the official PDF.

## Scope

This staging artifact includes exactly 12 Luapula districts and reflects the de jure 2022 census population totals from the official ZamStats publication.

## District Values

| District | Code | Total | Male | Female | Rural | Urban |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Chembe | LP-CHEMBE | 51,634 | 26,205 | 25,429 | 51,634 | 0 |
| Chienge | LP-CHIENGE | 190,566 | 94,023 | 96,543 | 175,401 | 15,165 |
| Chifunabuli | LP-CHIFUNABULI | 116,634 | 57,015 | 59,619 | 81,391 | 35,243 |
| Chipili | LP-CHIPILI | 47,473 | 23,676 | 23,797 | 47,473 | 0 |
| Kawambwa | LP-KAWAMBWA | 124,046 | 61,491 | 62,555 | 92,885 | 31,161 |
| Lunga | LP-LUNGA | 39,462 | 19,343 | 20,119 | 39,462 | 0 |
| Mansa | LP-MANSA | 329,622 | 161,891 | 167,731 | 157,899 | 171,723 |
| Milenge | LP-MILENGE | 56,638 | 27,776 | 28,862 | 56,638 | 0 |
| Mwansabombwe | LP-MWANSABOMBWE | 58,992 | 28,602 | 30,390 | 42,915 | 16,077 |
| Mwense | LP-MWENSE | 122,796 | 59,873 | 62,923 | 115,888 | 6,908 |
| Nchelenge | LP-NCHELENGE | 234,259 | 116,149 | 118,110 | 156,513 | 77,746 |
| Samfya | LP-SAMFYA | 147,356 | 71,354 | 76,002 | 96,047 | 51,309 |

## Review Notes

- The values come from the official ZamStats 2022 census report and not from illustrative demo data.
- The district list matches the canonical repo district list for Luapula.
- The staging artifact is intentionally limited to review and approval; no import or write step has occurred.
- Source row integrity: 12 district rows, 1 province row not imported, no duplicates, no non-official rows.

## Files

- CSV artifact: [docs/evidence/luapula_district_population_2022_verified.csv](luapula_district_population_2022_verified.csv)
- Review summary: [docs/evidence/luapula_district_population_2022_verified.md](luapula_district_population_2022_verified.md)
