import chainer
import numpy
import pytest

import chainerx
import chainerx.testing

from chainerx_tests import array_utils
from chainerx_tests import dtype_utils
from chainerx_tests import op_utils


_expected_numeric_dtypes_comparison = [
    (t1, t2)
    for (t1, t2), _ in dtype_utils.result_dtypes_two_arrays
    if all([numpy.dtype(t) != 'bool_' for t in (t1, t2)])
]


_expected_float_dtypes_comparison = [
    (t1, t2)
    for (t1, t2), _ in dtype_utils.result_dtypes_two_arrays
    if all([numpy.dtype(t).kind == 'f' for t in (t1, t2)])
]


_expected_all_dtypes_comparison = _expected_numeric_dtypes_comparison + [
    ('bool_', 'bool_'),
]


@op_utils.op_test(['native:0', 'cuda:0'])
@chainer.testing.parameterize(*(
    # All dtypes
    chainer.testing.product({
        'dtypes': _expected_all_dtypes_comparison,
        'inputs': [
            ([], []),
            ([True], [True]),
            ([True], [False]),
        ]
    })
    # Numeric dtypes
    + chainer.testing.product({
        'dtypes': _expected_numeric_dtypes_comparison,
        'inputs': [
            ([0], [0]),
            ([0], [-0]),
            ([0], [1]),
            ([0, 1, 2], [0, 1, 2]),
            ([1, 1, 2], [0, 1, 2]),
            ([0, 1, 2], [1, 2, 3]),
            ([[0, 1], [2, 3]], [[0, 1], [2, 3]]),
            ([[0, 1], [2, 3]], [[0, 1], [2, -2]]),
            ([[0, 1], [2, 3]], [[1, 2], [3, 4]]),
            (0, [0]),
            (1, [0]),
            ([], [0]),
            ([0], [[0, 1, 2], [3, 4, 5]]),
            ([[0], [1]], [0, 1, 2]),
            ([0.2], [0.2]),
            ([0.2], [-0.3]),
        ],
    })
    # Float dtypes
    + chainer.testing.product({
        'dtypes': _expected_float_dtypes_comparison,
        'inputs': [
            ([0., numpy.nan], [0., 1.]),
            ([0., numpy.nan], [0., numpy.nan]),
            ([0., numpy.inf], [0., 1.]),
            ([0., -numpy.inf], [0., 1.]),
            ([numpy.inf, 1.], [numpy.inf, 1.]),
            ([-numpy.inf, 1.], [-numpy.inf, 1.]),
            ([numpy.inf, 1.], [-numpy.inf, 1.]),
            ([numpy.inf, 1.], [-numpy.inf, numpy.nan]),
        ]
    })
))
@chainer.testing.parameterize_pytest('cmp_op,module_func', [
    (lambda a, b: a == b, 'equal'),
    (lambda a, b: a != b, 'not_equal'),
    (lambda a, b: a > b, 'greater'),
    (lambda a, b: a >= b, 'greater_equal'),
    (lambda a, b: a < b, 'less'),
    (lambda a, b: a <= b, 'less_equal'),
])
# Ignore warnings from numpy for NaN comparisons.
@pytest.mark.filterwarnings('ignore:invalid value encountered in ')
class TestCmp(op_utils.NumpyOpTest):

    skip_backward_test = True
    skip_double_backward_test = True

    def generate_inputs(self):
        a_object, b_object = self.inputs
        a_dtype, b_dtype = self.dtypes
        a = numpy.array(a_object, a_dtype)
        b = numpy.array(b_object, b_dtype)
        return a, b

    def forward_xp(self, inputs, xp):
        a, b = inputs
        cmp_op = self.cmp_op
        module_func = getattr(xp, self.module_func)

        y1 = cmp_op(a, b)
        y2 = cmp_op(b, a)
        y3 = module_func(a, b)
        y4 = module_func(b, a)
        return y1, y2, y3, y4


@pytest.mark.parametrize('a_shape,b_shape', [
    ((2,), (3,)),
    ((2,), (2, 3)),
    ((1, 2, 3), (1, 2, 3, 4)),
])
@pytest.mark.parametrize('cmp_op, chx_cmp', [
    (lambda a, b: a == b, chainerx.equal),
    (lambda a, b: a != b, chainerx.not_equal),
    (lambda a, b: a > b, chainerx.greater),
    (lambda a, b: a >= b, chainerx.greater_equal),
    (lambda a, b: a < b, chainerx.less),
    (lambda a, b: a < b, chainerx.less_equal),
])
def test_cmp_invalid_shapes(cmp_op, chx_cmp, a_shape, b_shape):
    def check(x, y):
        with pytest.raises(chainerx.DimensionError):
            cmp_op(x, y)

        with pytest.raises(chainerx.DimensionError):
            chx_cmp(x, y)

    a = array_utils.create_dummy_ndarray(chainerx, a_shape, 'float32')
    b = array_utils.create_dummy_ndarray(chainerx, b_shape, 'float32')
    check(a, b)
    check(b, a)


