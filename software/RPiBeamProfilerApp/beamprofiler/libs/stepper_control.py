# Copyright 2017 J. Keaveney

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import wx

import numpy as np

#gpio
import RPi.GPIO as GPIO
#GPIO.setmode(GPIO.BCM)


# GPIO pin names for connections
ENABLE_BTN = 0 
STEP_BTN = 17
DIR_BTN = 27
SWITCH_BTN = 11

class StepMotorControl():
	"""
	Control class for the stepper motor. 
	Init with whatever pins the step, direction and switch buttons are on.
	In the proper configuration the 'forward' direction means the 
	translation stage moves away from the motor.
	Forwards:  dir = 0
	Backwards: dir = 1
	Position is calibrated with the microswitch, which sets the zero position
	Lag should be 1ms (tested unloaded) which is the fastest repeatable step rate
	This gives 1 rotation in ~400 ms, which will move 1mm in ~2.5 seconds.
	"""
	##forwards: dir = 0
	def __init__(self,parent,
					step_btn=STEP_BTN,dir_btn=DIR_BTN,
					switch_btn=SWITCH_BTN,enable_btn=ENABLE_BTN,
					lag=0.001):
		""" initialise the stepper motor """
		
		self.parent = parent 
		GPIO.setmode(GPIO.BCM)
		self.step_btn = step_btn #pin 11
		self.dir_btn = dir_btn #pin13
		self.switch_btn = switch_btn #pin23
		self.enable_btn = enable_btn 
		self.lag = lag
	
		#set up pins
		GPIO.setup(self.step_btn,GPIO.OUT,initial=0)
		GPIO.setup(self.dir_btn,GPIO.OUT,initial=0)
		GPIO.setup(self.switch_btn,GPIO.IN, pull_up_down=GPIO.PUD_UP)
		GPIO.setup(self.enable_btn,GPIO.OUT,initial=1)
		
		self.step_number = 0
		## self.step_amount = 1./400 * 149.4e-6 # one step = 1/400 of revolution * 149.4 micron per rev --- original thorlabs screw
		self.step_amount = 1./400 * 500.e-6 # one step = 1/400 of revolution * 500 micron per rev --- new custom brass screw from the workshop
		
		print 'Calibration Switch position:', GPIO.input(self.switch_btn)
		
		##Addendum - nothing to do with the stepper motor! Disable the camera red LED
		GPIO.setup(5,GPIO.OUT,initial=0)
		
	def doSteps(self,n,dirn):
		""" Move n steps in the direction specified by dirn """
		GPIO.output(self.enable_btn,0) # enable
		GPIO.output(self.dir_btn,dirn)
		i=0
		while i<n:
			#print i
			GPIO.output(self.step_btn,0)
			GPIO.output(self.step_btn,1)
			time.sleep(self.lag)
			i+=1
		#count movement - backwards direction (towards the motor) corresponds to direction_pin=low:
		if dirn==1:
			dir_sign = -1
		else:
			dir_sign = 1
		self.step_number += n * dir_sign
		GPIO.output(self.enable_btn,1) # disable

	#translation stage init
	def calibrate(self):
		""" Run calibration - move backwards until microswitch is triggered. """
		#time.sleep(0.2)
		back_dirn = 1
		GPIO.output(self.dir_btn,back_dirn)
		GPIO.output(self.enable_btn,0) # enable

		#until the switch is triggered, move constantly in back_dirn direction
		i=0
		while GPIO.input(self.switch_btn):
			if i%2000==0: 
				#wx.Yield()
				print ' ...',
			GPIO.output(self.step_btn,0)
			GPIO.output(self.step_btn,1)
			time.sleep(self.lag)
			i += 1
			
			if i > (30 / self.lag): # (approx 30 seconds)
				print 'Errors....?'
				# assume something has gone wrong and return error code
				GPIO.output(self.enable_btn,1) # disable
				return False
		
		print '... Done' #after switch is triggered, reset the position counter
		self.step_number = 0
		GPIO.output(self.enable_btn,1) # disable
		
		return True
		
	def get_position(self):
		""" Get position in milimetres from the zero-position"""
		return self.step_number*self.step_amount*1e3
	
	def set_position(self,posn):
		""" Move to position specified by posn """
		print 'Moving...',
		posn_steps = int(round(1e-3 * posn / self.step_amount,0))
		steps_to_move = posn_steps - self.step_number
		print '...',steps_to_move,' steps...',
		if np.sign(steps_to_move)==1:
			dirn = 0
		else:
			dirn = 1
		self.doSteps(abs(steps_to_move),dirn)
		print '..Done'
