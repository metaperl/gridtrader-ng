# -*- coding: utf-8 -*-

from sympy import N
from sympy.core.numbers import Float

def mystr(f): return "{:.8f}".format(float(f))
Float.__str__ = Float.__repr__ = mystr


def F(n):
    return N(n, 8)


def CF(config, config_section, config_parm):
    return F(config.getfloat(config_section, config_parm))

