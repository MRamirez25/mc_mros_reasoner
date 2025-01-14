#!/usr/bin/env python
###########################################
#
# authors:    M.A.GarzonOviedo@tudelft.nl
#             c.h.corbato@tudelft.nl
##########################################

from collections import defaultdict

import argparse
from decimal import Decimal

import signal
import sys
from threading import Lock

from mros1_reasoner.tomasys import remove_objective_grounding, ground_fd
from mros1_reasoner.tomasys import updateQAvalue, updateQAestimation
from mros1_reasoner.tomasys import resetFDRealisability, resetObjStatus

from owlready2 import sync_reasoner_pellet, destroy_entity

import logging


class Reasoner(object):
    """docstring for Reasoner."""

    def __init__(self):
        super(Reasoner, self).__init__()
        # Initialize global variables
        # owl model with the tomasys ontology
        self.tomasys = None
        # owl model with the application model
        # as individuals of tomasys classes
        self.onto = None
        # whether we are running a mock system (True),
        # so reasoning happens in isolation, or connected to the real system
        self.mock = True

        # name of the current system configuration, as stored in KB
        # TODO move to RosReasoner or remove: there can be multiple
        # configurations grounded (for multiple objectives)
        self.grounded_configuration = None

        # This Lock is used to ensure safety of tQAvalues
        self.ontology_lock = Lock()

        signal.signal(signal.SIGINT, self.save_ontology_exit)
        self.isInitialized = True

    def remove_objective(self, objective_id):
        # Checks if there are previously defined objectives.
        old_objective = self.onto.search_one(iri="*{}".format(objective_id))
        if old_objective:
            old_fg_instance = self.onto.search_one(solvesO=old_objective)
            with self.ontology_lock:
                destroy_entity(old_fg_instance)
                destroy_entity(old_objective)
            return True
        else:
            return False

    def search_objectives(self):
        # Root objectives
        objectives = self.onto.search(type=self.tomasys.Objective)
        return objectives

    def get_new_tomasys_objective(self, objective_name, iri_seed):
        """Creates Objective individual in the KB given a desired name
           and a string seed for the Function name
        """
        objective = self.tomasys.Objective(str(objective_name),
                                           namespace=self.onto,
                                           typeF=self.onto.search_one(
                                               iri=str(iri_seed)))
        return objective

    def get_new_tomasys_nrf(self, qa_value_name, iri_seed, nfr_value):
        """Creates QAvalue individual in the KB given a desired name
           and a string seed for the QAtype name and the value
        """
        new_nfr = self.tomasys.QAvalue(str(qa_value_name),
                                       namespace=self.onto,
                                       isQAtype=self.onto.search_one(
                                           iri=str(iri_seed)),
                                       hasValue=nfr_value)
        return new_nfr

    def set_new_grounding(self, fd_name, objective):
        """Given a string fd_name with the name of a FunctionDesign and
           an objective, removes the previous fg for the objective
           and ground a new fg of typeF fd
        """
        remove_objective_grounding(objective, self.tomasys, self.onto)
        fd = self.onto.search_one(iri="*{}".format(fd_name),
                                  is_a=self.tomasys.FunctionDesign)
        if fd:
            with self.ontology_lock:
                ground_fd(fd, objective, self.tomasys, self.onto)
                resetObjStatus(objective)
            return str(fd.name)
        else:
            return None

    # the DiagnosticStatus message process contains, per field
    # - message: "binding_error"
    # - name: name of the fg reported, as named in the OWL file
    # - level: values 0 and 1 are mapped to nothing, values 2 or 3 are mapped
    #   to fg.status="INTERNAL_ERROR"
    def updateBinding(self, diagnostic_status):
        fg = self.onto.search_one(iri="*{}".format(diagnostic_status.name))
        if fg is None:
            return -1
        if diagnostic_status.level > 1:
            fg.fg_status = "INTERNAL_ERROR"
            return 1
        else:
            return 0

    # Converst a string to Boolean
    @staticmethod
    def str2bool(v):
        return v.lower() in ("yes", "true", "t", "1")

    # the DiagnosticStatus message process contains, per field
    # - message: "Component status"
    # - key: name of the Component Reported, as named in the OWL file
    # - value: (True, False ) Meaning whether or not the component is working
    def updateComponentStatus(self, diagnostic_status):
        # Find the Component with the same name that the one in the Component
        # Status message (in diagnostic_status.key)
        component_type = self.onto.search_one(
            iri="*{}".format(diagnostic_status.values[0].key))
        if component_type is not None:
            value = diagnostic_status.values[0].value
            with self.ontology_lock:
                resetFDRealisability(
                    self.tomasys, self.onto, diagnostic_status.values[0].key)
                component_type.c_status = value
            return_value = 1
        else:
            return_value = 0
        return return_value

    # update QA value based on incoming diagnostic
    def updateQA(self, diagnostic_status):
        # Find the FG with the same name that the one in the QA message
        # (in diagnostic_status.name)

        return_value = 0
        if len(self.tomasys.FunctionGrounding.instances()) == 0:
            return -1

        fg = next((fg for fg in self.tomasys.FunctionGrounding.instances()
                  if fg.name == diagnostic_status.name), None)
        if fg is None:
            fg = self.tomasys.FunctionGrounding.instances()[0]

        qa_type = self.onto.search_one(iri="*{}".format(
            diagnostic_status.values[0].key))

        if qa_type is not None:
            value = float(diagnostic_status.values[0].value)
            with self.ontology_lock:
                updateQAvalue(fg, qa_type, value, self.tomasys, self.onto)
            return_value = 1

        return return_value

    # Adding Jasper's function to update QA estimations
    def updateQA_pred(self, values):
        # Find the FG with the same name that the one in the QA message (in diagnostic_status.name)
        return_value = 0
        for i in range(len(values)):
            print("Prediction received for %s, safety=%s" % (values[i].key, values[i].value))
            fd = next((fd for fd in self.tomasys.FunctionDesign.instances() if fd.name == values[i].key), None)
            qa_type = self.onto.search_one(iri="*{}".format('safety'))
            if qa_type != None:
                value = float(values[i].value)
                with self.ontology_lock:
                    updateQAestimation(fd, qa_type, value)
                return_value = 1
            else:
                return_value = 0
                return return_value
        return return_value

    # EXEC REASONING to update ontology with inferences
    # TODO CHECK: update reasoner facts, evaluate, retrieve action, publish
    # update reasoner facts
    def perform_reasoning(self):
        return_value = False
        with self.ontology_lock:
            with self.onto:
                try:
                    sync_reasoner_pellet(infer_property_values=True,
                                         infer_data_property_values=True)
                    return_value = True
                except Exception as err:
                    logging.exception("{0}".format(err))
                    return False
                    # raise err
        return return_value

    # For debugging purposes: saves state of the KB in an ontology file
    # TODO move to library
    # TODO save file in a temp location
    def save_ontology_exit(self, signal, frame):
        self.onto.save(file="error.owl", format="rdfxml")
        sys.exit(0)
