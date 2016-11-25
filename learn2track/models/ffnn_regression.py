from os.path import join as pjoin

import numpy as np
import smartlearner.initializers as initer
import theano
import theano.tensor as T
from learn2track.models import FFNN
from learn2track.models.layers import LayerRegression
from smartlearner.interfaces.loss import Loss

from learn2track.utils import l2distance

floatX = theano.config.floatX


class FFNN_Regression(FFNN):
    """ A standard FFNN model with a regression layer stacked on top of it.
    """

    def __init__(self, volume_manager, input_size, hidden_sizes, output_size, activation, **_):
        """
        Parameters
        ----------
        volume_manager : :class:`VolumeManger` object
            Use to evaluate the diffusion signal at specific coordinates.
        input_size : int
            Number of units each element X has.
        hidden_sizes : int, list of int
            Number of hidden units each FFNN layer should have.
        output_size : int
            Number of units the regression layer should have.
        activation : str
            Name of the activation function to use in the hidden layers
        """
        super().__init__(input_size, hidden_sizes, activation)
        self.volume_manager = volume_manager
        self.output_size = output_size
        self.layer_regression = LayerRegression(self.hidden_sizes[-1], self.output_size)

    def initialize(self, weights_initializer=initer.UniformInitializer(1234)):
        super().initialize(weights_initializer)
        self.layer_regression.initialize(weights_initializer)

    @property
    def hyperparameters(self):
        hyperparameters = super().hyperparameters
        hyperparameters['output_size'] = self.output_size
        return hyperparameters

    @property
    def parameters(self):
        return super().parameters + self.layer_regression.parameters

    def _fprop(self, Xi, *args):
        # coords : streamlines 3D coordinates.
        # coords.shape : (batch_size, 4) where the last column is a dwi ID.
        # args.shape : n_layers * (batch_size, layer_size)
        coords = Xi

        # Get diffusion data.
        # data_at_coords.shape : (batch_size, input_size)
        data_at_coords = self.volume_manager.eval_at_coords(coords)

        # Hidden state to be passed to the next GRU iteration (next _fprop call)
        # next_hidden_state.shape : n_layers * (batch_size, layer_size)
        layer_outputs = super()._fprop(data_at_coords)

        # Compute the direction to follow for step (t)
        regression_out = self.layer_regression.fprop(layer_outputs[-1])

        return layer_outputs + (regression_out,)

    def make_sequence_generator(self, subject_id=0, **_):
        """ Makes functions that return the prediction for x_{t+1} for every
        sequence in the batch given x_{t}.

        Parameters
        ----------
        subject_id : int, optional
            ID of the subject from which its diffusion data will be used. Default: 0.
        """

        # Build the sequence generator as a theano function.
        symb_x_t = T.matrix(name="x_t")

        layer_outputs = self._fprop(symb_x_t)

        # predictions.shape : (batch_size, target_size)
        predictions = layer_outputs[-1]

        f = theano.function(inputs=[symb_x_t], outputs=[predictions])

        def _gen(x_t, states):
            """ Returns the prediction for x_{t+1} for every
                sequence in the batch given x_{t}.

            Parameters
            ----------
            x_t : ndarray with shape (batch_size, 3)
                Streamline coordinate (x, y, z).
            states : list of 2D array of shape (batch_size, hidden_size)
                Currrent states of the network.

            Returns
            -------
            next_x_t : ndarray with shape (batch_size, 3)
                Directions to follow.
            new_states : list of 2D array of shape (batch_size, hidden_size)
                Updated states of the network after seeing x_t.
            """
            # Append the DWI ID of each sequence after the 3D coordinates.
            subject_ids = np.array([subject_id] * len(x_t), dtype=floatX)[:, None]
            x_t = np.c_[x_t, subject_ids]

            results = f(x_t)
            next_x_t = results[-1]

            # FFNN_Regression is not a recurrent network, return original states
            new_states = states

            return next_x_t, new_states

        return _gen


class L2Distance(Loss):
    """ Computes the L2 error of the output.

    Notes
    -----
    This loss assumes the regression target is a vector.
    """
    def __init__(self, model, dataset, normalize_output=False, eps=1e-6):
        super().__init__(model, dataset)
        self.normalize_output = normalize_output
        self.eps = eps

    def _get_updates(self):
        return {}  # There is no updates for L2Distance.

    def _compute_losses(self, model_output):
        # regression_outputs.shape = (batch_size, out_dim)
        regression_outputs = model_output
        if self.normalize_output:
            regression_outputs /= l2distance(regression_outputs, keepdims=True, eps=self.eps)

        self.samples = regression_outputs

        # loss_per_time_step.shape = (batch_size,)
        self.loss_per_time_step = l2distance(self.samples, self.dataset.symb_targets)

        return self.loss_per_time_step