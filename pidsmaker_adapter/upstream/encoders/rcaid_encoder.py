"""R-Caid system GAT encoder with residual MLP aggregation.

R-Caid-specific encoder combining multi-layer GAT with MLP-based aggregation
for root cause analysis and attack investigation in provenance graphs.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint
from torch_geometric.nn import GATConv
from torch_geometric.utils import add_self_loops, remove_self_loops, softmax


def _memory_efficient_gat(conv, x, edge_index, chunk_size=65_536):
    """Exact GATConv aggregation without materializing every edge message."""
    if conv.lin is None:
        raise ValueError("R-CAID requires homogeneous GATConv projections")
    heads, channels = conv.heads, conv.out_channels
    projected = conv.lin(x).view(-1, heads, channels)
    alpha_src = (projected * conv.att_src).sum(dim=-1)
    alpha_dst = (projected * conv.att_dst).sum(dim=-1)

    if conv.add_self_loops:
        edge_index, _ = remove_self_loops(edge_index)
        edge_index, _ = add_self_loops(edge_index, num_nodes=projected.size(0))
    src, dst = edge_index
    alpha = F.leaky_relu(alpha_src[src] + alpha_dst[dst], conv.negative_slope)
    alpha = softmax(alpha, dst, num_nodes=projected.size(0))
    alpha = F.dropout(alpha, p=conv.dropout, training=conv.training)

    output_shape = (projected.size(0), heads, channels)
    out = projected.new_zeros(output_shape)

    def aggregate_chunk(projected_nodes, attention, chunk_src, chunk_dst):
        chunk_out = projected_nodes.new_zeros(output_shape)
        messages = attention.unsqueeze(-1) * projected_nodes[chunk_src]
        return chunk_out.index_add(0, chunk_dst, messages)

    for start in range(0, src.numel(), chunk_size):
        end = min(start + chunk_size, src.numel())
        args = (projected, alpha[start:end], src[start:end], dst[start:end])
        if torch.is_grad_enabled():
            out = out + checkpoint(aggregate_chunk, *args, use_reentrant=False)
        else:
            out = out + aggregate_chunk(*args)
    out = out.view(-1, heads * channels) if conv.concat else out.mean(dim=1)
    return out if conv.bias is None else out + conv.bias


def _apply_gat(conv, x, edge_index):
    if edge_index.shape[1] > 262_144:
        return _memory_efficient_gat(conv, x, edge_index)
    return conv(x, edge_index)


class _RcaidMLP(nn.Module):
    """Internal MLP for R-Caid aggregation."""

    def __init__(self, input_dim, output_dim):
        super(_RcaidMLP, self).__init__()
        self.fc1 = nn.Linear(input_dim, output_dim)
        self.fc2 = nn.Linear(output_dim, output_dim)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x


class RCaidGAT(nn.Module):
    """R-Caid GAT encoder with 3-layer attention and MLP aggregation.

    Combines three GAT layers with an MLP that aggregates intermediate and final
    representations for improved node embeddings in causal analysis tasks.
    """

    def __init__(self, in_dim, hid_dim, out_dim, dropout, num_heads=4):
        super(RCaidGAT, self).__init__()
        self.gat1 = GATConv(in_dim, hid_dim, heads=num_heads, concat=True)
        self.gat2 = GATConv(hid_dim * num_heads, hid_dim, heads=num_heads, concat=True)
        self.gat3 = GATConv(
            hid_dim * num_heads, out_dim, heads=1, concat=False
        )  # Output is not concatenated
        self.mlp = _RcaidMLP(hid_dim * num_heads + out_dim, out_dim)  # Input is concatenated
        self.dropout1 = nn.Dropout(dropout)

    def forward(self, x, edge_index, **kwargs):
        x1 = _apply_gat(self.gat1, x, edge_index)
        x1 = F.relu(x1)
        # GAT Layer 2 with attention
        x2 = _apply_gat(self.gat2, x1, edge_index)
        x2 = F.relu(x2)
        # Aggregation through attention in the third layer
        x3 = _apply_gat(self.gat3, x2, edge_index)

        x3 = self.dropout1(x3)
        # Update through MLP (concatenate previous layer's output with the current output)
        mlp_input = torch.cat([x2, x3], dim=-1)

        out = self.mlp(mlp_input)

        return {"h": out}
