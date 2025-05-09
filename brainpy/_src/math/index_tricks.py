# -*- coding: utf-8 -*-

import abc

from jax import core
from .compat_numpy import arange, array, concatenate, expand_dims, linspace, meshgrid, stack, transpose
import numpy as np

__all__ = ["c_", "index_exp", "mgrid", "ogrid", "r_", "s_"]


def _make_1d_grid_from_slice(s: slice, op_name: str):
  start = core.concrete_or_error(None, s.start,
                                 f"slice start of jnp.{op_name}") or 0
  stop = core.concrete_or_error(None, s.stop,
                                f"slice stop of jnp.{op_name}")
  step = core.concrete_or_error(None, s.step,
                                f"slice step of jnp.{op_name}") or 1
  if np.iscomplex(step):
    newobj = linspace(start, stop, int(abs(step)))
  else:
    newobj = arange(start, stop, step)

  return newobj


class _IndexGrid(abc.ABC):
  """Creates multi-dimensional grids of indices."""
  sparse: bool
  op_name: str

  def __getitem__(self, key):
    if isinstance(key, slice):
      return _make_1d_grid_from_slice(key, op_name=self.op_name)
    output = (_make_1d_grid_from_slice(k, op_name=self.op_name) for k in key)
    output = meshgrid(*output, indexing='ij', sparse=self.sparse)
    return output if self.sparse else stack(output, 0)


class _Mgrid(_IndexGrid):
  """Return dense multi-dimensional "meshgrid".

  LAX-backend implementation of :obj:`numpy.mgrid`. This is a convenience wrapper for
  functionality provided by :func:`jax.numpy.meshgrid` with ``sparse=False``.

  See Also:
    jnp.ogrid: open/sparse version of jnp.mgrid

  Examples:
    Pass ``[start:stop:step]`` to generate values similar to :func:`jax.numpy.arange`:

    >>> import brainpy.math as bm
    >>> bm.mgrid[0:4:1]
    DeviceArray([0, 1, 2, 3], dtype=int32)

    Passing an imaginary step generates values similar to :func:`jax.numpy.linspace`:

    >>> bm.mgrid[0:1:4j]
    DeviceArray([0.        , 0.33333334, 0.6666667 , 1.        ], dtype=float32)

    Multiple slices can be used to create broadcasted grids of indices:

    >>> bm.mgrid[:2, :3]
    DeviceArray([[[0, 0, 0],
                  [1, 1, 1]],
                 [[0, 1, 2],
                  [0, 1, 2]]], dtype=int32)
  """
  sparse = False
  op_name = "mgrid"


mgrid = _Mgrid()


class _Ogrid(_IndexGrid):
  """Return open multi-dimensional "meshgrid".

  LAX-backend implementation of :obj:`numpy.ogrid`. This is a convenience wrapper for
  functionality provided by :func:`jax.numpy.meshgrid` with ``sparse=True``.

  See Also:
    jnp.mgrid: dense version of jnp.ogrid

  Examples:
    Pass ``[start:stop:step]`` to generate values similar to :func:`jax.numpy.arange`:

    >>> bm.ogrid[0:4:1]
    DeviceArray([0, 1, 2, 3], dtype=int32)

    Passing an imaginary step generates values similar to :func:`jax.numpy.linspace`:

    >>> bm.ogrid[0:1:4j]
    DeviceArray([0.        , 0.33333334, 0.6666667 , 1.        ], dtype=float32)

    Multiple slices can be used to create sparse grids of indices:

    >>> bm.ogrid[:2, :3]
    [DeviceArray([[0],
                  [1]], dtype=int32),
     DeviceArray([[0, 1, 2]], dtype=int32)]
  """
  sparse = True
  op_name = "ogrid"


ogrid = _Ogrid()


class _AxisConcat(abc.ABC):
  """Concatenates slices, scalars and array-like objects along a given axis."""
  axis: int
  ndmin: int
  trans1d: int
  op_name: str

  def __getitem__(self, key):
    if not isinstance(key, tuple):
      key = (key,)

    params = [self.axis, self.ndmin, self.trans1d, -1]

    if isinstance(key[0], str):
      # split off the directive
      directive, *key = key  # pytype: disable=bad-unpacking
      # check two special cases: matrix directives
      if directive == "r":
        params[-1] = 0
      elif directive == "c":
        params[-1] = 1
      else:
        vec = directive.split(",")
        k = len(vec)
        if k < 4:
          vec += params[k:]
        else:
          # ignore everything after the first three comma-separated ints
          vec = vec[:3] + params[-1]
        try:
          params = list(map(int, vec))
        except ValueError as err:
          raise ValueError(
            "could not understand directive {!r}".format(directive)
          ) from err

    axis, ndmin, trans1d, matrix = params

    output = []
    for item in key:
      if isinstance(item, slice):
        newobj = _make_1d_grid_from_slice(item, op_name=self.op_name)
      elif isinstance(item, str):
        raise ValueError("string directive must be placed at the beginning")
      else:
        newobj = item

      newobj = array(newobj, copy=False, ndmin=ndmin)

      if trans1d != -1 and ndmin - np.ndim(item) > 0:
        shape_obj = list(range(ndmin))
        # Calculate number of left shifts, with overflow protection by mod
        num_lshifts = ndmin - abs(ndmin + trans1d + 1) % ndmin
        shape_obj = tuple(shape_obj[num_lshifts:] + shape_obj[:num_lshifts])

        newobj = transpose(newobj, shape_obj)

      output.append(newobj)

    res = concatenate(tuple(output), axis=axis)

    if matrix != -1 and res.ndim == 1:
      # insert 2nd dim at axis 0 or 1
      res = expand_dims(res, matrix)

    return res

  def __len__(self):
    return 0


