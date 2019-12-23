from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext
import numpy

ext_modules=[ Extension("pictorial",
              ["pictorial.pyx"],
              libraries=["m"],
              extra_compile_args = ["-ffast-math", "-O3"],
              include_dirs=[numpy.get_include()])]

setup(
  name = "pictorial",
  cmdclass = {"build_ext": build_ext},
  ext_modules = ext_modules)