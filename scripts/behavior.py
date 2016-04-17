#!/usr/bin/python

# imports
import ast
from ErrorCode import error_code
from biobot_ros_msgs.msg import IntList
import rospy
import numbers
from std_msgs.msg import Bool, String


class Behavior():
    def __init__(self):
        # ROS init
        self.node_name = self.__class__.__name__
        rospy.init_node(self.node_name, anonymous=True)
        self.rate = rospy.Rate(10)  # 10Hz

        # ROS subscriptions
        self.subscriber = rospy.Subscriber('New_Step', String, \
                                           self.callback_new_step_abs)
        self.subscriber = rospy.Subscriber('New_Step_Rel', String, \
                                           self.callback_new_step_rel)
        self.subscriber = rospy.Subscriber('Error', String, self.callback_error)
        self.subscriber = rospy.Subscriber('Done_Module', String,self.callback_done_module)

        # ROS publishments
        self.motor_kill = rospy.Publisher('Motor_Kill', String, queue_size=10)
        self.platform_init = rospy.Publisher('Platform_Init', String, queue_size=10)
        self.pub_pulse_xy = rospy.Publisher('Pulse_XY', IntList, queue_size=10)
        self.pub_pulse_z = rospy.Publisher('Pulse_Z', IntList, queue_size=10)
        self.pub_pulse_sp = rospy.Publisher('Pulse_SP', IntList, queue_size=10)
        self.pub_pulse_mp = rospy.Publisher('Pulse_MP', IntList, queue_size=10)
        self.pub_gripper_pos = rospy.Publisher('Gripper_Pos', String, queue_size=10)
        self.step_done = rospy.Publisher('Step_Done', Bool, queue_size=10)

        #Robot position inits
        self.delta_x = 0
        self.delta_y = 0
        self.delta_z = [0, 0, 0]

        self.actual_pos_x = 0.0
        self.actual_pos_y = 0.0
        self.actual_pos_z = [0.0, 0.0, 0.0]
        self.actual_pos_sp = 0
        self.actual_pos_mp = 0

        self.new_pos_x = 0.0
        self.new_pos_y = 0.0
        self.new_pos_z = [0.0, 0.0, 0.0]

        self.pulse_x = 0
        self.pulse_y = 0
        self.pulse_z = [0, 0, 0]
        self.pulse_sp = 0
        self.pulse_mp = 0

        # Constants
        self.dist_step_xy = 0.127
        self.mode_step_xy = 0.25  # 4 pulses per step
        self.pulse_cst_xy = self.dist_step_xy * self.mode_step_xy

        self.dist_step_z = 0.04
        self.mode_step_z = 0.25  # 4 pulses per step
        self.pulse_cst_z = self.dist_step_z * self.mode_step_z

        self.pip_lim = 70000  # number of pulse limits

        # pipette tips equations variables
        self.pip_slope_tip20 = 97.61071086
        self.pip_intercept_tip20 = 63.73267033

        self.pip_slope_tip200 = 99.91081613
        self.pip_intercept_tip200 = 68.43652967

        self.pip_slope_tip1000 = 97.84199255
        self.pip_intercept_tip1000 = 328.9959479

        # Error control
        self.err_pulse_x = 0
        self.err_pulse_y = 0
        self.err_pulse_z = [0, 0, 0]

        # Others
        self.step_dict = {}
        self.done_module = []
        self.z_id = -1
        self.valid_motor_names = ['MotorControlXY', 'MotorControlZ']
        self.move_mode = 'abs'

    # Callback for new step
    def callback_new_step_abs(self, data):
        while self.done_module:
            self.rate.sleep()

        self.move_mode = 'abs'
        self.callback_new_step(data)

    # Callback for new step (special case for relative movements from web page)
    def callback_new_step_rel(self, data):
        while self.done_module:
            self.rate.sleep()

        self.move_mode = 'rel'
        self.callback_new_step(data)

    def callback_new_step(self, data):
        try:
            self.step_dict = ast.literal_eval(data.data)
            assert type(self.step_dict) == dict
            assert 'module_type' in self.step_dict
            getattr(self.__class__, "send_{}".format(self.step_dict['module_type']))(self)

        except (AssertionError, AttributeError) as e:
            print("Error : {}".format(e))
            return None

    def callback_done_module(self, data):
        try:
            self.done_module.remove(data.data)

        except ValueError:
            print("Error : wrong done_module received: {}".format(data.data))
            return None

        if not self.done_module:
            if self.step_dict['module_type'] == 'init':
                self.actual_pos_x = 0
                self.actual_pos_y = 0
                self.actual_pos_z = [0, 0, 0]
            else:
                self.actual_pos_x = self.new_pos_x
                self.actual_pos_y = self.new_pos_y
                self.actual_pos_z = self.new_pos_z[:]  # [:] important to clone the list
                self.actual_pos_sp = self.pulse_sp + self.actual_pos_sp
                self.actual_pos_mp = self.pulse_mp + self.actual_pos_mp
                self.pulse_mp = 0  # TODO
                self.pulse_sp = 0  # TODO

            print("Publishing step done")
            self.step_done.publish(True)

    # Error management
    def callback_error(self,data):
        try:
            new_error_dict = ast.literal_eval(data.data)
            assert type(new_error_dict) == dict
            assert 'error_code' in new_error_dict
            assert 'name' in new_error_dict
            getattr(self.__class__, error_code[new_error_dict['error_code']])(self,new_error_dict['name'])

        except (AssertionError, AttributeError) as e:
            print("Error : {}".format(e))
            return None

    # send platform_init
    def send_init(self):
        try:
            assert type(self.step_dict['params']) == list

        except (AssertionError):
            print('Invalid params type for init : {}'.format(self.step_dict))
            return None

        print(self.step_dict['params'])

        for axis in self.step_dict['params']:
            if axis in self.valid_motor_names:
                self.done_module.append(axis)

        if 'MotorControlZ' in self.step_dict['params']:
            print("init : {}".format('MotorControlZ'))
            self.platform_init.publish('MotorControlZ')
            self.step_dict['params'].remove('MotorControlZ')

            while 'MotorControlZ' in self.done_module:
                self.rate.sleep()

        for axis in self.step_dict['params']:
            if axis in self.valid_motor_names:
                print("init : {}".format(axis))
                self.platform_init.publish(axis)


    # Publish pipette_s topics in function of self.step_dict args
    def send_pipette_s(self):
        if self.step_dict['params']['name'] == 'pos':
            self.z_id = 0
            return self.send_pos()

        elif self.step_dict['params']['name'] == 'manip':
            vol = self.step_dict['params']['args']['vol']

            print('actual pos ', self.actual_pos_sp)
            #linear empiric relations
            if abs(vol) < 10 :
                self.pulse_sp = int(round(self.pip_slope_tip20*abs(vol) + self.pip_intercept_tip20))
            elif (abs(vol) >= 10) and (abs(vol) < 100):
                self.pulse_sp = int(round(self.pip_slope_tip200*abs(vol) + self.pip_intercept_tip200))
            elif (abs(vol) >= 100) and (abs(vol) < 800):
                self.pulse_sp = int(round(self.pip_slope_tip1000*abs(vol) + self.pip_intercept_tip1000))
            else :
                print("Error wrong volume entered")
                return None

            if vol < 0:
                self.pulse_sp *= -1
            '''
            try :
                assert (self.pulse_sp + self.actual_pos_sp) < self.pip_lim
                assert (self.pulse_sp + self.actual_pos_sp) > 0

            except AssertionError:
                print("Impossible SP manip, volume out of range: {}".format(vol))
                return None
            '''
            freq_sp = int(round(self.step_dict['params']['args']['speed'] * abs(self.pulse_sp / vol)))



            #Publish number of pulse for simple pip
            pulse_SP = IntList()
            pulse_SP.data = [freq_sp, self.pulse_sp]
            print("pulse_sp : {}".format(pulse_SP.data))
            self.pub_pulse_sp.publish(pulse_SP)
            self.done_module.append('MotorControlSP')

    # Publish pipette_mp topics in function of self.step_dict args
    def send_pipette_m(self):
        if self.step_dict['params']['name'] == 'pos':
            self.z_id = 1
            return self.send_pos()

        elif self.step_dict['params']['name'] == 'manip':
            vol = self.step_dict['params']['args']['vol']
            print("volume : {}".format(vol))
            print('actual pos ', self.actual_pos_mp)
            #linear empiric relations
            if abs(vol) < 10 :
                self.pulse_mp = int(round(self.pip_slope_tip20*abs(vol) + self.pip_intercept_tip20))
            elif (abs(vol) >= 10) and (abs(vol) < 100):
                self.pulse_mp = int(round(self.pip_slope_tip200*abs(vol) + self.pip_intercept_tip200))
            elif (abs(vol) >= 100) and (abs(vol) < 800):
                self.pulse_mp = int(round(self.pip_slope_tip1000*abs(vol) + self.pip_intercept_tip1000))
            else :
                print("Error wrong volume entered")
                return None

            if vol > 0:
                self.pulse_mp *= -1
            '''
            try :
                assert (self.pulse_mp + self.actual_pos_mp) < self.pip_lim
                assert (self.pulse_mp + self.actual_pos_mp) > 0

            except AssertionError:
                print("Impossible mp manip, volume out of range: {}".format(vol))
                return None
            '''
            freq_mp = int(round(self.step_dict['params']['args']['speed'] * abs(self.pulse_mp / vol)))



            #Publish number of pulse for simple pip
            pulse_mp = IntList()
            pulse_mp.data = [freq_mp, self.pulse_mp/4]  # TODO : Remove "/4", added for tests
            print("pulse_mp : {}".format(pulse_mp.data))
            self.pub_pulse_mp.publish(pulse_mp)
            self.done_module.append('MotorControlMP')

    # Publish gripper topics in function of self.step_dict args
    def send_gripper(self):
        if self.step_dict['params']['name'] == 'pos':
            self.z_id = 2
            return self.send_pos()

        if self.step_dict['params']['name'] == 'manip':
            gripper = str(self.step_dict['params']['args'])
            self.pub_gripper_pos.publish(gripper)
            self.done_module.append('Gripper')

        else:
            print("Error with params name in dict: {}".format(e))
            return None

    # Compute and publish the number of pulse for each axes
    def send_pos(self):

        try:
            assert isinstance(self.step_dict['params']['args']['x'], numbers.Real)
            assert isinstance(self.step_dict['params']['args']['y'], numbers.Real)
            assert isinstance(self.step_dict['params']['args']['z'], numbers.Real)

        except (AssertionError, AttributeError) as e:
            print("Error : wrong argument type {}".format(e))
            return None

        self.new_pos_x = self.step_dict['params']['args']['x']
        self.new_pos_y = self.step_dict['params']['args']['y']
        self.new_pos_z[self.z_id] = self.step_dict['params']['args']['z']

        if self.move_mode == 'abs':
            self.delta_x = self.new_pos_x - self.actual_pos_x
            self.delta_y = self.new_pos_y - self.actual_pos_y
            self.delta_z[self.z_id] = self.new_pos_z[self.z_id] - self.actual_pos_z[self.z_id]

        elif self.move_mode == 'rel':
            self.delta_x = self.new_pos_x
            self.delta_y = self.new_pos_y
            self.delta_z[self.z_id] = self.new_pos_z[self.z_id]

        else:
            print("Invalid move mode: {0}".format(self.move_mode))
            return None

        pulse_temp_x = self.delta_x / self.pulse_cst_xy
        pulse_temp_y = self.delta_y / self.pulse_cst_xy
        pulse_temp_z = self.delta_z[self.z_id] / self.pulse_cst_z

        self.pulse_x = int(round(pulse_temp_x))
        self.pulse_y = int(round(pulse_temp_y))
        self.pulse_z[self.z_id] = int(round(pulse_temp_z))

        # Adjust values if error is greater than 1 pulse
        self.err_pulse_x += pulse_temp_x - self.pulse_x
        self.err_pulse_y += pulse_temp_y - self.pulse_y
        self.err_pulse_z[self.z_id] += pulse_temp_z - self.pulse_z[self.z_id]

        if self.err_pulse_x < -1:
            self.err_pulse_x += 1
            self.pulse_x -= 1
        elif self.err_pulse_x > 1:
            self.err_pulse_x -= 1
            self.pulse_x += 1

        if self.err_pulse_y < -1:
            self.err_pulse_y += 1
            self.pulse_y -= 1
        elif self.err_pulse_y > 1 :
            self.err_pulse_y -= 1
            self.pulse_y += 1

        if self.err_pulse_z[self.z_id] < -1:
            self.err_pulse_z[self.z_id] += 1
            self.pulse_z[self.z_id] -= 1
        elif self.err_pulse_z[self.z_id] > 1:
            self.err_pulse_z[self.z_id] -= 1
            self.pulse_z[self.z_id] += 1


        if self.pulse_x != 0 or self.pulse_y != 0:
            self.done_module.append('MotorControlXY')
        if self.pulse_z[self.z_id] != 0:
            self.done_module.append('MotorControlZ')

        #Publish number of pulse for all axis
        if self.pulse_x != 0 or self.pulse_y != 0:
            pulse_XY = IntList()
            pulse_XY.data = [self.pulse_x, self.pulse_y]
            print("pulse_xy: {}".format(pulse_XY.data))
            self.pub_pulse_xy.publish(pulse_XY)

        if self.pulse_z != 0:
            while 'MotorControlXY' in self.done_module:
                self.rate.sleep()
            pulse_Z = IntList()
            pulse_Z.data = [self.z_id, self.pulse_z[self.z_id]]
            self.pub_pulse_z.publish(pulse_Z)

    def motor_kill_err(self, axis):
        self.motor_kill.publish(axis)

    def platform_init_err(self, axis):
        self.platform_init.publish(axis)

    def listener(self):
        rospy.spin()

# Main function
if __name__ == '__main__':

    try:
        bh = Behavior()
        bh.listener()

    except rospy.ROSInterruptException as e:
        print(e)

