#!/usr/bin/env python3
import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.base, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    config["model_name"] = "clust_cats_16"
    config["model_save_path"] = str(Path(args.models).resolve()) + "/"
    config["from_checkpoint"] = ""
    config["device"] = "cpu"
    config["low_memory"] = True
    config["save_vis_imgs"] = False
    with open(args.output, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)


if __name__ == "__main__":
    main()
