from __future__ import print_function

import json
import os


def load_config(path):
    path = os.path.abspath(path)
    with open(path, "r") as f:
        cfg = json.load(f)
    cfg["_config_path"] = path
    cfg["_case_dir"] = os.path.dirname(path)
    cfg.setdefault("output", {})
    out_dir = cfg["output"].get("directory")
    if not out_dir:
        out_dir = os.path.join(cfg["_case_dir"], "outputs")
    if not os.path.isabs(out_dir):
        out_dir = os.path.abspath(os.path.join(cfg["_case_dir"], out_dir))
    cfg["output"]["directory"] = out_dir
    return cfg


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def sample_radii(config):
    rp = float(config["geometry"]["plate_radius"])
    factors = config.get("extraction", {}).get("radius_factors", [0.0, 0.2, 0.5, 0.8, 1.0, 1.2])
    return [(float(f), float(f) * rp) for f in factors]


def sample_depths(config):
    depths = config.get("extraction", {}).get("depths")
    if depths:
        return [float(d) for d in depths]
    h_total = float(config["geometry"]["soil_depth"])
    return [0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 0.25 * h_total, 0.5 * h_total, h_total]


def case_name(config):
    return config.get("case_name") or os.path.basename(config["_case_dir"])

