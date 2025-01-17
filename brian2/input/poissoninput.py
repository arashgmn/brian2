"""
Implementation of `PoissonInput`.
"""
from brian2.core.variables import Variables
from brian2.groups.group import CodeRunner
from brian2.units.fundamentalunits import (
    DimensionMismatchError,
    check_units,
    get_dimensions,
    have_same_dimensions,
)
from brian2.units.stdunits import Hz

from .binomial import BinomialFunction

__all__ = ["PoissonInput"]


class PoissonInput(CodeRunner):
    """
    PoissonInput(target, target_var, N, rate, weight, when='synapses', order=0)

    Adds independent Poisson input to a target variable of a `Group`. For large
    numbers of inputs, this is much more efficient than creating a
    `PoissonGroup`. The synaptic events are generated randomly during the
    simulation and are not preloaded and stored in memory. All the inputs must
    target the same variable, have the same frequency and same synaptic weight.
    All neurons in the target `Group` receive independent realizations of
    Poisson spike trains.

    Parameters
    ----------
    target : `Group`
        The group that is targeted by this input.
    target_var : str
        The variable of `target` that is targeted by this input.
    N : int
        The number of inputs
    rate : `Quantity`
        The rate of each of the inputs
    weight : str or `Quantity`
        Either a string expression (that can be interpreted in the context of
        `target`) or a `Quantity` that will be added for every event to
        the `target_var` of `target`. The unit has to match the unit of
        `target_var`
    when : str, optional
        When to update the target variable during a time step. Defaults to
        the `synapses` scheduling slot. See :ref:`scheduling` for possible values.
    order : int, optional
        The priority of of the update compared to other operations occurring at
        the same time step and in the same scheduling slot. Defaults to 0.

    """

    @check_units(N=1, rate=Hz)
    def __init__(self, target, target_var, N, rate, weight, when="synapses", order=0):
        if target_var not in target.variables:
            raise KeyError(f"{target_var} is not a variable of {target.name}")

        self._weight = weight
        self._target_var = target_var

        if isinstance(weight, str):
            weight = f"({weight})"
        else:
            weight_dims = get_dimensions(weight)
            target_dims = target.variables[target_var].dim
            # This will be checked automatically in the abstract code as well
            # but doing an explicit check here allows for a clearer error
            # message
            if not have_same_dimensions(weight_dims, target_dims):
                raise DimensionMismatchError(
                    "The provided weight does not "
                    "have the same unit as the "
                    f"target variable '{target_var}'",
                    weight_dims,
                    target_dims,
                )
            weight = repr(weight)
        self._N = N
        self._rate = rate
        binomial_sampling = BinomialFunction(
            N, rate * target.clock.dt, name="poissoninput_binomial*"
        )

        code = f"{target_var} += {binomial_sampling.name}()*{weight}"
        self._stored_dt = target.dt_[:]  # make a copy
        # FIXME: we need an explicit reference here for on-the-fly subgroups
        # For example: PoissonInput(group[:N], ...)
        self._group = target
        CodeRunner.__init__(
            self,
            group=target,
            template="stateupdate",
            code=code,
            user_code="",
            when=when,
            order=order,
            name="poissoninput*",
            clock=target.clock,
        )
        self.variables = Variables(self)
        self.variables._add_variable(binomial_sampling.name, binomial_sampling)

    rate = property(fget=lambda self: self._rate, doc="The rate of each input")
    N = property(fget=lambda self: self._N, doc="The number of inputs")
    target_var = property(
        fget=lambda self: self._target_var, doc="The targetted variable"
    )
    weight = property(fget=lambda self: self._weight, doc="The synaptic weight")

    def before_run(self, run_namespace):
        if self._group.dt_ != self._stored_dt:
            raise NotImplementedError(
                f"The dt used for simulating {self.group.name} "
                "changed after the PoissonInput source was "
                "created."
            )
        CodeRunner.before_run(self, run_namespace=run_namespace)
