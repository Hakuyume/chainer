import chainer


def _as_tuple(t):
    if isinstance(t, tuple):
        return tuple(t), True
    else:
        return (t,), False


class BaseDataset(chainer.dataset.DatasetMixin):

    def __len__(self):
        raise NotImplementedError

    def get_example_by_keys(self, i, keys):
        raise NotImplementedError

    def get_example(self, i):
        return self.get_example_by_keys(i, self.keys)

    def slice(self, keys):
        return SlicedDataset(self, keys)

    def sub(self, start, stop=None, step=None):
        return SubDataset(self, slice(start, stop, step))


class SlicedDataset(BaseDataset):

    def __init__(self, base, keys):
        self._base = base
        self.keys = keys

    def __len__(self):
        return len(self._base)

    def get_example_by_keys(self, i, keys):
        return self._base.get_example_by_keys(i, keys)


class SubDataset(BaseDataset):

    def __init__(self, base, index):
        self._base = base
        self._index = index
        self.keys = base.keys

    def __len__(self):
        start, end, step = self._index.indices(len(self._base))
        return len(range(start, end, step))

    def get_example_by_keys(self, i, keys):
        start, _, step = self._index.indices(len(self._base))
        return self._base.get_example_by_keys(start + i * step, keys)


class SliceableDataset(BaseDataset):

    def __init__(self):
        self._getters = dict()

    def __len__(self):
        raise NotImplementedError

    def add_getter(self, keys, getter):
        keys, _ = _as_tuple(keys)
        for i, key in enumerate(keys):
            self._getters[key] = (getter, i)

    def get_example_by_keys(self, i, keys):
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
