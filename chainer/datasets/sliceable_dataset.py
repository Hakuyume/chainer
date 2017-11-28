import chainer


def _as_tuple(t):
    if isinstance(t, tuple):
        return tuple(t), True
    else:
        return (t,), False


class SliceableBaseDataset(chainer.dataset.DatasetMixin):

    def __len__(self):
        raise NotImplementedError

    def _get_example(self, i, keys):
        raise NotImplementedError

    def get_example(self, i):
        return self._get_example(i, self.keys)

    def slice(self, index=None, keys=None):
        return SlicedDataset(self, index, keys)


class SlicedDataset(SliceableBaseDataset):

    def __init__(self, base, index, keys):
        if index is None:
            index = slice(None)
        elif not isinstance(index, slice):
            index = slice(index, index + 1)
        self._base = base
        self._index = index
        self.keys = keys

    def __len__(self):
        start, end, step = self._index.indices(len(self._base))
        return (end - start) // step

    def _get_example(self, i, keys):
        start, _, step = self._index.indices(len(self._base))
        return self._base._get_example(start + i * step, keys)


class SliceableDataset(SliceableBaseDataset):

    def __init__(self):
        self._getters = dict()

    def __len__(self):
        raise NotImplementedError

    def add_getter(self, keys, getter):
        keys, _ = _as_tuple(keys)
        for i, key in enumerate(keys):
            self._getters[key] = (getter, i)

    def _get_example(self, i, keys):
        keys, is_tuple = _as_tuple(keys)

        example = list()
        cache = dict()
        for key in keys:
            getter, index = self._getters[key]
            if getter not in cache:
                cache[getter], _ = _as_tuple(getter(i))
            example.append(cache[getter][index])

        if is_tuple:
            return tuple(example)
        else:
            return example[0]
