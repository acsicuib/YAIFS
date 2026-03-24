"""
Distribution utilities for YAFS.

This module defines a small hierarchy of classes that encapsulate
time distributions used in the simulator (for example, inter-arrival
times of messages or delays between events).
"""
import random
import warnings

import numpy as np


class Distribution(object):
    """
    Abstract base class for all distributions.

    Subclasses must override :meth:`next` to return the next sampled
    value from the underlying distribution.
    """
    def __init__(self, name):
        """
        Parameters
        ----------
        name : str
            Identifier for the distribution (used mainly for logging
            and debugging).
        """
        self.name = name

    def next(self):
        """
        Return the next sampled value.

        Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement 'next'.")


class deterministic_distribution(Distribution):
    """
    Deterministic distribution that always returns the same value.
    """

    def __init__(self, time, **kwargs):
        super(deterministic_distribution, self).__init__(**kwargs)
        self.time = time

    def next(self):
        return self.time


class deterministicDistributionStartPoint(Distribution):
    """
    Deterministic distribution with a different first value.

    The first call to :meth:`next` returns ``start``; all subsequent
    calls return ``time``.
    """

    def __init__(self, start, time, **kwargs):
        self.start = start
        self.time = time
        self.started = False
        super(deterministicDistributionStartPoint, self).__init__(**kwargs)

    def next(self):
        if not self.started:
            self.started = True
            return self.start
        return self.time


class exponentialDistribution(Distribution):
    """
    Deprecated exponential distribution wrapper.

    This class is kept for backwards compatibility. Prefer using
    :class:`exponential_distribution` instead.
    """

    def __init__(self, lambd, seed=1, **kwargs):
        warnings.warn(
            "The exponentialDistribution class is deprecated and "
            "will be removed in version 2.0.0. "
            "Use the exponential_distribution function instead.",
            FutureWarning,
            stacklevel=8,
        )
        super(exponentialDistribution, self).__init__(**kwargs)
        self.l = lambd
        self.rnd = np.random.RandomState(seed)

    def next(self):
        value = int(self.rnd.exponential(self.l, size=1)[0])
        # Avoid returning a zero delay.
        if value == 0:
            return 1
        return value


class exponential_distribution(Distribution):
    """
    Exponential distribution wrapper.

    Values are sampled from an exponential distribution with parameter
    ``lambd`` and converted to integers. A minimum value of 1 is
    enforced to avoid zero delays.
    """

    def __init__(self, lambd, seed=1, **kwargs):
        super(exponential_distribution, self).__init__(**kwargs)
        self.l = lambd
        self.rnd = np.random.RandomState(seed)

    def next(self):
        value = int(self.rnd.exponential(self.l, size=1)[0])
        # Avoid returning a zero delay.
        if value == 0:
            return 1
        return value


class exponentialDistributionStartPoint(Distribution):
    """
    Exponential distribution with a different first value.

    The first call to :meth:`next` returns ``start``; subsequent calls
    sample from an exponential distribution with parameter ``lambd``.
    """

    def __init__(self, start, lambd, seed=1, **kwargs):
        self.lambd = lambd
        self.start = start
        self.started = False
        self.rnd = np.random.RandomState(seed)
        super(exponentialDistributionStartPoint, self).__init__(**kwargs)

    def next(self):
        if not self.started:
            self.started = True
            return self.start
        return int(self.rnd.exponential(self.lambd, size=1)[0])


class uniformDistribution(Distribution):
    """
    Uniform integer distribution between ``min`` and ``max`` (inclusive).
    """

    def __init__(self, min, max, seed=1, **kwargs):
        self.min = min
        self.max = max
        self.rnd = random.Random(seed)
        super(uniformDistribution, self).__init__(**kwargs)

    def next(self):
        return self.rnd.randint(self.min, self.max)
