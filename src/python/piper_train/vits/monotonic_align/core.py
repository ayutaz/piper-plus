"""Pure Python/Numba replacement for Cython monotonic_align core."""
import numba
import numpy as np


@numba.jit(nopython=True, cache=True)
def _maximum_path_each(path, value, t_y, t_x):
    max_neg_val = -1e9
    index = t_x - 1

    for y in range(t_y):
        for x in range(max(0, t_x + y - t_y), min(t_x, y + 1)):
            if x == y:
                v_cur = max_neg_val
            else:
                v_cur = value[y - 1, x]
            if x == 0:
                if y == 0:
                    v_prev = 0.0
                else:
                    v_prev = max_neg_val
            else:
                v_prev = value[y - 1, x - 1]
            value[y, x] += max(v_prev, v_cur)

    for y in range(t_y - 1, -1, -1):
        path[y, index] = 1
        if index != 0 and (index == y or value[y - 1, index] < value[y - 1, index - 1]):
            index = index - 1


def maximum_path_c(paths, values, t_ys, t_xs):
    """Drop-in replacement for the Cython maximum_path_c."""
    for i in range(paths.shape[0]):
        _maximum_path_each(paths[i], values[i], t_ys[i], t_xs[i])
