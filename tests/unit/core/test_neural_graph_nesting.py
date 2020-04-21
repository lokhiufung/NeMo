# ! /usr/bin/python
# -*- coding: utf-8 -*-

# =============================================================================
# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

import pytest
import torch

from nemo.backends.pytorch.actions import PtActions
from nemo.backends.pytorch.tutorials import MSELoss, RealFunctionDataLayer, TaylorNet
from nemo.core import EvaluatorCallback, NeuralGraph, OperationMode, SimpleLossLoggerCallback
from nemo.core.neural_types import NeuralTypeComparisonResult
from nemo.utils import logging


@pytest.mark.usefixtures("neural_factory")
class TestNeuralGraphNesting:
    @pytest.mark.unit
    def test_module_nesting_change_operation_modes(self):
        """ 
            Tests whether invalid nesting (i.e. nesting of graphs with incompatible modes) throw exeptions.
        """
        # Instantiate the necessary neural modules.
        dl = RealFunctionDataLayer(n=100, batch_size=4)

        with NeuralGraph(operation_mode=OperationMode.both):
            _, _ = dl()
            assert dl.operation_mode == OperationMode.both

        with NeuralGraph(operation_mode=OperationMode.training):
            _, _ = dl()
            assert dl.operation_mode == OperationMode.training

        with NeuralGraph(operation_mode=OperationMode.inference):
            _, _ = dl()
            assert dl.operation_mode == OperationMode.inference

    @pytest.mark.unit
    def test_graph_nesting_possible_operation_modes(self):
        """ 
            Tests whether invalid nesting (i.e. nesting of graphs with incompatible modes) throw exeptions.
        """
        # Instantiate the necessary neural modules.
        dl = RealFunctionDataLayer(n=100, batch_size=4)

        with NeuralGraph(operation_mode=OperationMode.both) as both:
            _, _ = dl()

        with NeuralGraph(operation_mode=OperationMode.training) as training:
            _, _ = dl()

        with NeuralGraph(operation_mode=OperationMode.inference) as inference:
            _, _ = dl()

        # Allowed operations.
        # Can nest 'both' into 'training'.
        with NeuralGraph(operation_mode=OperationMode.training):
            _, _ = both()

        # Can nest 'both' into 'inference'.
        with NeuralGraph(operation_mode=OperationMode.inference):
            _, _ = both()

        # Can nest 'training' into 'training'.
        with NeuralGraph(operation_mode=OperationMode.training):
            _, _ = training()

        # Can nest 'inference' into 'inference'.
        with NeuralGraph(operation_mode=OperationMode.inference):
            _, _ = inference()

        # Can nest 'both' into 'both'.
        with NeuralGraph(operation_mode=OperationMode.both):
            _, _ = both()

        # Operations not allowed.
        # Cannot nest 'inference' into 'training'.
        with pytest.raises(TypeError):
            with NeuralGraph(operation_mode=OperationMode.training):
                _, _ = inference()

        # Cannot nest 'training' into 'inference'.
        with pytest.raises(TypeError):
            with NeuralGraph(operation_mode=OperationMode.inference):
                _, _ = training()

        # Cannot nest 'training' into 'both'.
        with pytest.raises(TypeError):
            with NeuralGraph(operation_mode=OperationMode.both):
                _, _ = training()

        # Cannot nest 'inference' into 'both'.
        with pytest.raises(TypeError):
            with NeuralGraph(operation_mode=OperationMode.both):
                _, _ = inference()

    @pytest.mark.unit
    def test_output_ports_binding(self):
        # Create modules.
        data_source = RealFunctionDataLayer(n=100, batch_size=1, name="tgn_ds")
        tn = TaylorNet(dim=4, name="tgn_tn")
        loss = MSELoss(name="tgn_loss")

        # Test default binding.
        with NeuralGraph(operation_mode=OperationMode.training) as g1:
            # Create the graph by connnecting the modules.
            x, y = data_source()
            y_pred = tn(x=x)
            lss = loss(predictions=y_pred, target=y)

        assert len(g1.outputs) == 4
        assert g1.output_tensors["x"].compare(data_source.output_ports["x"]) == NeuralTypeComparisonResult.SAME
        assert g1.output_tensors["y"].compare(data_source.output_ports["y"]) == NeuralTypeComparisonResult.SAME
        assert g1.output_tensors["y_pred"].compare(tn.output_ports["y_pred"]) == NeuralTypeComparisonResult.SAME
        assert g1.output_tensors["loss"].compare(loss.output_ports["loss"]) == NeuralTypeComparisonResult.SAME

        # Test manual binding.
        with g1:
            g1.outputs["my_prediction"] = y_pred
            g1.outputs["my_loss"] = lss

        assert len(g1.outputs) == 2
        assert (
            g1.output_tensors["my_prediction"].compare(tn.output_ports["y_pred"])
            == NeuralTypeComparisonResult.SAME
        )
        assert g1.output_tensors["my_loss"].compare(loss.output_ports["loss"]) == NeuralTypeComparisonResult.SAME

    @pytest.mark.unit
    def test_graph_nesting_topology_copy_one_module_defaults(self):
        """ Test whether when nesting one graph into another the graph topology (tensors) will be copied. """

        dl = RealFunctionDataLayer(n=100, batch_size=32, name="t1_dl")

        with NeuralGraph(operation_mode=OperationMode.training, name="t1_g1") as g1:
            xg1, tg1 = dl()

        with NeuralGraph(operation_mode=OperationMode.training, name="t1_g2") as g2:
            xg2, tg2 = g1()
        # import pdb;pdb.set_trace()
        # We expect that both graphs will have the same modes/steps.
        assert len(g1.steps) == len(g2.steps)
        assert g1.steps[0] == g2.steps[0]
        assert len(g1) == len(g2)
        assert g1["t1_dl"] is g2["t1_dl"]