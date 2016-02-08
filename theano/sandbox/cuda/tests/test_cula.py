import unittest
import numpy

import theano
from theano.tests import unittest_tools as utt

# Skip tests if cuda_ndarray is not available.
from nose.plugins.skip import SkipTest
import theano.sandbox.cuda as cuda_ndarray
from theano.misc.pycuda_init import pycuda_available
from theano.sandbox.cuda.cula import cula_available

from theano.sandbox.cuda import cula

if not cuda_ndarray.cuda_available:
    raise SkipTest('Optional package cuda not available')
if not pycuda_available:
    raise SkipTest('Optional package pycuda not available')
if not cula_available:
    raise SkipTest('Optional package scikits.cuda.cula not available')

if theano.config.mode == 'FAST_COMPILE':
    mode_with_gpu = theano.compile.mode.get_mode('FAST_RUN').including('gpu')
else:
    mode_with_gpu = theano.compile.mode.get_default_mode().including('gpu')


class TestCula(unittest.TestCase):
    def run_gpu_solve(self, A_val, x_val):
        b_val = numpy.dot(A_val, x_val)
        A = theano.tensor.matrix("A", dtype="float32")
        b = theano.tensor.matrix("b", dtype="float32")

        solver = cula.gpu_solve(A, b)
        fn = theano.function([A, b], [solver])
        res = fn(A_val, b_val)
        x_res = numpy.array(res[0])
        utt.assert_allclose(x_res, x_val)

    def test_diag_solve(self):
        numpy.random.seed(1)
        A_val = numpy.asarray([[2, 0, 0], [0, 1, 0], [0, 0, 1]],
                              dtype="float32")
        x_val = numpy.random.uniform(-0.4, 0.4, (A_val.shape[1],
                                     1)).astype("float32")
        self.run_gpu_solve(A_val, x_val)

    def test_sym_solve(self):
        numpy.random.seed(1)
        A_val = numpy.random.uniform(-0.4, 0.4, (5, 5)).astype("float32")
        A_sym = (A_val + A_val.T) / 2.0
        x_val = numpy.random.uniform(-0.4, 0.4, (A_val.shape[1],
                                     1)).astype("float32")
        self.run_gpu_solve(A_sym, x_val)

    def test_orth_solve(self):
        numpy.random.seed(1)
        A_val = numpy.random.uniform(-0.4, 0.4, (5, 5)).astype("float32")
        A_orth = numpy.linalg.svd(A_val)[0]
        x_val = numpy.random.uniform(-0.4, 0.4, (A_orth.shape[1],
                                     1)).astype("float32")
        self.run_gpu_solve(A_orth, x_val)

    def test_uni_rand_solve(self):
        numpy.random.seed(1)
        A_val = numpy.random.uniform(-0.4, 0.4, (5, 5)).astype("float32")
        x_val = numpy.random.uniform(-0.4, 0.4,
                                     (A_val.shape[1], 4)).astype("float32")
        self.run_gpu_solve(A_val, x_val)


class TestGpuCholesky(unittest.TestCase):

    def setUp(self):
        utt.seed_rng()

    def get_gpu_cholesky_func(self, lower):
        """ Helper function to compile function from GPU Cholesky op. """
        A = theano.tensor.matrix("A", dtype="float32")
        chol_A = cula.gpu_cholesky(A, lower)
        return theano.function([A], chol_A)

    def compare_gpu_cholesky_to_numpy(self, A_val, lower):
        """ Helper function to compare op output to numpy.cholesky output. """
        chol_A_val = numpy.linalg.cholesky(A_val)
        if not lower:
            chol_A_val = chol_A_val.T
        fn = self.get_gpu_cholesky_func(lower)
        res = fn(A_val)
        chol_A_res = numpy.array(res)
        utt.assert_allclose(chol_A_res, chol_A_val)

    def test_invalid_input_fail_non_square(self):
        """ Invalid Cholesky input test with non-square matrix as input. """
        def invalid_input_func():
            A_val = numpy.random.normal(size=(3, 2)).astype("float32")
            fn = self.get_gpu_cholesky_func(True)
            fn(A_val)
        self.assertRaises(ValueError, invalid_input_func)

    def test_invalid_input_fail_non_symmetric(self):
        """ Invalid Cholesky input test with non-symmetric input.
            (Non-symmetric real input must also be non-positive definite). """
        def invalid_input_func():
            A_val = numpy.random.normal(size=(3, 3)).astype("float32")
            # double-check random A_val is asymmetric - the probability of
            # this not being the case even with finite precision should be
            # negligible
            assert not numpy.allclose(A_val, A_val.T)
            fn = self.get_gpu_cholesky_func(True)
            fn(A_val)
        self.assertRaises(cula.cula.culaError, invalid_input_func)

    def test_invalid_input_fail_non_positive_definite(self):
        """ Invalid Cholesky input test with non positive-definite input. """
        def invalid_input_func():
            M_val = numpy.random.normal(size=(3, 3)).astype("float32")
            A_val = -M_val.dot(M_val.T)
            fn = self.get_gpu_cholesky_func(True)
            fn(A_val)
        self.assertRaises(cula.cula.culaError, invalid_input_func)

    def test_invalid_input_fail_vector(self):
        """ Invalid Cholesky input test with vector as input. """
        def invalid_input_func():
            A = theano.tensor.vector("A", dtype="float32")
            cula.gpu_cholesky(A, True)
        self.assertRaises(AssertionError, invalid_input_func)

    def test_invalid_input_fail_tensor3(self):
        """ Invalid Cholesky input test with vector as input. """
        def invalid_input_func():
            A = theano.tensor.tensor3("A", dtype="float32")
            cula.gpu_cholesky(A, True)
        self.assertRaises(AssertionError, invalid_input_func)

    def test_diag_chol(self):
        """ Diagonal matrix input with positive entries Cholesky test. """
        A_val = numpy.diag(numpy.random.uniform(size=5).astype("float32") + 1)
        self.compare_gpu_cholesky_to_numpy(A_val, lower=True)

    def test_dense_chol_lower(self):
        """ Dense matrix input lower-triangular Cholesky test. """
        M_val = numpy.random.normal(size=(3, 3)).astype("float32")
        A_val = M_val.dot(M_val.T)
        self.compare_gpu_cholesky_to_numpy(A_val, lower=True)

    def test_dense_chol_upper(self):
        """ Dense matrix input upper-triangular Cholesky test. """
        M_val = numpy.random.normal(size=(3, 3)).astype("float32")
        A_val = M_val.dot(M_val.T)
        self.compare_gpu_cholesky_to_numpy(A_val, lower=False)
