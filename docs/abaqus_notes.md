# Abaqus implementation notes

These scripts use standard Abaqus/CAE and ODB scripting patterns:

- build the model with `mdb.Model`, `Part`, `ConstrainedSketch`, sections, assembly instances, steps, loads, and boundary conditions
- submit an Abaqus `Job`
- read results with `openOdb`
- use field outputs `U`, `S`, `E`, `RF`, and `COORD`

The Abaqus scripts are kept mostly Python 2 compatible because many Abaqus installations before 2024 still embed Python 2.7.

## Boundary conditions

- Symmetry axis at `r = 0`: `U1 = 0`
- Very stiff lower layer / bottom at `H_total`: `U2 = 0`
- Far field at `100rp`: `U1 = 0`, `U2 = 0`

## Requested outputs

- radial deflection `U1` and vertical deflection `U2` at plate-soil interface and in soil
- decay function `U2(depth) / U2(surface)` at `r = 0, 0.2rp, 0.5rp, 0.8rp, rp, 1.2rp`
- stresses from `S`
- strains from `E`
- approximate plate moments and shear forces from continuum plate stress integration

## Mesh strategy

The config controls:

- global soil mesh size
- plate mesh size
- a fine near-field band using `fine_depth`, `fine_radius_factor`, and `fine_size`
- partition breaks in depth and radius

For production, start with a modest mesh, verify that the job solves, then reduce `fine_size` and add additional depth/radius breaks near the interface.

