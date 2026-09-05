from cypack.utils import axpy

import hashlib
import importlib.resources


def the_answer():
    "The Answer to the Ultimate Question of Life, The Universe, and Everything."
    return axpy(4, 10, 2)


def zen_hash():
    zen = importlib.resources.read_binary("cypack.data", "zen.txt")
    return hashlib.md5(zen).hexdigest()
