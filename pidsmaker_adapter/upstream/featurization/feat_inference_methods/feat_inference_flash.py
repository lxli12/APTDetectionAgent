import math
import os
from collections import defaultdict

import numpy as np
import torch
from gensim.models import Word2Vec

from pidsmaker_adapter.upstream.utils.utils import (
    get_indexid2msg,
    log_start,
    tokenize_arbitrary_label,
)


def infer(document, w2vmodel, encoder):
    """
    Each node is associated to a `document` which is the list of (msg => edge type => msg)
    involving this node.
    We get the embedding of each word inside this document and we do the mean of all embeddings.
    OOV words are simply ignored.
    """
    word_embeddings = [w2vmodel.wv[word] for word in document if word in w2vmodel.wv]

    embedding_dim = w2vmodel.vector_size

    if not word_embeddings:
        return np.zeros(embedding_dim)

    word_embeddings_array = np.array(word_embeddings)

    output_embedding = torch.tensor(word_embeddings_array, dtype=torch.float)
    if len(document) < 100000:
        output_embedding = encoder.embed(output_embedding)

    output_embedding = output_embedding.detach().cpu().numpy()
    return np.mean(output_embedding, axis=0)


class PositionalEncoder:
    def __init__(self, d_model, max_len=100000):
        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        self.pe = torch.zeros(max_len, d_model)
        self.pe[:, 0::2] = torch.sin(position * div_term)
        self.pe[:, 1::2] = torch.cos(position * div_term)

    def embed(self, x):
        return x + self.pe[: x.size(0)]


def load_components(cfg):
    trained_w2v_dir = cfg.featurization._model_dir
    model = Word2Vec.load(os.path.join(trained_w2v_dir, "word2vec_model_final.model"))
    encoder = PositionalEncoder(cfg.featurization.emb_dim)
    return model, encoder


def infer_graph(graph_path, cfg, components=None):
    """Infer node embeddings from one construction graph only.

    The upstream implementation merged a node's context across train, validation,
    and test before embedding it. That leaks future windows into earlier online
    observations. The adapter instead derives every node document from the current
    15-minute graph while keeping the Word2Vec model frozen after train.
    """
    w2vmodel, encoder = components or load_components(cfg)
    graph = torch.load(graph_path)
    indexid2msg = get_indexid2msg(cfg)
    nodes = defaultdict(list)
    sorted_edges = sorted(
        (
            (u, v, attr["label"], int(attr["time"]))
            for u, v, _, attr in graph.edges(data=True, keys=True)
        ),
        key=lambda item: item[3],
    )
    for src, dst, operation, _ in sorted_edges:
        _, src_msg = indexid2msg[src]
        _, dst_msg = indexid2msg[dst]
        properties = (src_msg, operation, dst_msg)
        if len(nodes[src]) < 300:
            nodes[src].extend(properties)
        if len(nodes[dst]) < 300:
            nodes[dst].extend(properties)

    token_cache = {}
    indexid2vec = {}
    for node_id, properties in nodes.items():
        document = []
        for sentence in properties:
            if sentence not in token_cache:
                token_cache[sentence] = tokenize_arbitrary_label(sentence)
            document.extend(token_cache[sentence])
        indexid2vec[node_id] = infer(document, w2vmodel, encoder)
    return indexid2vec


def main(cfg):
    log_start(__file__)
    raise RuntimeError(
        "FLASH embeddings are graph-local; call infer_graph for each 15-minute graph"
    )
