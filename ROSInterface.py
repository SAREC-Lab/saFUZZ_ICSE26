import rospy 
from mavros_msgs.srv import SetMode, CommandBool, ParamPull, ParamPush, ParamGet, ParamSet, CommandLong,CommandBool
from mavros_msgs.msg import State, ParamValue, ManualControl, ExtendedState, StatusText
import threading 
from geometry_msgs.msg import PoseStamped
import time 
import random


class ROS_Interface:
    COMMAND_KILL = 'kill'
    COMMAND_MODE_SWITCH = 'mode_switch'
    COMMAND_SET_PARAM = 'set_param'
    COMMAND_MANUAL_CONTROL = 'manual_control'
    SEND_CMD = 'mavros/cmd/command'
    
    
    def __init__(self,throttle_value,throttle_lock,adjust_timer_event):
        rospy.init_node("Fuzz_Tester")
        self.throttle_value = throttle_value
        self.throttle_lock = throttle_lock 
        self.adjust_timer_event = None
        self.send_cmd = rospy.ServiceProxy(SEND_CMD,CommandLong,persistent=True)
      
        #initialization 
        self.init_services()
        self.init_publishers()
        self.init_subscribers()
        self.init_vars_geofence()
        
        self.running = False 
        #spawn manual control sender thread - RC controller
        if self.throttle_lock:
            self.running = True 
            print('[ros_interface] starting manual control')
            self.throttle_thread = threading.Thread(target=self.manual_control_sender)
            self.throttle_thread.start()

    def init_services(self):
        self.services = {
            'set_param': ('mavros/param/set', ParamSet),
            'get_param': ('mavros/param/get', ParamGet),
            'send_command': ('mavros/cmd/command', CommandLong),
            'set_mode': ('mavros/set_mode', SetMode),
            'arm': ('mavros/cmd/arming', CommandBool)
        }
        for key, (topic, srv_type) in self.services.items():
            try:
                rospy.wait_for_service(topic, timeout=5)  # Wait for the service to become available
                # Use setattr to dynamically create a service proxy
                setattr(self, f"{key}_service", rospy.ServiceProxy(topic, srv_type, persistent=True))
                # Print success message indicating the service is connected
                print(f"Successfully connected to {key} service at {topic}.")
            except rospy.ROSException as e:
                # Print error message if the service connection fails
                print(f"Failed to connect to {key} service at {topic}: {str(e)}")

    def init_publishers(self):
        self.manual_control_publisher = rospy.Publisher('/mavros/manual_control/send', ManualControl, queue_size=10)

    def init_subscribers(self):
        rospy.Subscriber('/mavros/state', State, self.state_callback)

    def init_vars_geofence(self):
        self.geo_tests = None 
        self.throttle_to_switch = None 
        self.sent_geo = False 
        self.fuzz_done = False 


    def kill_message(self):
        ack = self.send_cmd(False,185,1,1,0,0,0,0,0,0)
        return ack.success
    
    def kill_cleanup(self):
        ack = self.send_cmd(False,185,1,0,0,0,0,0,0,0)
        return ack.success
    

    def reset_fuzz_done_flag(self):
        self.fuzz_done = False 
        return 
        
    def reset_geo_flag(self):
        self.sent_geo = False
        return 

    def sub_geo_breach(self):
        topic_exists = rospy.search_param('/mavros/statustext/recv')
        rospy.Subscriber('/mavros/statustext/recv', StatusText, self.geofence_breach_callback)
        return 

    def state_callback(self, data):
        pass  # Implement as needed
    
    def cleanup(self):
        #force auto.land, and reset throttle to 0 
        print('[ros_interface] setting AUTO.LAND')
        self._send_command(command_type = "set_mode", args={'custom_mode': 'AUTO.LAND'},timing=1)
        return 

    def send_geo_commands(self,command_dict):
        print('calling send geo command',command_dict)
        geo_callback_dict = {}
        try:
            for command_type, args in command_dict.items():
                #immediately set geofence action
                if command_type == "set_param":
                    self._send_command(command_type,args,timing=5)
                #otherwise, signal to callback to wait for geofence event
                else:
                    geo_callback_dict[command_type] = args
        except:
            pass
        print('adding to geo tests',geo_callback_dict)
        self.geo_tests = geo_callback_dict
        print('added',self.geo_tests)
        return 

    def send_command(self,command_dict,timing):
        for command_type, args in command_dict.items():
            self._send_command(command_type,args,timing)
        #signal to waiting thread to redo timing if needed 
        if self.adjust_timer_event:
            self.adjust_timer_event.set()
        return 

    def toggle_geofence(self,value):
        value = ParamValue(0,value)
        # Create the command dictionary for setting the parameter
        command_dict = {
            'set_param': {
                'param_id': 'GF_MAX_HOR_DIST',
                'value': value
            }
        }
        command_type = 'set_param'
        args = command_dict[command_type]
        self._send_command(command_type,args,timing=1)
        return 

    def _send_command(self, command_type,args,timing=1):
            '''
            examples of bandwith testing with different timing intervals based on state
            '''
            
            if timing == 1:
                time_ = random.uniform(.1,.5) #this is default 
            elif timing == 2:
                time_ = random.uniform(.5,1.6)
            elif timing == 3:
                time_ = random.uniform(1.6,3.6)
            elif timing == 5:
                time_=.3 
            """ Processes a dictionary of commands and dispatches them to the appropriate services. """
            results = {}
            print('Sending commands - Command type - ', command_type, ' Args - ', args)
            if command_type == 'set_throttle':
                self.update_curr_throttle(args['throttle_value'])
                rospy.loginfo(f"Throttle updated to {args['throttle_value']}.")
            elif command_type == 'set_mode' and args['custom_mode'] == 'KILL_SWITCH':
                ack = self.kill_message()
            else:
                #sleep 
                self.time_in= time_
                time.sleep(time_)
                service = getattr(self, f"{command_type}_service", None)
                print('Service - ', service)
                # Dynamically unpack arguments based on the command type
            try:
                response = service(**args)
                print('[ros_interface] MAVROS response', response)
                rospy.loginfo(f"Command command_type: {command_type}, args: {args} executed successfully.")
            except rospy.ServiceException as e:
                    print(f"Service call failed: {e}")
            except Exception as e:
                print(f"Unexpected error during service call: {e}")


    def get_curr_throttle(self):
        with self.throttle_lock:
            return self.throttle_value 

    def update_curr_throttle(self,throttle):
        with self.throttle_lock:
            self.throttle_value = throttle

    def manual_control_sender(self):
        #set frequency for rospy 
        rate = rospy.Rate(100) 
        manual_control_msg = ManualControl()
        while self.running:
            throttle = self.get_curr_throttle()
            manual_control_msg.z = throttle if throttle else 0 
            self.manual_control_publisher.publish(manual_control_msg)
            rate.sleep()

    def get_current_pose(self, timeout=.2):
        """
        grab local position from '/mavros/local_position/pose'.
        """
      
        try:
            pose_msg = rospy.wait_for_message('/mavros/local_position/pose', PoseStamped, timeout=timeout)
            return pose_msg.pose
        except rospy.ROSException:
            rospy.logwarn("Timeout while waiting for local position message.")
            return None
        
    def geofence_breach_callback(self,data):
        if "maximum" in data.text.lower() and not self.sent_geo:
            print('[ros_interface] geofence boundary exceeded, executing tests...')
            self.send_command(self.geo_tests,timing=1)
            self.sent_geo = True
            self.geo_tests = None 
            self.fuzz_done = True 
            #signal to waiting thread to redo timing if needed 
            if self.adjust_timer_event:
                self.adjust_timer_event.set()

    def shutdown(self):
        print('[ros_interface] signaling shutdown')
        rospy.signal_shutdown("Done")
        return 
    
    def reset_attributes(self):

        rospy.init_node("Fuzz_Tester")

        #initialization 
        self.init_services()
        self.init_publishers()
        self.init_subscribers()
        self.init_vars_geofence()
        self.running = False 
        print('[ros_interface] attributes reset')