@pytest.mark.parametrize('cmp_op, chx_cmp', [
    (lambda a, b: a == b, chainerx.equal),
    (lambda a, b: a != b, chainerx.not_equal),
    (lambda a, b: a > b, chainerx.greater),
    (lambda a, b: a >= b, chainerx.greater_equal),
    (lambda a, b: a < b, chainerx.less),
    (lambda a, b: a < b, chainerx.less_equal),
])
def test_cmp_invalid_dtypes(cmp_op, chx_cmp, numeric_dtype):
    def check(x, y):
        with pytest.raises(chainerx.DtypeError):
            cmp_op(x, y)

        with pytest.raises(chainerx.DtypeError):
            chx_cmp(x, y)

    a = array_utils.create_dummy_ndarray(chainerx, (2, 3), 'bool_')
    b = array_utils.create_dummy_ndarray(chainerx, (2, 3), numeric_dtype)
    check(a, b)
    check(b, a)


@op_utils.op_test(['native:0', 'cuda:0'])
@chainer.testing.parameterize(*(
    # All dtypes
    chainer.testing.product({
        'dtype': chainerx.testing.all_dtypes,
        'input': [
            [],
            [True],
            [False],
        ]
    })
    # Numeric dtypes
    + chainer.testing.product({
        'dtype': chainerx.testing.numeric_dtypes,
        'input': [
            [0],
            [1],
            [0, 1, 2],
            [[0, 1], [2, 0]],
        ],
    })
    # Float dtypes
    + chainer.testing.product({
        'dtype': chainerx.testing.float_dtypes,
        'input': [
            [0.2],
            [-0.3],
            [0., numpy.nan],
            [numpy.nan, numpy.inf],
            [-numpy.inf, numpy.nan],
        ]
    })
))
class TestLogicalNot(op_utils.NumpyOpTest):

    skip_backward_test = True
    skip_double_backward_test = True

    def generate_inputs(self):
        return numpy.array(self.input, self.dtype),

    def forward_xp(self, inputs, xp):
        a, = inputs
        b = xp.logical_not(a)
        return b,


def compute_all(xp, a, axis, keepdims):
    return xp.all(a, axis=axis, keepdims=keepdims)


def compute_any(xp, a, axis, keepdims):
    return xp.any(a, axis=axis, keepdims=keepdims)


@chainerx.testing.numpy_chainerx_array_equal()
@pytest.mark.parametrize('keepdims', [False, True])
@pytest.mark.parametrize('shape,axis', [
    ((), None),
    ((), ()),
    ((2,), None),
    ((2,), ()),
    ((2,), 0),
    ((2,), (0,)),
    ((2,), (-1,)),
    ((2, 3), None),
    ((2, 3), ()),
    ((2, 3), 0),
    ((2, 3), (0,)),
    ((2, 3), (1,)),
    ((2, 3), (-1,)),
    ((2, 3), (-2,)),
    ((2, 3), (0, 1)),
    ((2, 3), (-2, -1)),
    ((1, 3), None),  # Reduce over 1-dim axis
    ((0, 3), None),  # Reduce over 0-dim axis
    # Reduce over axes that are in the middle or apart
    ((2, 3, 4), (1,)),
    ((2, 3, 4), (0, 2)),
    # Reduce over axes that are apart and/or unsorted
    ((2, 3), (1, 0)),
    ((2, 3, 4), (2, 0)),
    ((2, 3, 4), (2, 0, 1)),
    ((2, 3, 4), (-2, 2, 0)),
])
@pytest.mark.parametrize_device(['native:0', 'cuda:0'])
@pytest.mark.parametrize('func',[
    compute_all,
    compute_any
])
def test_logical_reductions(func, xp, device, shape, axis, keepdims, dtype):
    a = array_utils.create_dummy_ndarray(xp, shape, dtype)

    # Hack for #6778
    # TODO(kshitij12345) : Remove when fixed
    if xp is chainerx and a.dtype == 'float16' and 'cuda' in str(a.device):
        a = xp.logical_not(a.astype(bool, copy=True))

    return func(xp, a, axis, keepdims)
        

@chainerx.testing.numpy_chainerx_array_equal(
    accept_error=(chainerx.DimensionError, ValueError))
@pytest.mark.parametrize('keepdims', [False, True])
@pytest.mark.parametrize('shape,axis', [
    ((), 1),
    ((), (1,)),
    ((2,), 2),
    ((2,), (2,)),
    ((2,), (-2,)),
    ((2, 3,), (-3,)),
    ((2, 3,), (-3, -4)),
    ((2, 3,), (0, 0)),
    ((2, 3,), (-1, -1)),
    ((2, 3,), (0, 1, 1)),
    ((2, 3,), (0, -2)),
])
@pytest.mark.parametrize('func',[
    compute_all,
    compute_any
])
def test_logical_reductions_invalid(func, is_module, xp, shape, 
                                     axis, keepdims, dtype):
    a = array_utils.create_dummy_ndarray(xp, shape, dtype)
    func(xp, a, axis, keepdims)
