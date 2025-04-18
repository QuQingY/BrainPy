import jax
import jax.numpy as jnp
import taichi as taichi
import pytest
import platform

import brainpy.math as bm

bm.set_platform('cpu')

if not platform.platform().startswith('Windows'):
  pytest.skip(allow_module_level=True)


# @ti.kernel
# def event_ell_cpu(indices: ti.types.ndarray(ndim=2),
#                   vector: ti.types.ndarray(ndim=1),
#                   weight: ti.types.ndarray(ndim=1),
#                   out: ti.types.ndarray(ndim=1)):
#   weight_0 = weight[0]
#   num_rows, num_cols = indices.shape
#   ti.loop_config(serialize=True)
#   for i in range(num_rows):
#     if vector[i]:
#       for j in range(num_cols):
#         out[indices[i, j]] += weight_0

@taichi.func
def get_weight(weight: taichi.types.ndarray(ndim=1)) -> taichi.f32:
  return weight[0]


@taichi.func
def update_output(out: taichi.types.ndarray(ndim=1), index: taichi.i32, weight_val: taichi.f32):
  out[index] += weight_val


@taichi.kernel
def event_ell_cpu(indices: taichi.types.ndarray(ndim=2),
                  vector: taichi.types.ndarray(ndim=1),
                  weight: taichi.types.ndarray(ndim=1),
                  out: taichi.types.ndarray(ndim=1)):
  weight_val = get_weight(weight)
  num_rows, num_cols = indices.shape
  taichi.loop_config(serialize=True)
  for i in range(num_rows):
    if vector[i]:
      for j in range(num_cols):
        update_output(out, indices[i, j], weight_val)


prim = bm.XLACustomOp(cpu_kernel=event_ell_cpu)


def test_taichi_op_register():
  s = 1000
  indices = bm.random.randint(0, s, (s, 1000))
  vector = bm.random.rand(s) < 0.1
  weight = bm.array([1.0])

  out = prim(indices, vector, weight, outs=[jax.ShapeDtypeStruct((s,), dtype=jnp.float32)])

  out = prim(indices, vector, weight, outs=[jax.ShapeDtypeStruct((s,), dtype=jnp.float32)])

  print(out)
  bm.clear_buffer_memory()

# test_taichi_op_register()
