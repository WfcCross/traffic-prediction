from typing import Tuple, List

import torch
from torch import nn, Tensor

from networks.dcrnn import DCRNN
from networks.fc_lstm import FCLSTM
from networks.graph_wavenet import GWNet
from networks.ours import Ours
from networks.st_metanet import STMetaNet
from networks.stgcn import STGCN
from utils import load_graph_data, sparse_scipy2torch
from utils.stmetanet import get_geo_feature


class Trainer:
    def __init__(self, model: nn.Module, loss):
        self.model = model
        self.loss = loss

    def train(self, inputs: Tensor, targets: Tensor, phase: str) -> Tuple[Tensor, Tensor]:
        raise ValueError('Not implemented.')


def create_model(name: str, dataset: str, loss, config: dict, device) -> Tuple[nn.Module, Trainer]:
    if name == 'STGCN':
        model = STGCN(**config)
        return model, STGCNTrainer(model, loss)
    elif name == 'DCRNN':
        model = DCRNN(**config)
        supports = [sparse_scipy2torch(graph).to(device) for graph in load_graph_data(dataset, 'scalap')]
        return model, DCRNNTrainer(model, loss, supports)
    elif name == 'FCLSTM':
        model = FCLSTM(**config)
        return model, FCLSTMTrainer(model, loss)
    elif name == 'STMETANET':
        n_neighbors = config.pop('n_neighbors')
        features, graph = get_geo_feature(n_neighbors)
        model = STMetaNet(graph, **config)
        return model, STMETANETTrainer(model, loss, features)
    elif name == 'GWNET':
        adjtype, randomadj = config.pop('adjtype'), config.pop('randomadj')
        supports = [torch.tensor(graph.todense(), dtype=torch.float32, device=device) for graph in
                    load_graph_data(dataset, adjtype)]
        aptinit = None if randomadj else supports[0]
        model = GWNet(device, supports=supports, aptinit=aptinit, **config)
        return model, GWNetTrainer(model, loss)
    elif name == 'Ours':
        model = Ours(**config)
        return model, OursTrainer(model, loss)
    else:
        raise ValueError(f'{name} is not implemented.')


class STGCNTrainer(Trainer):
    pass


class DCRNNTrainer(Trainer):
    def __init__(self, model: DCRNN, loss, graphs: List[Tensor]):
        super(DCRNNTrainer, self).__init__(model, loss)
        for graph in graphs:
            graph.requires_grad_(False)
        self.graphs = graphs
        self.train_batch_seen: int = 0

    def train(self, inputs: Tensor, targets: Tensor, phase: str):
        if phase == 'train':
            self.train_batch_seen += 1
        i_targets = targets if phase == 'train' else None
        outputs = self.model(inputs, self.graphs, i_targets, self.train_batch_seen)
        loss = self.loss(outputs, targets)
        return outputs, loss


class FCLSTMTrainer(Trainer):
    def train(self, inputs: Tensor, targets: Tensor, phase: str) -> Tuple[Tensor, Tensor]:
        if phase == 'train':
            outputs = self.model(inputs, targets)
        else:
            outputs = self.model(inputs)
        loss = self.loss(outputs, targets)
        return outputs, loss


class OursTrainer(Trainer):
    def train(self, inputs: Tensor, targets: Tensor, phase: str) -> Tuple[Tensor, Tensor]:
        if phase == 'train':
            outputs, supports = self.model(inputs, targets)
        else:
            outputs, supports = self.model(inputs)
        loss = self.loss(outputs, targets)  # - 100 * distributions.Categorical(probs=supports).entropy().mean()
        return outputs, loss


class STMETANETTrainer(Trainer):
    def __init__(self, model: DCRNN, loss, features: Tensor):
        super(STMETANETTrainer, self).__init__(model, loss)
        self.features = features
        self.train_batch_seen: int = 0

    def train(self, inputs: Tensor, targets: Tensor, phase: str) -> Tuple[Tensor, Tensor]:
        if phase == 'train':
            self.train_batch_seen += 1
        i_targets = targets if phase == 'train' else None
        outputs = self.model(torch.tensor(self.features, device=inputs.device, dtype=inputs.dtype),
                             inputs, i_targets, self.train_batch_seen)
        loss = self.loss(outputs, targets)
        return outputs, loss


class GWNetTrainer(Trainer):
    def train(self, inputs: Tensor, targets: Tensor, phase: str) -> Tuple[Tensor, Tensor]:
        outputs = self.model(inputs.transpose(1, 3))
        loss = self.loss(outputs, targets)
        return outputs, loss
