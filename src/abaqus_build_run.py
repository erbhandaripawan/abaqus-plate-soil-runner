from __future__ import print_function

import os
import sys

from abaqus import *
from abaqusConstants import *
import mesh
import regionToolset

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_io import case_name, ensure_dir, load_config


def parse_args(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    config = None
    skip_submit = False
    i = 0
    while i < len(argv):
        if argv[i] == "--config":
            config = argv[i + 1]
            i += 2
        elif argv[i] == "--skip-submit":
            skip_submit = True
            i += 1
        else:
            i += 1
    if not config:
        raise RuntimeError("Usage: abaqus cae noGUI=src/abaqus_build_run.py -- --config path/to/config.json")
    return config, skip_submit


def make_material(model, name, props):
    mat = model.Material(name=name)
    mat.Elastic(table=((float(props["elastic_modulus"]), float(props["poisson_ratio"])),))
    if props.get("density") is not None:
        mat.Density(table=((float(props["density"]),),))
    return mat


def find_edges_by_midpoint(part, predicate):
    found = []
    for edge in part.edges:
        p = edge.pointOn[0]
        if predicate(float(p[0]), float(p[1])):
            found.append(edge)
    return found


def find_faces_by_centroid(part, predicate):
    found = []
    for face in part.faces:
        p = face.getCentroid()
        if predicate(float(p[0]), float(p[1])):
            found.append(face)
    return found


def create_model(cfg):
    name = case_name(cfg)
    if name in mdb.models:
        del mdb.models[name]
    model = mdb.Model(name=name)

    g = cfg["geometry"]
    rp = float(g["plate_radius"])
    t_plate = float(g["plate_thickness"])
    h_total = float(g["soil_depth"])
    soil_radius = rp * float(g.get("soil_radius_factor", 100.0))

    for material_name, material_props in cfg["materials"].items():
        make_material(model, material_name, material_props)

    sketch = model.ConstrainedSketch(name="soil_profile", sheetSize=max(soil_radius, h_total) * 2.5)
    sketch.rectangle(point1=(0.0, -h_total), point2=(soil_radius, 0.0))
    soil = model.Part(name="SOIL", dimensionality=AXISYMMETRIC, type=DEFORMABLE_BODY)
    soil.BaseShell(sketch=sketch)
    del model.sketches["soil_profile"]

    face = soil.faces[0]
    partition_depths = set([0.0, h_total])
    partition_radii = set([0.0, rp, soil_radius])
    for layer in cfg["soil_layers"]:
        partition_depths.add(float(layer["top_depth"]))
        partition_depths.add(float(layer["bottom_depth"]))
    for d in cfg.get("mesh", {}).get("depth_breaks", []):
        partition_depths.add(float(d))
    for rf in cfg.get("mesh", {}).get("radial_break_factors", []):
        partition_radii.add(float(rf) * rp)

    for depth in sorted(partition_depths):
        if depth <= 0.0 or depth >= h_total:
            continue
        sketch = model.ConstrainedSketch(name="soil_depth_partition", sheetSize=max(soil_radius, h_total) * 2.5)
        sketch.Line(point1=(0.0, -depth), point2=(soil_radius, -depth))
        soil.PartitionFaceBySketch(faces=soil.faces[:], sketch=sketch)
        del model.sketches["soil_depth_partition"]

    for radius in sorted(partition_radii):
        if radius <= 0.0 or radius >= soil_radius:
            continue
        sketch = model.ConstrainedSketch(name="soil_radius_partition", sheetSize=max(soil_radius, h_total) * 2.5)
        sketch.Line(point1=(radius, -h_total), point2=(radius, 0.0))
        soil.PartitionFaceBySketch(faces=soil.faces[:], sketch=sketch)
        del model.sketches["soil_radius_partition"]

    for layer in cfg["soil_layers"]:
        sec_name = "SEC_{}".format(layer["name"])
        model.HomogeneousSolidSection(name=sec_name, material=layer["material"], thickness=None)
        top = float(layer["top_depth"])
        bottom = float(layer["bottom_depth"])
        faces = find_faces_by_centroid(soil, lambda r, z, top=top, bottom=bottom: -bottom <= z <= -top)
        soil.SectionAssignment(region=regionToolset.Region(faces=faces), sectionName=sec_name)

    sketch = model.ConstrainedSketch(name="plate_profile", sheetSize=max(rp, t_plate) * 4.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=(rp, t_plate))
    plate = model.Part(name="PLATE", dimensionality=AXISYMMETRIC, type=DEFORMABLE_BODY)
    plate.BaseShell(sketch=sketch)
    del model.sketches["plate_profile"]
    model.HomogeneousSolidSection(name="SEC_PLATE", material=cfg["plate"]["material"], thickness=None)
    plate.SectionAssignment(region=regionToolset.Region(faces=plate.faces[:]), sectionName="SEC_PLATE")

    elem_type = mesh.ElemType(elemCode=CAX4R, elemLibrary=STANDARD)
    soil.setElementType(regions=(soil.faces[:],), elemTypes=(elem_type,))
    plate.setElementType(regions=(plate.faces[:],), elemTypes=(elem_type,))

    mesh_cfg = cfg.get("mesh", {})
    soil.seedPart(size=float(mesh_cfg.get("global_soil_size", rp)), deviationFactor=0.1, minSizeFactor=0.1)
    plate.seedPart(size=float(mesh_cfg.get("plate_size", rp / 20.0)), deviationFactor=0.1, minSizeFactor=0.1)

    fine_depth = float(mesh_cfg.get("fine_depth", min(2.0, 0.1 * h_total)))
    fine_radius = float(mesh_cfg.get("fine_radius_factor", 1.2)) * rp
    fine_size = float(mesh_cfg.get("fine_size", rp / 40.0))
    for edge in soil.edges:
        p = edge.pointOn[0]
        r = float(p[0])
        z = float(p[1])
        if r <= fine_radius and z >= -fine_depth:
            length = edge.getSize()
            n = max(1, int(round(length / fine_size)))
            soil.seedEdgeByNumber(edges=(edge,), number=n, constraint=FINER)

    plate.generateMesh()
    soil.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CYLINDRICAL)
    soil_i = assembly.Instance(name="SOIL-1", part=soil, dependent=ON)
    plate_i = assembly.Instance(name="PLATE-1", part=plate, dependent=ON)

    soil_top_edges = soil_i.edges.getByBoundingBox(xMin=-1e-9, xMax=rp + 1e-9, yMin=-1e-9, yMax=1e-9)
    plate_bottom_edges = plate_i.edges.getByBoundingBox(xMin=-1e-9, xMax=rp + 1e-9, yMin=-1e-9, yMax=1e-9)
    model.Tie(
        name="plate_soil_tie",
        main=regionToolset.Region(side1Edges=plate_bottom_edges),
        secondary=regionToolset.Region(side1Edges=soil_top_edges),
        positionToleranceMethod=COMPUTED,
        adjust=ON,
        tieRotations=ON,
        thickness=ON,
    )

    model.StaticStep(name="LOAD", previous="Initial", nlgeom=OFF)
    model.fieldOutputRequests["F-Output-1"].setValues(variables=("S", "E", "U", "RF"))

    axis_edges = soil_i.edges.getByBoundingBox(xMin=-1e-9, xMax=1e-9)
    plate_axis_edges = plate_i.edges.getByBoundingBox(xMin=-1e-9, xMax=1e-9)
    model.DisplacementBC(name="axis_u1_zero", createStepName="Initial",
                         region=regionToolset.Region(edges=axis_edges), u1=0.0)
    model.DisplacementBC(name="plate_axis_u1_zero", createStepName="Initial",
                         region=regionToolset.Region(edges=plate_axis_edges), u1=0.0)

    bottom_edges = soil_i.edges.getByBoundingBox(yMin=-h_total - 1e-9, yMax=-h_total + 1e-9)
    model.DisplacementBC(name="bottom_u2_zero", createStepName="Initial",
                         region=regionToolset.Region(edges=bottom_edges), u2=0.0)

    far_edges = soil_i.edges.getByBoundingBox(xMin=soil_radius - 1e-9, xMax=soil_radius + 1e-9)
    model.DisplacementBC(name="far_u_zero", createStepName="Initial",
                         region=regionToolset.Region(edges=far_edges), u1=0.0, u2=0.0)

    plate_top_edges = plate_i.edges.getByBoundingBox(xMin=-1e-9, xMax=rp + 1e-9, yMin=t_plate - 1e-9, yMax=t_plate + 1e-9)
    load = cfg.get("loading", {})
    pressure = float(load.get("pressure", 1.0))
    model.Pressure(name="plate_pressure", createStepName="LOAD",
                   region=regionToolset.Region(side1Edges=plate_top_edges), magnitude=pressure)

    job_cfg = cfg.get("job", {})
    job_name = job_cfg.get("name", name)
    out_dir = cfg["output"]["directory"]
    ensure_dir(out_dir)
    os.chdir(out_dir)
    job = mdb.Job(
        name=job_name,
        model=name,
        description="Generated axisymmetric plate-soil case {}".format(name),
        numCpus=int(job_cfg.get("num_cpus", 1)),
        numDomains=int(job_cfg.get("num_domains", job_cfg.get("num_cpus", 1))),
        memory=int(job_cfg.get("memory_percent", 90)),
        memoryUnits=PERCENTAGE,
    )
    return job, os.path.join(out_dir, job_name + ".cae")


def main():
    config_path, skip_submit = parse_args(sys.argv)
    cfg = load_config(config_path)
    job, cae_path = create_model(cfg)
    mdb.saveAs(pathName=cae_path)
    if not skip_submit:
        job.submit(consistencyChecking=OFF)
        job.waitForCompletion()
    print("Abaqus model complete: {}".format(cae_path))


if __name__ == "__main__":
    main()
