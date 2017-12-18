import functools
import itertools
import operator

import pytest

import xchainer


def create_dummy_data(shape, dtype):
    size = functools.reduce(operator.mul, shape, 1)
    if dtype == xchainer.Dtype.bool:
        return [i % 2 == 1 for i in range(size)]
    else:
        return [i for i in range(size)]


@pytest.mark.parametrize('shape,dtype', itertools.product([
    (),
    (0,),
    (1,),
    (1, 1, 1),
    (2, 3),
    (2, 0, 3),
], [
    xchainer.Dtype.bool,
    xchainer.Dtype.int8,
    xchainer.Dtype.int16,
    xchainer.Dtype.int32,
    xchainer.Dtype.int64,
    xchainer.Dtype.uint8,
    xchainer.Dtype.float32,
    xchainer.Dtype.float64,
]))
def test_array(shape, dtype):
    data_list = create_dummy_data(shape, dtype)
    array = xchainer.Array(shape, dtype, data_list)

    assert isinstance(array.shape, xchainer.Shape)
    assert array.shape == shape
    assert array.dtype == dtype
    assert array.offset == 0
    assert array.is_contiguous

    expected_total_size = functools.reduce(operator.mul, shape, 1)
    assert array.total_size == expected_total_size
    assert array.element_bytes == dtype.itemsize
    assert array.total_bytes == dtype.itemsize * expected_total_size

    assert array.debug_flat_data == data_list