class RClass(_AxisConcat):
  """Concatenate slices, scalars and array-like objects along the first axis.

  LAX-backend implementation of :obj:`numpy.r_`.

  See Also:
    ``jnp.c_``: Concatenates slices, scalars and array-like objects along the last axis.

  Examples:
    Passing slices in the form ``[start:stop:step]`` generates ``jnp.arange`` objects:

    >>> bm.r_[-1:5:1, 0, 0, bm.array([1,2,3])]
    DeviceArray([-1,  0,  1,  2,  3,  4,  0,  0,  1,  2,  3], dtype=int32)

    An imaginary value for ``step`` will create a ``jnp.linspace`` object instead,
    which includes the right endpoint:

    >>> bm.r_[-1:1:6j, 0, bm.array([1,2,3])]
    DeviceArray([-1.        , -0.6       , -0.20000002,  0.20000005,
                  0.6       ,  1.        ,  0.        ,  1.        ,
                  2.        ,  3.        ], dtype=float32)

    Use a string directive of the form ``"axis,dims,trans1d"`` as the first argument to
    specify concatenation axis, minimum number of dimensions, and the position of the
    upgraded array's original dimensions in the resulting array's shape tuple:

    >>> bm.r_['0,2', [1,2,3], [4,5,6]] # concatenate along first axis, 2D output
    DeviceArray([[1, 2, 3],
                 [4, 5, 6]], dtype=int32)

    >>> bm.r_['0,2,0', [1,2,3], [4,5,6]] # push last input axis to the front
    DeviceArray([[1],
                 [2],
                 [3],
                 [4],
                 [5],
                 [6]], dtype=int32)

    Negative values for ``trans1d`` offset the last axis towards the start
    of the shape tuple:

    >>> bm.r_['0,2,-2', [1,2,3], [4,5,6]]
    DeviceArray([[1],
                 [2],
                 [3],
                 [4],
                 [5],
                 [6]], dtype=int32)

    Use the special directives ``"r"`` or ``"c"`` as the first argument on flat inputs
    to create an array with an extra row or column axis, respectively:

    >>> bm.r_['r',[1,2,3], [4,5,6]]
    DeviceArray([[1, 2, 3, 4, 5, 6]], dtype=int32)

    >>> bm.r_['c',[1,2,3], [4,5,6]]
    DeviceArray([[1],
                 [2],
                 [3],
                 [4],
                 [5],
                 [6]], dtype=int32)

    For higher-dimensional inputs (``dim >= 2``), both directives ``"r"`` and ``"c"``
    give the same result.
  """
  axis = 0
  ndmin = 1
  trans1d = -1
  op_name = "r_"


r_ = RClass()


class CClass(_AxisConcat):
  """Concatenate slices, scalars and array-like objects along the last axis.

  LAX-backend implementation of :obj:`numpy.c_`.

  See Also:
    ``jnp.r_``: Concatenates slices, scalars and array-like objects along the first axis.

  Examples:

    >>> a = bm.arange(6).reshape((2,3))
    >>> bm.c_[a,a]
    DeviceArray([[0, 1, 2, 0, 1, 2],
                 [3, 4, 5, 3, 4, 5]], dtype=int32)

    Use a string directive of the form ``"axis:dims:trans1d"`` as the first argument to specify
    concatenation axis, minimum number of dimensions, and the position of the upgraded array's
    original dimensions in the resulting array's shape tuple:

    >>> bm.c_['0,2', [1,2,3], [4,5,6]]
    DeviceArray([[1],
                 [2],
                 [3],
                 [4],
                 [5],
                 [6]], dtype=int32)

    >>> bm.c_['0,2,-1', [1,2,3], [4,5,6]]
    DeviceArray([[1, 2, 3],
                 [4, 5, 6]], dtype=int32)

    Use the special directives ``"r"`` or ``"c"`` as the first argument on flat inputs
    to create an array with inputs stacked along the last axis:

    >>> jnp.c_['r',[1,2,3], [4,5,6]]
    DeviceArray([[1, 4],
                 [2, 5],
                 [3, 6]], dtype=int32)
  """
  axis = -1
  ndmin = 2
  trans1d = 0
  op_name = "c_"


c_ = CClass()

s_ = np.s_

index_exp = np.index_exp
