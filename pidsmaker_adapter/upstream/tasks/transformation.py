import os

import torch

from pidsmaker_adapter.upstream.config import update_cfg_for_multi_dataset
from pidsmaker_adapter.upstream.preprocessing.transformation_methods import (
    transformation_dag,
    transformation_rcaid_pseudo_graph,
    transformation_undirected,
)
from pidsmaker_adapter.upstream.utils.utils import (
    copy_directory,
    get_all_graphs_for_dates,
    get_multi_datasets,
    load_graphs_for_dates,
    log_start,
    log_tqdm,
    set_seed,
)


def no_transformation(base_dir, dst_dir):
    # If no transformation is used, we copy all original graphs to the transformation task path
    copy_directory(base_dir, dst_dir)


def add_graph_transformation(base_dir, dst_dir, cfg, methods):
    os.makedirs(dst_dir, exist_ok=True)

    dates = cfg.dataset.train_dates + cfg.dataset.val_dates + cfg.dataset.test_dates
    for date in log_tqdm(dates, desc="Transforming"):
        sorted_paths = get_all_graphs_for_dates(base_dir, [date])
        for path in sorted_paths:
            graph = torch.load(path)

            # Apply all transformations to a single graph
            graph = apply_graph_transformations(graph, methods, cfg)

            file_name = path.split("/")[-1]
            dst_path = os.path.join(dst_dir, f"graph_{date}")
            os.makedirs(dst_path, exist_ok=True)
            torch.save(graph, os.path.join(dst_path, file_name))


def apply_graph_transformations(graph, methods, cfg):
    for method in methods:
        if method == "none":
            pass
        elif method == "rcaid_pseudo_graph":
            graph = transformation_rcaid_pseudo_graph.main(graph, cfg)
        elif method == "undirected":
            graph = transformation_undirected.main(graph)
        elif method == "dag":
            graph = transformation_dag.main(graph)
        else:
            raise ValueError(f"Unrecognized transformation method: {method}")

    return graph


def main_from_config(cfg):
    methods = cfg.transformation.used_methods
    methods = list(map(lambda x: x.strip(), methods.split(",")))

    base_dir = cfg.construction._graphs_dir
    dst_dir = cfg.transformation._graphs_dir

    if len(methods) == 1 and methods[0] == "none":
        no_transformation(base_dir, dst_dir)

    else:
        add_graph_transformation(base_dir, dst_dir, cfg, methods)


def main(cfg):
    set_seed(cfg)
    log_start(__file__)

    multi_datasets = get_multi_datasets(cfg)
    if "none" in multi_datasets:
        main_from_config(cfg)

    # Multi-dataset mode
    else:
        for dataset in multi_datasets:
            updated_cfg, should_restart = update_cfg_for_multi_dataset(cfg, dataset)

            if should_restart["transformation"]:
                main_from_config(updated_cfg)
