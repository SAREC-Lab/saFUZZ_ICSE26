from collections import defaultdict
import asyncio
import argparse 
import threading
import paho.mqtt.client as mqtt
import time 
import subprocess
import json
import collections 
import signal
import math 
import sys 
import logging 
import queue 
import pickle
import os 
from geometry_msgs.msg import PoseStamped
from dataclasses import dataclass, field, asdict
from time import gmtime, strftime
import numpy as np
from typing import Tuple
import sys 
import glob

#other imports
from .DockerInterface import Docker_Interface
from .entities import Fuzz_Test
from .ROSInterface import ROS_Interface
from  .log_analyzer import get_max_deviation

#example of discrete throttle thresholds that were tested 

#neutral is 550
THROTTLE_POS_ALTCTL = [0,260,550,600,615]
#netural is 435
THROTTLE_STABILIZE = [0,225,435,445,450]
#default
THROTTLE_DEFAULT = [-100,0,100,300,570]

GEOFENCE_ACTIONS = {0: "None",1:"Warning",2:"Hold mode", 3:"Return mode", 4: "Terminate", 5:"Land mode"}
MODE_TO_THROTTLE = {
    "STABILIZED": THROTTLE_STABILIZE,
    "POSCTL": THROTTLE_POS_ALTCTL,
    "ALTCTL": THROTTLE_POS_ALTCTL
}

#Flight MODES and STATES
#PX4 Flight Modes  
MODES = ['ALTCTL', 'POSCTL', 'OFFBOARD', 'STABILIZED', 'AUTO.LOITER', 'AUTO.RTL', 'AUTO.LAND']
STATES = ['anonymous_states']

#MAVROS SERVICE TOPICS 
SET_PARAM_TOPIC = 'mavros/param/set'
GET_PARAM_TOPIC = 'mavros/param/get'
SEND_CMD = 'mavros/cmd/command'
MAV_STATE = '/mavros/state'
SERVICES = [SEND_CMD,GET_PARAM_TOPIC,SET_PARAM_TOPIC]

#MQTT MISSION SENDER PUB TOPIC and SUB TOPIC for onboard updates 
MQTT_MISSION="anonymous_topic"
MQTT_SUB = "anonymous_topic"

#BLUEPRINT MISSION
MISSION_FILE = 'missions/FUZZ_MISSION.json'

#TIMING THRESHOLDS
LAND_TIME = 0
RTL_TIME = 0 
MISSION_TIME = 0

