#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Revision $Id: gossipbot.py 1013 2008-05-21 01:08:56Z sfkwc $

import sys
import unittest
import rospy
import rostest
import actionlib

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from metacontrol_msgs.msg import MvpReconfigurationResult
from metacontrol_msgs.msg import MvpReconfigurationAction

PKG = 'mros1_reasoner'
NAME = 'test_models_paper'
MSG_DELAY = 0.2


class TestSendQAValue(unittest.TestCase):
    def __init__(self, *args):
        super(TestSendQAValue, self).__init__(*args)

    def init_node(self):
        rospy.init_node(NAME, anonymous=True)
        self.success = False

        self.result = MvpReconfigurationResult()

        self.message_pub = rospy.Publisher(
            '/diagnostics', DiagnosticArray, queue_size=1)

        self._action_name = 'rosgraph_manipulator_action_server'
        self._as = actionlib.SimpleActionServer(
                self._action_name,
                MvpReconfigurationAction,
                execute_cb=self.execute_cb,
                auto_start=False)
        self._as.start()
        rospy.loginfo('RosgraphManipulator Action Server started.')

    ###########################################################################
    def send_qa_value_msgs(self, key_names, init_value, end_value, step=0.1):
        #######################################################################

        key_value = init_value

        rospy.loginfo("- D - Test sending %s -  %s - Step value %s"
                      % (str(key_names), str(key_value), str(step)))

        max_steps = (end_value - init_value) / step

        rospy.logwarn("--- D --- Max steps %s " % (str(max_steps)))

        step_count = 0

        while (not rospy.is_shutdown()
               and not self.success
               and max_steps > step_count):

            diag_msg = DiagnosticArray()
            diag_msg.header.stamp = rospy.get_rostime()

            for k_name in key_names:
                status_msg = DiagnosticStatus()
                status_msg.level = DiagnosticStatus.OK
                status_msg.name = ""
                status_msg.values.append(
                    KeyValue(str(k_name), str(key_value)))
                status_msg.message = "QA status"
                diag_msg.status.append(status_msg)

            self.message_pub.publish(diag_msg)
            key_value = key_value + step
            step_count = step_count + 1
            rospy.sleep(2.0)

    ###########################################################################
    def send_component_failure_msgs(self, key_names, init_value, timeout=5.0):
        #######################################################################

        key_value = init_value

        rospy.loginfo("- D - Test sending %s -  %s "
                      % (str(key_names), str(key_value)))

        step_count = 0

        diag_msg = DiagnosticArray()
        diag_msg.header.stamp = rospy.get_rostime()

        for k_name in key_names:
            status_msg = DiagnosticStatus()
            status_msg.level = DiagnosticStatus.OK
            status_msg.name = ""
            status_msg.values.append(
                KeyValue(str(k_name), str(key_value)))
            status_msg.message = "Component status"
            diag_msg.status.append(status_msg)

        self.message_pub.publish(diag_msg)

        while (not rospy.is_shutdown()
               and not self.success
               and timeout > step_count):
            step_count = step_count + 1
            rospy.sleep(1.0)

    ###########################################################################
    def test_publish_energy_qa_value(self):
        #######################################################################
        self.init_node()
        # Wait for initial reconfiguration
        rospy.sleep(5.0)

        self.success = False

        # Send energy QA Value
        self.send_qa_value_msgs(["energy"], 0.4, 0.7, 0.09)
        rospy.sleep(1.0)
        self.assert_(self.success)

        # Send safety QA Value
        self.success = False
        self.send_qa_value_msgs(["safety", "not_valid_qa"], 0.4, 0.7, 0.09)
        rospy.sleep(1.0)
        self.assert_(self.success)

        # Send laser failure : FALSE
        self.success = False
        self.send_component_failure_msgs(["laser_resender"], "FALSE")
        rospy.sleep(1.0)
        self.assert_(self.success)

        # Send laser recover RECOVERED
        self.success = False
        self.send_component_failure_msgs(["laser_resender"], "RECOVERED")
        rospy.sleep(1.0)
        self.assert_(self.success)

        # Send low battery : RECOVERED
        self.success = False
        self.send_component_failure_msgs(["battery"], "FALSE")
        rospy.sleep(1.0)
        self.assert_(self.success)

        # Send low battery : RECOVERED
        self.success = False
        self.send_component_failure_msgs(["battery"], "RECOVERED")
        rospy.sleep(1.0)
        self.assert_(self.success)

    ###########################################################################
    def execute_cb(self, goal):
        #######################################################################

        rospy.loginfo("Rosgraph Manipulator Action Server received goal %s"
                      % str(goal))

        if not rospy.has_param('rosgraph_manipulator/configs'):
            rospy.logwarn(
                'No value in ros param server for rosgraph_manipulator/configs'
                + 'setting it to  [f_normal_mode, f_performance_mode, '
                + 'f_slow_mode, f_degraded_mode, f_energy_saving_mode]')
            rospy.set_param('rosgraph_manipulator/configs',
                            ['f_normal_mode', 'f_performance_mode',
                             'f_slow_mode', 'f_degraded_mode',
                             'f_energy_saving_mode'])

        configurations_list = rospy.get_param('rosgraph_manipulator/configs')

        if (goal.desired_configuration_name in configurations_list):
            self.result.result = 1
            self.success = True
        else:
            self.result.result = -1
            self._as.set_aborted(self.result)
            rospy.loginfo('Unknown configuration request %s' % goal)
            return

        rospy.sleep(0.1)
        self._as.set_succeeded(self.result)
        return


if __name__ == '__main__':
    rostest.rosrun(PKG, NAME, TestSendQAValue, sys.argv)
