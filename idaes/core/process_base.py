##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Base for IDAES process model objects.
"""
from __future__ import absolute_import  # disable implicit relative imports
from __future__ import division  # No integer division
from __future__ import print_function  # Python 3 style print

import logging

from pyomo.core.base.block import _BlockData
from pyomo.environ import Block
from pyomo.gdp import Disjunct
from pyomo.common.config import ConfigBlock
from pyutilib.enum import Enum

from idaes.core.process_block import declare_process_block_class
from idaes.core.util.exceptions import (BurntToast,
                                        ConfigurationError,
                                        DynamicError,
                                        PropertyPackageError)
from idaes.core.util.misc import add_object_reference


# Some more inforation about this module
__author__ = "John Eslick, Qi Chen, Andrew Lee"


__all__ = ['ProcessBlockData']


useDefault = object()


# Set up logger
_log = logging.getLogger(__name__)


# Enumerate options for material flow basis
MaterialFlowBasis = Enum(
    'molar',
    'mass',
    'other')


@declare_process_block_class("ProcessBaseBlock")
class ProcessBlockData(_BlockData):
    """
    Base class for most IDAES process models and classes.

    The primary purpose of this class is to create the local config block to
    handle arguments provided by the user when constructing an object and to
    ensure that these arguments are stored in the config block.

    Additionally, this class contains a number of methods common to all IDAES
    classes.
    """
    CONFIG = ConfigBlock("ProcessBlockData", implicit=False)

    def __init__(self, component):
        """
        Initialize a ProcessBlockData object.

        Args:
            component(Block): container Block instance to which this _BlockData
                              belongs.

        Returns:
            (ProcessBlockData): A new instance
        """
        super(ProcessBlockData, self).__init__(component=component)
        self._pb_configured = False

    def build(self):
        """
        The build method is called by the default ProcessBlock rule.  If a rule
        is sepecified other than the default it is important to call
        ProcessBlockData's build method to put information from the "default"
        and "initialize" arguments to a ProcessBlock derived class into the
        BlockData object's ConfigBlock.

        The the build method should usually be overloaded in a subclass derived
        from ProcessBlockData. This method would generally add Pyomo components
        such as variables, expressions, and constraints to the object. It is
        important for build() methods implimented in derived classes to call
        build() from the super class.

        Args:
            None

        Returns:
            None
        """
        self._get_config_args()

    def flowsheet(self):
        """
        This method returns the components parent flowsheet object, i.e. the
        flowsheet component to which the model is attached. If the component
        has no parent flowsheet, the method returns None.

        Args:
            None

        Returns:
            Flowsheet object or None
        """
        parent = self.parent_block()

        while True:
            if parent is None:
                return None

            if hasattr(parent, 'is_flowsheet') and parent.is_flowsheet():
                return parent

            else:
                parent = parent.parent_block()

    def _get_config_args(self):
        """
        Get config arguments for this element and put them in the ConfigBlock
        """
        if self._pb_configured:
            return
        self._pb_configured = True
        idx_map = self.parent_component()._idx_map  # index map function
        try:
            idx = self.index()
        except:
            idx = None
        if idx_map is not None:
            idx = idx_map(idx)
        initialize = self.parent_component()._block_data_config_initialize
        if idx in initialize:
            kwargs = initialize[idx]
        else:
            kwargs = self.parent_component()._block_data_config_default
        self.config = self.CONFIG(kwargs)

    def fix_initial_conditions(self, state="steady-state"):
        """This method fixes the initial conditions for dynamic models.

        Args:
            state : initial state to use for simulation (default =
                    'steady-state')

        Returns :
            None
        """
        if state == 'steady-state':
            for obj in self.component_objects((Block, Disjunct),
                                              descend_into=True):
                # Try to fix material_accumulation @ first time point
                try:
                    obj.material_accumulation[
                            obj.flowsheet().config.time.first(), ...].fix(0.0)
                except AttributeError:
                    pass

                # Try to fix element_accumulation @ first time point
                try:
                    obj.element_accumulation[
                            obj.flowsheet().config.time.first(), ...].fix(0.0)
                except AttributeError:
                    pass

                # Try to fix enthalpy_accumulation @ first time point
                try:
                    obj.enthalpy_accumulation[
                            obj.flowsheet().config.time.first(), ...].fix(0.0)
                except AttributeError:
                    pass

        else:
            raise ValueError("Unrecognised value for argument 'state'. "
                             "Valid values are 'steady-state'.")

    def unfix_initial_conditions(self):
        """This method unfixed the initial conditions for dynamic models.

        Args:
            None

        Returns :
            None
        """
        for obj in self.component_objects(Block, descend_into=True):
            # Try to unfix material_accumulation @ first time point
            try:
                obj.material_accumulation[
                        obj.flowsheet().config.time.first(), ...].unfix()
            except AttributeError:
                pass

            # Try to fix element_accumulation @ first time point
            try:
                obj.element_accumulation[
                        obj.flowsheet().config.time.first(), ...].unfix()
            except AttributeError:
                pass

            # Try to fix enthalpy_accumulation @ first time point
            try:
                obj.enthalpy_accumulation[
                        obj.flowsheet().config.time.first(), ...].unfix()
            except AttributeError:
                pass

    def _setup_dynamics(self):
        """
        This method automates the setting of the dynamic flag and time domain
        for unit models.

        Performs the following:
         1) Determines if this is a top level flowsheet
         2) Gets dynamic flag from parent if not top level, or checks validity
            of argument provided
         3) Checks has_holdup flag if present and dynamic = True

        Args:
            None

        Returns:
            None
        """
        # Get parent object
        if hasattr(self.parent_block(), "config"):
            # Parent block has a config block, so use this
            parent = self.parent_block()
        else:
            # Use parent flowsheet
            try:
                parent = self.flowsheet()
            except ConfigurationError:
                raise DynamicError('{} has no parent flowsheet from which to '
                                   'get dynamic argument. Please provide a '
                                   'value for this argument when constructing '
                                   'the unit.'
                                   .format(self.name))

        # Check the dynamic flag, and retrieve if necessary
        if self.config.dynamic == useDefault:
            # Get flag from parent flowsheet
            try:
                self.config.dynamic = parent.config.dynamic
            except AttributeError:
                # No flowsheet, raise exception
                raise DynamicError('{} parent flowsheet has no dynamic '
                                   'argument. Please provide a '
                                   'value for this argument when constructing '
                                   'the unit.'
                                   .format(self.name))

        # Check for case when dynamic=True, but parent dynamic=False
        if (self.config.dynamic and not parent.config.dynamic):
            raise DynamicError('{} trying to declare a dynamic model within '
                               'a steady-state flowsheet. This is not '
                               'supported by the IDAES framework. Try '
                               'creating a dynamic flowsheet instead, and '
                               'declaring some models as steady-state.'
                               .format(self.name))

        # Set and validate has_holdup argument
        if self.config.has_holdup == useDefault:
            # Default to same value as dynamic flag
            self.config.has_holdup = self.config.dynamic
        elif self.config.has_holdup is False:
            if self.config.dynamic is True:
                # Dynamic model must have has_holdup = True
                raise ConfigurationError(
                            "{} invalid arguments for dynamic and has_holdup. "
                            "If dynamic = True, has_holdup must also be True "
                            "(was False)".format(self.name))

    def _get_property_package(self):
        """
        This method gathers the necessary information about the property
        package to be used in the control volume block.

        If a property package has not been provided by the user, the method
        searches up the model tree until it finds an object with the
        'default_property_package' attribute and uses this package for the
        control volume block.

        The method also gathers any default construction arguments specified
        for the property package and combines these with any arguments
        specified by the user for the control volume block (user specified
        arguments take priority over defaults).

        Args:
            None

        Returns:
            None
        """
        # Get property_package block if not provided in arguments
        parent = self.parent_block()
        if self.config.property_package == useDefault:
            # Try to get property_package from parent
            try:
                if parent.config.property_package in [None, useDefault]:
                    parent.config.property_package = \
                        self._get_default_prop_pack()

                self.config.property_package = parent.config.property_package
            except AttributeError:
                self.config.property_package = self._get_default_prop_pack()

        # Check for any flowsheet level build arguments
        for k in self.config.property_package.config.default_arguments:
            if k not in self.config.property_package_args:
                self.config.property_package_args[k] = \
                    self.config.property_package.config.default_arguments[k]

    def _get_default_prop_pack(self):
        """
        This method is used to find a default property package defined at the
        flowsheet level if a package is not provided as an argument when
        instantiating the control volume block.

        Args:
            None

        Returns:
            None
        """
        parent = self.flowsheet()
        while True:
            if parent is None:
                raise ConfigurationError(
                            '{} no property package provided and '
                            'no default defined by parent flowsheet(s).'
                            .format(self.name))
            elif parent.config.default_property_package is not None:
                _log.info('{} Using default property package'
                          .format(self.name))
                return parent.config.default_property_package

            parent = parent.flowsheet()

    def _get_indexing_sets(self):
        """
        This method collects all necessary indexing sets from property
        parameter block and makes references to these for use within the
        control volume block. Collected indexing sets are phase_list and
        component_list.

        Args:
            None

        Returns:
            None
        """
        # Get phase list(s)
        try:
            add_object_reference(self, "phase_list_ref",
                                 self.config.property_package.phase_list)
        except AttributeError:
            raise PropertyPackageError(
                '{} property_package provided does not '
                'contain a phase_list. '
                'Please contact the developer of the property package.'
                .format(self.name))

        # Check for component list(s)
        if not hasattr(self.config.property_package, "component_list"):
            raise PropertyPackageError(
                '{} property_package provided does not '
                'contain a component_list. '
                'Please contact the developer of the property package.'
                .format(self.name))

    def _get_reaction_package(self):
        """
        This method gathers the necessary information about the reaction
        package to be used in the control volume block (if required).

        If a reaction package has been provided by the user, the method
        gathers any default construction arguments specified
        for the reaction package and combines these with any arguments
        specified by the user for the control volume block (user specified
        arguments take priority over defaults).

        Args:
            None

        Returns:
            None
        """
        if self.config.reaction_package is not None:
            # Check for any flowsheet level build arguments
            for k in self.config.reaction_package.config.default_arguments:
                if k not in self.config.reaction_package_args:
                    self.config.reaction_package_args[k] = \
                       self.config.reaction_package.config.default_arguments[k]

    def _get_phase_comp_list(self):
        """
        Method to collect phase-component list from property package.
        If property package does not define a phase-component list, then it is
        assumed that all components are present in all phases.

        Args:
            None

        Returns:
            phase_component_list
        """
        # Get phase component list(s)
        if hasattr(self.config.property_package, "phase_component_list"):
            phase_component_list =\
                self.config.property_package.phase_component_list
        else:
            # Otherwise assume all components in all phases
            phase_component_list = {}
            for p in self.phase_list_ref:
                phase_component_list[p] = self.config.property_package.\
                    component_list
        return phase_component_list
