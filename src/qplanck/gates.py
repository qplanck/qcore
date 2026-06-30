"""Gate builder helpers for the supported v0.1 operation subset."""

from qplanck.ir import Operation


def H(q: int) -> Operation:
    return Operation("h", (q,))


def X(q: int) -> Operation:
    return Operation("x", (q,))


def Y(q: int) -> Operation:
    return Operation("y", (q,))


def Z(q: int) -> Operation:
    return Operation("z", (q,))


def S(q: int) -> Operation:
    return Operation("s", (q,))


def T(q: int) -> Operation:
    return Operation("t", (q,))


def RX(theta: float, q: int) -> Operation:
    return Operation("rx", (q,), (theta,))


def RY(theta: float, q: int) -> Operation:
    return Operation("ry", (q,), (theta,))


def RZ(theta: float, q: int) -> Operation:
    return Operation("rz", (q,), (theta,))


def CX(control: int, target: int) -> Operation:
    return Operation("cx", (control, target))


def CZ(control: int, target: int) -> Operation:
    return Operation("cz", (control, target))


h = H
x = X
y = Y
z = Z
s = S
t = T
rx = RX
ry = RY
rz = RZ
cx = CX
cz = CZ
