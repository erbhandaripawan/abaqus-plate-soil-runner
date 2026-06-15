import argparse
import os

from config_io import case_name, load_config, sample_depths, sample_radii


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", "--config", dest="case", required=True)
    args = parser.parse_args()

    cfg = load_config(args.case)
    g = cfg["geometry"]
    print("Case: {}".format(case_name(cfg)))
    print("Config: {}".format(os.path.abspath(args.case)))
    print("")
    print("Geometry")
    print("  plate radius rp: {}".format(g["plate_radius"]))
    print("  plate thickness: {}".format(g["plate_thickness"]))
    print("  soil depth H_total: {}".format(g["soil_depth"]))
    print("  soil radius: {} * rp".format(g.get("soil_radius_factor", 100.0)))
    print("")
    print("Materials")
    print("  plate: {}".format(cfg["plate"]["material"]))
    for layer in cfg["soil_layers"]:
        print("  soil layer {name}: top={top_depth}, bottom={bottom_depth}, material={material}".format(**layer))
    print("")
    print("Boundary conditions")
    print("  r=0: U1 = 0")
    print("  z=-H_total: U2 = 0")
    print("  r=100rp: U1 = 0 and U2 = 0")
    print("")
    print("Extraction radii")
    for factor, radius in sample_radii(cfg):
        print("  {:>4g} rp = {}".format(factor, radius))
    print("")
    print("Extraction depths")
    for depth in sample_depths(cfg):
        print("  {}".format(depth))


if __name__ == "__main__":
    main()

