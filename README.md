# Abaqus plate-soil case runner

This folder is a handoff package for running circular plate-soil axisymmetric Abaqus cases from Python scripts.

It is designed for limited Abaqus access:

1. Edit one JSON config in `configs/after_meeting_rdr/.../config.json`.
2. Send this folder to the person with Abaqus.
3. They run one case at a time with `run_one_case.ps1`.
4. Abaqus creates the ODB and extracts CSV data.
5. Normal Python creates an editable Excel workbook with journal-style charts.

## What it models

The generated model is a 2D axisymmetric circular plate on layered soil:

- soil radius is `100 * rp` by default
- bottom boundary at `H_total`: vertical deflection fixed
- far boundary at `100 * rp`: radial and vertical deflections fixed
- symmetry axis at `r = 0`: radial displacement fixed
- very fine mesh bands can be specified near the soil surface, plate-soil interface, and small radii
- plate is modeled as continuum axisymmetric elements so interface displacements and stress-based plate force resultants can be extracted

## Quick start

Create the normal Python virtual environment for Excel post-processing:

```powershell
.\setup_venv.ps1
```

Run one Abaqus case:

```powershell
.\run_one_case.ps1 -CaseConfig configs\after_meeting_rdr\1l\config.json
```

Create the Excel workbook after Abaqus finishes:

```powershell
.\.venv\Scripts\python.exe src\make_workbook.py --case configs\after_meeting_rdr\1l\config.json
```

The workbook will be written under the case output folder.

## Files

- `src/abaqus_build_run.py`: Abaqus CAE script that builds, meshes, and submits one model.
- `src/abaqus_extract_odb.py`: Abaqus Python script that extracts displacements, decay ratios, stresses, strains, and plate resultants from one ODB.
- `src/make_workbook.py`: normal Python script that creates an editable `.xlsx` with data sheets and native Excel charts.
- `src/describe_case.py`: normal Python script that prints the material, geometry, mesh, boundary, and extraction plan from a config.
- `configs/after_meeting_rdr/*/config.json`: editable case inputs.
- `run_one_case.ps1`: one-case runner for the Abaqus computer.
- `setup_venv.ps1`: creates a local `.venv` and installs Excel/reporting dependencies.

## Important notes

- Replace the placeholder material properties and load values in each `config.json` before production runs.
- The scripts use JSON because it is available in Abaqus Python without installing extra packages.
- If your Abaqus version uses Python 2, keep `src/abaqus_build_run.py` and `src/abaqus_extract_odb.py` syntax conservative.
- The plate moments and shear forces are stress-integrated approximations from continuum plate elements. If you later switch to shell/structural plate elements, the extractor can be extended to read native section force outputs.

