# Copyright 2017/8 J. Keaveney

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np 
import time
import wx

#camera
import picamera
import picamera.array as camarray
from picamera.array import PiBayerArray

class MyCamera(picamera.PiCamera):
	""" 
	Class for interfacing with the picamera module, and getting raw (Bayer) data from the sensor
	
	The capture method uses the RAW bayer format output of the camera 
	class, formatted as a numpy 2d array for easy integration with
	matplotlib etc
	
	Settings are controlled via class variables.
	"""	
		
	def __init__(self,col='Red',\
					speed=1,ExpMode = 'auto', roi=[0.0,3.67,0.0,2.74]):
		picamera.PiCamera.__init__(self)
		
		## interpolate pixels, or use raw bayer pixels
		
		'''
		::Bayer ordering::
		bayer[ry::2, rx::2, 0] = 1 # Red
		bayer[gy::2, gx::2, 1] = 1 # Green
		bayer[Gy::2, Gx::2, 1] = 1 # Green
		bayer[by::2, bx::2, 2] = 1 # Blue	
		'''
		
		## Remove dark-frame from results
		self.bg_subtract = True
		
		## detect camera resolution / model
		if self.MAX_RESOLUTION[0] == 2592:
			self.version = 1 # OmniVision sensor
			# set minimum shutter speed
			self.min_shutter_speed = 12 # microseconds
		else:
			self.version = 2 # Sony sensor
			# detect minimum shutter speed
			self.min_shutter_speed = 9 # microseconds
		
		print 'Detected camera version: ', self.version
		
		self.Hpixels = self.MAX_RESOLUTION[0]
		self.Vpixels = self.MAX_RESOLUTION[1]
				
		self.image = np.array([0.])
		self.background = None
		
		self.col = col
		
		#actual size of ccd in mm (same for both versions)
		self.ccd_xsize = 3.67
		self.ccd_ysize = 2.74
		
		self.auto_exp = ExpMode
		self.exposure_mode = 'off'
		self.shutter_speed = int(speed*1e3)
		
		# Region-of-interest
		self.roi = roi #[xmin,xmax,ymax,ymin] in mm

		# Full extent of the sensor area (mm)
		self.extent = [0.0,3.67,0,2.74]
		
		# Turn off post-processing stuff (needed for live view?)
		self.awb_mode = 'off'
		self.awb_gains = (1,1)
		self.framerate = 5
		
		
	def capture_background(self):
		""" Capture an image into a 2d-array using current exposure settings"""
		
		if self.col == 'Interpolated':
			self.interpolate = True
		else:
			self.interpolate = False
			
		st = time.time()
		BayerArray = camarray.PiBayerArray(self)
		self.capture(BayerArray, 'jpeg', bayer=True)
		# bayer ordering
		((ry, rx), (gy, gx), (Gy, Gx), (by, bx)) = BayerArray.BAYER_OFFSETS[BayerArray._header.bayer_order]
		
		et1 = time.time() - st
		print 'elapsed time (capture):',et1
		
		if self.interpolate:
			## Use full resolution by interpolating the bayer data back to the full sensor resolution
			
			## demosaic - postprocess ccd data back to full resolution rgb array
			self.background = BayerArray.demosaic()
			et2 = time.time() - st
			print 'elapsed time (demosaic):',et2
		
			##red pixels only:
			self.background = np.asarray(self.background[:, :, 0],dtype=int)
		else:
			## Lose a factor of 2 in resolution, but without interpolating 
			## Use only 1 color of pixel in the bayer pattern - much faster than demosaic!
			
			## red pixels only:
			if self.col=='Red':
				print BayerArray.array
				self.background = np.asarray(BayerArray.array[ry::2, rx::2, 0],dtype=int)
			
			elif self.col=='Green':
				## green pixels:
				self.background = np.asarray(BayerArray.array[gy::2, gx::2, 1],dtype=int)
			
			else:
				## blue pixels:
				self.background = np.asarray(BayerArray.array[by::2, bx::2, 2],dtype=int)
			
			## green... more complicated ...
					
	def capture_image(self):
		""" Capture an image into a 2d-array using current exposure settings"""
		
		if self.col == 'Interpolated':
			self.interpolate = True
		else:
			self.interpolate = False
			
		if self.auto_exp == 'auto':
			self.shutter_speed = self.autoexpose()
		
		st = time.time()
		BayerArray = camarray.PiBayerArray(self)
		self.capture(BayerArray, 'jpeg', bayer=True)
		# bayer ordering
		((ry, rx), (gy, gx), (Gy, Gx), (by, bx)) = BayerArray.BAYER_OFFSETS[BayerArray._header.bayer_order]
		
		et1 = time.time() - st
		print 'elapsed time (capture):',et1
		
		#print BayerArray.array.shape
		#self.image = BayerArray.array ## full BGGR bayer mosaic array
		
		if self.interpolate:
			## Use full resolution by interpolating the bayer data back to the full sensor resolution
			
			##demosaic - postprocess ccd data back to full resolution rgb array
			self.image = np.asarray(BayerArray.demosaic(),dtype=int)
			et2 = time.time() - st
			print 'elapsed time (demosaic):',et2
		
			##red pixel values:
			self.image = self.image[:, :, 0]
		else:
			## Lose a factor of 2 in resolution, but without interpolating - i.e. use only 1 color of pixel
			
			# red pixels:
			## red pixels only:
			if self.col=='Red':
				print BayerArray.array
				self.image = np.asarray(BayerArray.array[ry::2, rx::2, 0],dtype=int)
			
			elif self.col=='Green':
				## green pixels:
				self.image = np.asarray(BayerArray.array[gy::2, gx::2, 1],dtype=int)
			
			else:
				## blue pixels:
				self.image = np.asarray(BayerArray.array[by::2, bx::2, 2],dtype=int)
				# dtype=int >> converts to signed integers - otherwise background subtraction can fail
		
		## apply crops for region of interest here
		h,w = self.image.shape
		self.roi_frac = [int(self.roi[0]/self.ccd_xsize),int(self.roi[1]/self.ccd_xsize),\
						1-int(self.roi[2]/self.ccd_ysize),1-int(self.roi[3]/self.ccd_ysize)]
						
		self.cropped_image = self.image[  h*self.roi_frac[3]:h*self.roi_frac[2],w*self.roi_frac[0]:w*self.roi_frac[1]]
		if self.background is not None:
			cropped_bg = self.background[h*self.roi_frac[3]:h*self.roi_frac[2],w*self.roi_frac[0]:w*self.roi_frac[1]]
		
		# remove dark frame
		if self.bg_subtract:
			if self.background is None:
				print '\t !! WARNING :: No dark frame image to subtract '
			else:
				self.image = self.image - self.background
				self.cropped_image = self.cropped_image - cropped_bg
		
		#print self.roi_frac
		#print 'Cropped shape:', cropped_image.shape
		ch,cw = self.cropped_image.shape
		
		# only fit to cropped part of the image
		self.imageX = self.cropped_image.sum(axis=0).astype(np.float)/ch
		self.imageY = self.cropped_image.sum(axis=1).astype(np.float)/cw
		
		# Approximate position - should use neareset integer to Ntimes pixel pitch
		self.Xs = np.linspace(self.roi[0],self.roi[1],cw)
		self.Ys = np.linspace(self.roi[3],self.roi[2],ch)
		
		et2 = time.time() - st
		print 'elapsed time (capture + processing):',et1
	
	def set_background(self):
		""" Use whatever the current image is as the dark frame image """
		self.background = self.image
		
	def get_image(self):
		""" Shortcut to getting the captured image array """
		self.capture_image()
		return self.image
	
	def get_cropped_image(self):
		""" Shortcut to getting the cropped image array, using the current ROI settings """
		self.capture_image()
		return self.cropped_image
		
	def cleanup(self):
		""" Cleanup the camera memory stuff - needed to prevent GPU memory leak errors """
		self.close()
		
	def autoexpose(self):
		""" 
		Custom auto-exposure routine that finds the maximum pixel value and makes sure it's below saturation 
		"""
		
		print 'Running auto-exposure:'
		
		#define 'good' range for maximum pixel value, arbitrary
		desired_range = (800,950)
		
		#check current settings
		finding_shutter_speed = True		
		while finding_shutter_speed:
			## need to add detection of min/max shutter speeds here !!
				
			print '.',
			#print self.analog_gain, self.digital_gain
			current_max = self.get_image_fast_max()
			#print 'Image max value:',current_max
			if current_max<desired_range[1] and current_max>desired_range[0]:
				finding_shutter_speed = False
			elif current_max>desired_range[1]:
				# reduce exposure time
				if self.shutter_speed == self.min_shutter_speed:
					print '\n\n','-'*50,'SHUTTER SPEED AT MINIMUM - REDUCE OPTICAL POWER','-'*50
					finding_shutter_speed = False

				self.shutter_speed = int(0.5 * self.shutter_speed * desired_range[0] / current_max)
				print 'New shutter speed:', self.shutter_speed
			elif current_max == 0:
				self.shutter_speed = int(100 * self.shutter_speed)
			else:
				# increase exposure time
				self.old_shutter_speed = self.shutter_speed
				print 'Old shutter speed', self.old_shutter_speed
				self.shutter_speed = int(self.shutter_speed * desired_range[0] / current_max * 1.1)
				if self.shutter_speed == self.old_shutter_speed:
					# catch increments that are too small
					print 'Estimated increment too small...'
					self.shutter_speed = self.shutter_speed + 19
				print 'New shutter speed', self.shutter_speed
					
		print ' Done'
		print ' Shutter speed:',
		print int(self.shutter_speed * 2.2)
		return int(self.shutter_speed * 2.2)
			
	def get_image_fast_max(self):
		""" 
		Acquire a quick image using the RGBarray method
		 - good for auto-exposure, but not proper image analysis! 
		"""
		
		#print 'Getting image...',
		st = time.time()
		self.resolution = (int(self.Hpixels/2), int(self.Vpixels/2))
		with camarray.PiRGBArray(self) as stream:
			self.capture(stream,'rgb')
			image = stream.array
		print 'Elapsed time (get_image_fast):', time.time() - st
		print '\tImage maximum value:',image[:,:,0].max()*4
		return image[:,:,0].max()*4
