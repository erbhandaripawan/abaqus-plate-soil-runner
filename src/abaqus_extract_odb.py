from __future__ import print_function

import csv
import math
import os
import sys

from odbAccess import openOdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_io import case_name, ensure_dir, load_config, sample_depths, sample_radii


def parse_args(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    config = None
    i = 0
    while i < len(argv):
        if argv[i] == "--config":
            config = argv[i + 1]
            i += 2
        else:
            i += 1
    if not config:
        raise RuntimeError("Usage: abaqus python src/abaqus_extract_odb.py -- --config path/to/config.json")
    return config


def nearest_node(nodes, r_target, z_target):
    best = None
    best_d2 = None
    for node in nodes:
        r = float(node.coordinates[0])
        z = float(node.coordinates[1])
        d2 = (r - r_target) ** 2 + (z - z_target) ** 2
        if best is None or d2 < best_d2:
            best = node
            best_d2 = d2
    return best, math.sqrt(best_d2)


def write_csv(path, header, rows):
    if sys.version_info[0] < 3:
        f = open(path, "wb")
    else:
        f = open(path, "w", newline="")
    with f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def element_centroids(instance):
    nodes = dict((n.label, n.coordinates) for n in instance.nodes)
    out = {}
    sizes = {}
    for elem in instance.elements:
        pts = [nodes[label] for label in elem.connectivity]
        rs = [float(p[0]) for p in pts]
        zs = [float(p[1]) for p in pts]
        out[elem.label] = (sum(rs) / len(rs), sum(zs) / len(zs))
        sizes[elem.label] = (max(rs) - min(rs), max(zs) - min(zs))
    return out, sizes


def field_by_node(frame, name):
    field = frame.fieldOutputs[name]
    out = {}
    for value in field.values:
        if value.nodeLabel:
            out[(value.instance.name, value.nodeLabel)] = value.data
    return out


def main():
    cfg = load_config(parse_args(sys.argv))
    out_dir = cfg["output"]["directory"]
    job_name = cfg.get("job", {}).get("name", case_name(cfg))
    odb_path = cfg.get("output", {}).get("odb_path") or os.path.join(out_dir, job_name + ".odb")
    ensure_dir(out_dir)

    odb = openOdb(path=odb_path, readOnly=True)
    step_name = cfg.get("output", {}).get("step_name", "LOAD")
    step = odb.steps[step_name]
    frame = step.frames[-1]
    soil = odb.rootAssembly.instances["SOIL-1"]
    plate = odb.rootAssembly.instances["PLATE-1"]

    u_by_node = field_by_node(frame, "U")
    radii = sample_radii(cfg)
    depths = sample_depths(cfg)

    disp_rows = []
    surface_by_factor = {}
    for factor, radius in radii:
        node, distance = nearest_node(soil.nodes, radius, 0.0)
        u = u_by_node.get(("SOIL-1", node.label), (None, None))
        surface_by_factor[factor] = u[1]
        disp_rows.append([factor, radius, 0.0, node.label, distance, u[0], u[1], "surface"])
        for depth in depths:
            node, distance = nearest_node(soil.nodes, radius, -float(depth))
            u = u_by_node.get(("SOIL-1", node.label), (None, None))
            disp_rows.append([factor, radius, depth, node.label, distance, u[0], u[1], "soil"])

    write_csv(
        os.path.join(out_dir, "displacements.csv"),
        ["radius_factor", "radius", "depth", "node_label", "nearest_distance", "radial_U1", "vertical_U2", "location"],
        disp_rows,
    )

    decay_rows = []
    for row in disp_rows:
        factor = row[0]
        surface = surface_by_factor.get(factor)
        vertical = row[6]
        ratio = ""
        if surface not in (None, 0.0) and vertical is not None:
            ratio = vertical / surface
        decay_rows.append(row[:7] + [surface, ratio])
    write_csv(
        os.path.join(out_dir, "decay.csv"),
        ["radius_factor", "radius", "depth", "node_label", "nearest_distance", "radial_U1", "vertical_U2", "surface_vertical_U2", "decay_ratio"],
        decay_rows,
    )

    centroid_by_inst = {}
    size_by_inst = {}
    for inst in [soil, plate]:
        centroid_by_inst[inst.name], size_by_inst[inst.name] = element_centroids(inst)

    for field_name, file_name in [("S", "stresses.csv"), ("E", "strains.csv")]:
        rows = []
        if field_name in frame.fieldOutputs:
            for value in frame.fieldOutputs[field_name].values:
                inst_name = value.instance.name
                centroid = centroid_by_inst.get(inst_name, {}).get(value.elementLabel, ("", ""))
                data = list(value.data)
                while len(data) < 4:
                    data.append("")
                rows.append([inst_name, value.elementLabel, value.integrationPoint, centroid[0], centroid[1]] + data[:6])
        write_csv(
            os.path.join(out_dir, file_name),
            ["instance", "element_label", "integration_point", "centroid_r", "centroid_z", "c11", "c22", "c33", "c12", "c13", "c23"],
            rows,
        )

    moment_rows = []
    rp = float(cfg["geometry"]["plate_radius"])
    t = float(cfg["geometry"]["plate_thickness"])
    bin_count = int(cfg.get("extraction", {}).get("plate_resultant_bins", 50))
    bins = {}
    if "S" in frame.fieldOutputs:
        for value in frame.fieldOutputs["S"].values:
            if value.instance.name != "PLATE-1":
                continue
            r, z = centroid_by_inst["PLATE-1"].get(value.elementLabel, (None, None))
            dr, dz = size_by_inst["PLATE-1"].get(value.elementLabel, (0.0, 0.0))
            if r is None:
                continue
            idx = min(bin_count - 1, max(0, int((r / rp) * bin_count)))
            bins.setdefault(idx, {"r_sum": 0.0, "w_sum": 0.0, "mr": 0.0, "mt": 0.0, "q": 0.0})
            data = list(value.data)
            s11 = float(data[0]) if len(data) > 0 else 0.0
            s33 = float(data[2]) if len(data) > 2 else 0.0
            s12 = float(data[3]) if len(data) > 3 else 0.0
            z_rel = z - 0.5 * t
            weight = abs(dz) if abs(dz) > 0.0 else t / max(1, bin_count)
            bins[idx]["r_sum"] += r * weight
            bins[idx]["w_sum"] += weight
            bins[idx]["mr"] += s11 * z_rel * weight
            bins[idx]["mt"] += s33 * z_rel * weight
            bins[idx]["q"] += s12 * weight
    for idx in sorted(bins):
        b = bins[idx]
        r_mean = b["r_sum"] / b["w_sum"] if b["w_sum"] else ""
        moment_rows.append([idx, r_mean, b["mr"], b["mt"], b["q"]])
    write_csv(
        os.path.join(out_dir, "plate_resultants.csv"),
        ["radius_bin", "radius", "M_radial_approx", "M_hoop_approx", "Q_radial_approx"],
        moment_rows,
    )

    odb.close()
    print("Extracted ODB results to {}".format(out_dir))


if __name__ == "__main__":
    main()
