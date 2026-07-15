"""Train-only optimization with validation-only checkpoint selection."""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn.parameter import UninitializedBuffer, UninitializedParameter

from pidsmaker_adapter.upstream.factory import build_model, optimizer_factory
from pidsmaker_adapter.upstream.tasks.batching import get_preprocessed_graphs
from pidsmaker_adapter.upstream.utils.data_utils import save_model
from pidsmaker_adapter.upstream.utils.utils import get_device, set_seed


def _batches(data_groups):
    for group in data_groups:
        for batch in group:
            yield batch


def _state_dict_to_cpu(model: Any) -> dict[str, Any]:
    result = {}
    for name, value in model.state_dict().items():
        if isinstance(value, (UninitializedParameter, UninitializedBuffer)):
            result[name] = copy.deepcopy(value)
        else:
            result[name] = value.detach().cpu().clone()
    return result


@torch.no_grad()
def validation_loss(cfg: Any, model: Any, val_data: Any) -> float:
    device = get_device(cfg)
    model.to_device(device)
    model.reset_state()
    model.eval()
    losses: list[float] = []
    for batch in _batches(val_data):
        batch.to(device=device)
        result = model(batch, inference=True, validation=True)
        losses.extend(result["loss"].detach().reshape(-1).float().cpu().tolist())
        batch.to("cpu")
        if device.type == "cuda":
            torch.cuda.empty_cache()
    if not losses:
        raise ValueError("Validation split produced no detector losses")
    return float(np.mean(losses))


def train_and_select(cfg: Any) -> tuple[Any, dict[str, Any], Any, Any, Any, int]:
    set_seed(cfg, seed=cfg.training.seed)
    device = get_device(cfg)
    train_data, val_data, test_data, max_node_num = get_preprocessed_graphs(cfg)
    if not train_data or not train_data[0]:
        raise ValueError("Training split is empty")
    model = build_model(
        data_sample=train_data[0][0],
        device=device,
        cfg=cfg,
        max_node_num=max_node_num,
    )
    optimizer = optimizer_factory(cfg, parameters=set(model.parameters()))
    grad_accumulation = int(cfg.training.grad_accumulation)
    if grad_accumulation < 1:
        raise ValueError("training.grad_accumulation must be >= 1")

    history: list[dict[str, Any]] = []
    best_epoch: int | None = None
    best_val_loss = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    patience_counter = 0
    started = time.perf_counter()
    epoch_root = Path(cfg.training._trained_models_dir) / "epochs"

    for epoch in range(int(cfg.training.num_epochs)):
        model.reset_state()
        model.train()
        optimizer.zero_grad()
        accumulated: torch.Tensor | None = None
        accumulated_count = 0
        batch_losses: list[float] = []

        for batch in _batches(train_data):
            batch.to(device=device)
            result = model(batch)
            loss = result["loss"].mean()
            batch_losses.append(float(loss.detach().cpu().item()))
            accumulated = loss if accumulated is None else accumulated + loss
            accumulated_count += 1
            if accumulated_count == grad_accumulation:
                accumulated.backward()
                optimizer.step()
                optimizer.zero_grad()
                accumulated = None
                accumulated_count = 0
            batch.to("cpu")
            if device.type == "cuda":
                torch.cuda.empty_cache()

        if accumulated is not None:
            accumulated.backward()
            optimizer.step()
            optimizer.zero_grad()
        if not batch_losses:
            raise ValueError("Training split produced no batches")

        val_loss = validation_loss(cfg, model, val_data)
        train_loss = float(np.mean(batch_losses))
        selected = val_loss < best_val_loss
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "selected_at_epoch": selected,
            }
        )
        model.reset_state()
        save_model(model, str(epoch_root / f"epoch_{epoch:03d}"), cfg)

        if selected:
            best_val_loss = val_loss
            best_epoch = epoch
            best_state = _state_dict_to_cpu(model)
            patience_counter = 0
        else:
            patience_counter += 1
        if patience_counter >= int(cfg.training.patience):
            break

    if best_state is None or best_epoch is None:
        raise RuntimeError("No validation-selected checkpoint was produced")
    model.load_state_dict(best_state)
    model.to_device(device)
    model.reset_state()
    final_model_dir = Path(cfg.training._trained_models_dir) / "final"
    save_model(model, str(final_model_dir), cfg)

    training_summary = {
        "selection": {
            "metric": "validation_loss",
            "mode": "min",
            "selected_epoch": best_epoch,
            "selected_value": best_val_loss,
            "weights_updated_from": "train",
            "validation_updates_weights": False,
        },
        "history": history,
        "epochs_completed": len(history),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "final_model_dir": str(final_model_dir),
    }
    return model, training_summary, train_data, val_data, test_data, max_node_num