class Fuzz_Testor():
    def __init__(self,uav_id="Polkadot") -> None:
        #signal.signal(signal.SIGINT, self.signal_handler)
        self.uav_id = uav_id
        #prepare threading events and bind to class 
        self.init_shared_variables()
        #prepare MQTT, and Docker Handler
        #we attach MQTT to the Fuzz_Testor since it has our main testing logic 
        self.__init_mqtt()

        self.mqtt_connected.wait()
        self.__init_docker_interface()
        self.__init_mission_file()

        #init value for mission completion time 
        self.threshold = MISSION_TIME # real values calculated dynamically
        self.timer_lock = threading.Lock()
       
        #needed to adjust timing based on RTL or LAND 
        self.adjust_timer_event = threading.Event()
        self.timer_adjust_thread = threading.Thread(target=self.timer_adjustment_handler)
        #self.timer_adjust_thread.start()
        
        #start time checking thread 
        self.time_thread = threading.Thread(target=self.check_time_threshold)
        self.time_thread.start()

        self.mission_thread = threading.Thread(target=self.send_mission_thread)
        self.mission_thread.start()


        self.output = ""
        self.fuzz_type = None 
        self.executed_tests = set()

    
    def save_executed_tests(self):
        with open('executed_tests.pkl', 'wb') as f:
            pickle.dump(self.executed_tests, f)
                
    def load_executed_tests(self):
        # Define file path
        file_path = 'executed_tests.pkl'
        
        # Load executed tests from the file if it exists
        # for geofence tests it will be a set not partitioned by states
        self.executed_tests = self._load_executed_tests()
        
        # Process the loaded tests for standard fuzzes
        # for standard tests (with states) we need to create a dictionary
        if 'state' in self.fuzz_type:
            self.tested_modes_by_state = defaultdict(set)
            #self._process_executed_tests()

    def _load_executed_tests(self):
        if os.path.exists('executed_tests.pkl'):
            try:
                with open('executed_tests.pkl', 'rb') as f:
                    print('[fuzz_testor] found executed tests, loading...')
                    return pickle.load(f)
            except EOFError:
                return set()
        else:
            return set()

    def _process_executed_tests(self):
        includes_modes = '_mode' in self.fuzz_type
        includes_throttles = '_throttle' in self.fuzz_type
        for tuple in self.executed_tests:
            if includes_modes and includes_throttles:
                # Structure: (mode, throttle, state)
                mode, throttle, state = tuple
                executed_test = (mode, throttle)
            elif includes_modes:
                # Structure: (mode, state)
                mode, state = tuple
                executed_test = (mode,) 
            elif includes_throttles:
                # Structure: (throttle, state)
                throttle, state = tuple
                executed_test = (throttle,) 
            self.tested_modes_by_state[state].add(executed_test)

    def init_shared_variables(self) -> None:
        self.mqtt_message_queue = queue.Queue()
        #main lock for each fuzz execution (each fuzz task/scenario)
        self.main_lock = threading.Lock()
        self.critical_lock = threading.Lock()
        #throttle lock and variable
        self.throttle_lock = threading.Lock()
        self.throttle_value = None 

        #EVENTS 
        self.mission_ready = threading.Event()
        self.mission_time = threading.Event()
        self.mission_abort = threading.Event()
        self.mqtt_connected = threading.Event()
        self.force_shutdown = threading.Event()

        self.tests_queue = queue.Queue()
        self.test_ready = threading.Event()

        self.test_complete = threading.Event()



    def __init_mqtt(self) -> None:
        self.mqtt_client = mqtt.Client("Fuzzing_System")
        self.mqtt_client.on_connect = self.mqtt_on_connect

        self.mqtt_client.connect("mqtt",1883)
        self.mqtt_client.loop_start()

    def __init_mission_file(self) -> None:
        file_path = os.path.join(os.path.dirname(__file__), "missions", MISSION_FILE)
        f = open(file_path, 'r')
        self.mission_file = json.load(f)
        f.close()
        return 

    def mqtt_on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            print("Connected to MQTT broker successfully!")
            #simple flag to control mqtt on message 
            self.message_sent = False
            self.mqtt_client.subscribe([("anon",0),("fuzz_mission/ready",1)])
            self.mqtt_client.message_callback_add("fuzz_mission/ready",self.mqtt_on_mission_ready)
            self.mqtt_client.message_callback_add("anon",self.mqtt_on_message)
            self.mqtt_connected.set()
        else:
            print("Failed to connect to MQTT broker with return code: {}".format(rc))
    
    def __init_docker_interface(self) -> None:
        self.docker_interface = Docker_Interface(self.mqtt_client,self.uav_id)
        self.docker_interface.run_onboard()

    def _abort_mission(self):
        #use docker handler for shutdown 
        #set mission abort event 
        self.mission_ready.clear()
        #shut down state machine and px4 
        self.docker_interface.abort_mission()
        return 

    def _cleanup(self):
        self.ros_interface.cleanup()
        time.sleep(1)
        self.docker_interface.run_onboard()
        return 
    
    def _adjust_wind(self):
        self.docker_interface.adjust_wind()

    def enqueue_mqtt_message(self):
        self.mqtt_message_queue.put(json.dumps(self.mission_file))

    def mqtt_on_mission_ready(self,client, userdata, msg):
        print('[fuzz_testor] received mission ready')
        if not self.mission_ready.is_set():
            self.mission_ready.set()
    

    def send_mission(self,message):
        #wait for state machine to be ready 
        print('[fuzz_testor] waiting for state machine ...')
        
        self.mission_ready.wait()
        # small sleep before we publish the mission 
        time.sleep(2)
        self.mqtt_client.publish(MQTT_MISSION.format(self.uav_id),message)
        print('[fuzz_testor] recieved ready, publishing mission')
        self._start_mission_timer()

    def send_mission_thread(self):
        while not self.force_shutdown.is_set():
            try:
                message = self.mqtt_message_queue.get(timeout=1)  # Wait for a message
                self.send_mission(message)
                self.mqtt_message_queue.task_done()
            except queue.Empty:
                continue

    def load_msg(self,msg):
        msg = json.loads(msg.payload)
        status = msg["status"]
        if status == "success":
            return status
        curr_state = status["state_name"]
        return curr_state

    def _start_mission_timer(self):
        print('[fuzz_tester] starting timer')
        self.mission_start_time = time.time()
        self.mission_time.set()
    

    def run_test(self,fuzz_test:Fuzz_Test,ones_columns):
        '''
        Executes a fuzz test based on the provided Fuzz_Test instance.
        Can be a single test, or multiple depending on input.

        Args:
            fuzz_test (Fuzz_Test): An instance of Fuzz_Test containing all necessary parameters for the test.
        '''
        throttle_value = self.throttle_value if fuzz_test.throttle else None
        throttle_lock = self.throttle_lock if fuzz_test.throttle else None
        self.output = ""

        # Initialize ROS_Interface with throttle parameters and adjust timer event if applicable
        if fuzz_test.rtl_mode or fuzz_test.geo_RTL_flag or fuzz_test.land_mode or fuzz_test.geo_land_flag:
            print('adjustment needed')
            adjust_timer_event = self.adjust_timer_event
        else:
            print('no adjustement needed')
            adjust_timer_event = None 

        self.ros_interface = ROS_Interface(
            throttle_value=throttle_value,
            throttle_lock=throttle_lock,
            adjust_timer_event= adjust_timer_event
        )

        # Set up geofence if applicable
        if fuzz_test.geofence:
            self.fuzz_test_combinations = fuzz_test.test_combinations
            #print('combinations: ',fuzz_test.test_combinations)
            self.fuzz_type = fuzz_test.fuzz_type
            #turn geofence on 
            self.ros_interface.toggle_geofence(20.0)
            self.ros_interface.sub_geo_breach()
                
        else:
            #make sure geofence is off 
            self.ros_interface.toggle_geofence(0.0)
            self.fuzz_type = fuzz_test.fuzz_type
            self.fuzz_test_combinations = fuzz_test.test_combinations
            self.mode_throttle_combos = fuzz_test.remove_states_from_combinations()
        self.load_executed_tests()
        fuzz_test.ones_columns = ones_columns
        self.fuzz_test = fuzz_test 
        print('[fuzz_testor] preparing to send mission')
        self.enqueue_mqtt_message()
        return 

    def select_fuzz_test(self,current_state):
        if "geo" in self.fuzz_type:
            available_tests = self.fuzz_test_combinations - self.executed_tests
        else:
            if current_state not in self.fuzz_test.states:
                return None 
            tested = self.tested_modes_by_state.get(current_state,set())
            available_tests = self.mode_throttle_combos - tested
        if not available_tests:
            return None 
        return available_tests.pop()

    def execute_fuzz_test(self, fuzz_tuple):
        command_dict = self.fuzz_test.populate_command(fuzz_tuple)
        
        reordered_command_dict = {}
        print('executing fuzz tuple',fuzz_tuple)
        if self.fuzz_test.order:
            if 'set_throttle' in command_dict:
                reordered_command_dict['set_throttle'] = command_dict['set_throttle']
            if 'set_mode' in command_dict:
                reordered_command_dict['set_mode'] = command_dict['set_mode']
            if 'set_param' in command_dict:
                reordered_command_dict['set_param'] = command_dict['set_param']
            command_dict = reordered_command_dict

        if "geo" in self.fuzz_type:
            self.ros_interface.reset_fuzz_done_flag()
            self.ros_interface.reset_geo_flag()
            self.ros_interface.send_geo_commands(command_dict)
        else:
            self.ros_interface.send_command(command_dict,self.fuzz_test.timing)
            self.time_in = self.ros_interface.time_in

        return 
    
    '''
    Main function that relies on MQTT for fuzzing based on the drone state.
    '''
    def mqtt_on_message(self, client, userdata, msg):
        # if we aren't in the abort state or we are still waiting for mission ready signal 
        if self.mission_abort.is_set() or not self.mission_ready.is_set():
            return 
        curr_state = self.load_msg(msg)
        with self.critical_lock:
            if self.mission_abort.is_set() or self.force_shutdown.is_set() or self.test_complete.is_set():
                return 
            if curr_state == "success":
                print('mission success')
                self.mission_time.clear()
                self.ros_interface.cleanup()
                ulg_file_path = self.docker_interface.get_latest_ulg_file()
                print('copying from docker...')
                self.save_contender_file(ulg_file_path)
                self.write_to_file(ulg_file_path,True,self.time_in)
                self.save_executed_tests()
                self.test_complete.set()
                self.message_sent = False 
                return 
            else:
                if self.message_sent:
                    return 
                fuzz_to_execute = self.select_fuzz_test(curr_state)
 
                if not fuzz_to_execute:
                    if self.executed_tests == self.fuzz_test_combinations:
                        print('[fuzz_testor] finished with all tests!')
                        self.test_complete.set()
                    return 
                
                print(f'[fuzz_testor] executing {fuzz_to_execute}')
                self.execute_fuzz_test(fuzz_to_execute)

                #updating executed tests 
                if "state" in self.fuzz_type:
                    self.tested_modes_by_state.setdefault(curr_state, set()).add(fuzz_to_execute)
                    executed_tuple = fuzz_to_execute + (curr_state,)
                    self.executed_tests.add(executed_tuple)
                    self.recent_test = executed_tuple 
                elif "geo" in self.fuzz_type:
                    self.executed_tests.add(fuzz_to_execute)
                    self.recent_test = fuzz_to_execute
                self.message_sent = True 
    
    def calculate_rtl_threshold(self):
        # Query the current pose.
        current_pose = self.ros_interface.get_current_pose(timeout=.3)
        if current_pose is None:
            print("[calculate_rtl_threshold] Position data unavailable; using default (0 sec).") 
            return 0

        home_pose = (0,0,0)

        safe_altitude = 50.0    # meters
        climb_rate = 2.5        # m/s
        cruise_speed = 2.5     # m/s
        descent_rate = .8     # m/s

        current_altitude = current_pose.position.z
        climb_time = (safe_altitude - current_altitude) / climb_rate if current_altitude < safe_altitude else 0.0

        # horiz distance in the XY plane.
        dx = current_pose.position.x - 0
        dy = current_pose.position.y - 0
        horizontal_distance = math.sqrt(dx**2 + dy**2)
        horizontal_time = horizontal_distance / cruise_speed

        descent_time = safe_altitude / descent_rate

        total_time = (climb_time + horizontal_time + descent_time) * 1.2
        print(f"[calculate_rtl_threshold] climb: {climb_time:.2f}s, transit: {horizontal_time:.2f}s, "
            f"descent: {descent_time:.2f}s, total: {total_time:.2f}s")
        return total_time+RTL_TIME


    def calculate_land_threshold(self):
        # Query the current pose.
        current_pose = self.ros_interface.get_current_pose(timeout=.3)
        if current_pose is None:
            print("[calculate_land_threshold] Current position data unavailable; using default (0 sec).")
            return 0

        current_altitude = current_pose.position.z
        descent_rate = .8  # m/s

        landing_time = (current_altitude / descent_rate) * 2.2
        print(f"[calculate_land_threshold] altitude: {current_altitude:.2f}m, landing time: {landing_time:.2f}s")
        return landing_time+LAND_TIME

    def timer_adjustment_handler(self):
        """Wait for adjust_timer_event signal, then update mission start time and threshold."""
        while not (self.force_shutdown.is_set() or self.test_complete.is_set()):
            self.adjust_timer_event.wait()
            self.mission_time.clear()

            # Check fuzz_test flags and update timing accordingly.
            if self.fuzz_test.rtl_mode or self.fuzz_test.geo_RTL_flag:
                new_threshold = self.calculate_rtl_threshold()
                print("ADJUSTING TIME....")
                print("[Fuzz_Testor] Adjusting for RTL: New threshold =", new_threshold)
            elif self.fuzz_test.land_mode or self.fuzz_test.geo_land_flag:
                new_threshold = self.calculate_land_threshold()
                print("ADJUSTING TIME....")
                print("[Fuzz_Testor] Adjusting for LAND: New threshold =", new_threshold)

            with self.timer_lock:
                self.mission_start_time = time.time()
                self.threshold = new_threshold

            # Clear the event so it can be triggered again.
            self.adjust_timer_event.clear()
            self.mission_time.set()
            return 


    def check_time_threshold(self):
        while True:
            self.mission_time.wait()
            if self.force_shutdown.is_set() or self.test_complete.is_set():
                print('shutdown_handler] shutting down timing thread')
                return 
            
            #grab updated mission start time 
            with self.timer_lock:
                current_start_time = self.mission_start_time
                current_threshold = self.threshold
                mission_time = time.time()-current_start_time
            
            if mission_time >= current_threshold:
                with self.critical_lock:
                    if self.mission_time.is_set():
                        self.mission_abort.set()
                        print('[fuzz_testor] time exceeded, restarting state machine')
                        ulg_file_path = self.docker_interface.get_latest_ulg_file()
                        self.save_contender_file(ulg_file_path)
                        self.write_to_file(ulg_file_path, False,self.time_in)
                        self.save_executed_tests()
                        self.test_complete.set()
                        return 

    '''
    Function to copy the log file from the px4 container into the fuzz service container.
    '''
    def save_contender_file(self, ulg_file_path):
        source_container = "anon"
        source_id = os.popen(f"docker ps -qf name={source_container}").read().strip()
        source_path = "anon"+ulg_file_path
        destination_path = "anon"
        os.system(f"docker cp {source_id}:{source_path} {destination_path}")


    def write_to_file(self, ulg_file_path, mission_status,time_in):
        max_difference,max_altitude,arm_to_disarm_duration, actually_disarmed, end_land_status, freefall_occurred,thrashing_detected,thrashing_count,nav_frequency_result,drift = get_max_deviation.log_parser(self.fuzz_test.ones_columns)
        json_object = {
            "filename": ulg_file_path,
            "max_deviation": max_difference,
            "max_altitude": max_altitude,
            "duration": arm_to_disarm_duration,
            "actually_disarmed": actually_disarmed,
            "final_landing_state": end_land_status,
            "freefall_occurred": freefall_occurred,
            "mission_complete": mission_status,
            "thrashing_detected":thrashing_detected,
            "thrashing_count":thrashing_count,
            "nav_frequency_result":nav_frequency_result,
            "drift":drift,
            "time_value":time_in
        }

        json_output = json.dumps(json_object, indent=4)
        self.output = json_output
        # Write the formatted message to the file
        with open("anon.txt", 'a') as f:
            f.write(json_output)
        return
    
    def submit_test(self, test):
        self.tests_queue.put(test)
        if not self.test_ready.is_set():
            self.test_ready.set()

    '''
    Option to do queue based 
    '''
    def process_tests(self):
        while not self.force_shutdown.is_set():
            self.test_ready.wait()  # Wait until a test is ready
            try:
                current_test = self.tests_queue.get(timeout=1)  # Get the test from the queue
                self.run_test(current_test)  # Run the test
                self.tests_queue.task_done()
                if self.tests_queue.empty():
                    self.test_ready.clear()
            except queue.Empty:
                continue
    
    
    '''
    gracefully handle hutdown
    '''
    def trigger_shutdown(self):
        print('[shutdown_handler] forcing exit of all threads ....')
        self.shutdown_timer()
        self.ros_interface.reset_attributes()
        print('[shutdown_handler] successfully shutdown rospy')
        self.docker_interface.abort_mission()
        print('[shutdown_handler] successfully shutdown docker')
        self.mqtt_client.loop_stop()
        return


    def shutdown_timer(self):
        self.mission_time.set() 
        self.force_shutdown.set()
        return 