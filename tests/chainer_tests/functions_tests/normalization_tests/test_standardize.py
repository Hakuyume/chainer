import functools
import unittest

import numpy

from chainer.functions.normalization._standardize import _standardize
from chainer import testing


def _skip_if(cond, reason):
    """Skip test if cond(self) is True"""
    def decorator(impl):
        @functools.wraps(impl)
        def wrapper(self, *args, **kwargs):
            if cond(self):
                raise unittest.SkipTest(reason)
            else:
                impl(self, *args, **kwargs)
        return wrapper
    return decorator


@testing.parameterize(*testing.product([
    [
        {'ch_out': 1},
        {'ch_out': 5},
    ],
    [
        {'size': 10},
        {'size': 20},
    ],
    [
        {'dtype': numpy.float32},
        {'dtype': numpy.float16},
    ],
    [
        # same (str): flag whether input elems are same values.
        #   'no'   : all elems are randamly-chosen,
        #   'equal': all elems are equal,
        #   'near' : all elems are (randomly-chosen small values
        #            + same value).
        {'eps': 1e-5, 'same': 'no'},
        {'eps': 1e-1, 'same': 'no'},
        {'eps': 1e-1, 'same': 'equal'},
        {'eps': 1e-1, 'same': 'near'},
    ],
]))
@testing.backend.inject_backend_tests(
    None,
    # CPU tests
    testing.product({
        'use_cuda': [False],
        'use_ideep': ['never', 'always'],
    })
    # GPU tests
    + testing.product({
        'use_cuda': [True],
        'use_cudnn': ['never', 'always'],
    })
    # ChainerX tests
    + testing.product({
        'use_chainerx': [True],
        'chainerx_device': ['native:0', 'cuda:0'],
    })
)
class TestStandardize(testing.FunctionTestCase):

    def setUp(self):
        self.skip_double_backward_test = self.same in ('equal', 'near')
        if self.dtype == numpy.float16:
            self.check_forward_options.update({'atol': 5e-3, 'rtol': 1e-2})
            self.check_backward_options.update(
                {'atol': 5e-3, 'rtol': 1e-2, 'eps': self.eps})
            self.check_double_backward_options.update(
                {'atol': 5e-3, 'rtol': 1e-2, 'eps': self.eps})

    def generate_inputs(self):
        shape = self.ch_out, self.size
        if self.same in ('equal', 'near'):
            # Make self.x have same values
            x = numpy.ones(shape, self.dtype)
            x *= numpy.random.uniform(-1, 1)
            if self.same == 'near':
                # Make self.x have slightly different values
                zero_scale = 10. ** numpy.random.randint(-40, -3)
                x += numpy.random.uniform(-zero_scale, zero_scale, shape)
        else:
            x = numpy.random.uniform(-1, 1, shape).astype(self.dtype)
        return x,

    def forward(self, inputs, device):
        x, = inputs
        return _standardize(x, self.eps),

    def forward_expected(self, inputs):
        x, = inputs
        mu = numpy.mean(x, axis=1, keepdims=True)
        x_mu = x - mu
        var = numpy.mean(numpy.square(x_mu), axis=1, keepdims=True)
        std = numpy.sqrt(var, dtype=x.dtype) + self.eps
        inv_std = numpy.reciprocal(std)
        return x_mu * inv_std,


testing.run_module(__name__, __file__)
