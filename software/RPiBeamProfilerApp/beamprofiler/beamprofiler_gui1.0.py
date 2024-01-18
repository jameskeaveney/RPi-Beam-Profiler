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

""" 
Raspberry Pi Beam Profiler

Run this program with 'sudo python beamprofiler_x.x.x.py' (where 'x' is the version number of this file) from a terminal window

Version 1.0 
January 2018, JK 

"""
import matplotlib

matplotlib.use("WxAgg")
import matplotlib.pyplot as plt

plt.ioff()

# from matplotlib import rc
# rc('text', usetex=False)
# rc('font',**{'family':'serif'})

import csv
import os
import pickle
import sys
import time

import numpy as np

# camera
import picamera
import picamera.array as camarray

# gpio
import RPi.GPIO as GPIO

# GUI
import wx
from matplotlib import cm
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar
from mpl_toolkits.axes_grid.anchored_artists import AnchoredText

GPIO.setmode(GPIO.BCM)

import libs.colormaps as cm_new  # the matplotlib 2.0 colourmaps aren't available on RPi yet...
from libs.blurb import about_message, fullpath
from libs.camera_control import MyCamera
from libs.durhamcolours import *

# local modules
from libs.stepper_control import StepMotorControl

# fitting
from scipy.optimize import curve_fit

# use relative file paths
bp_dir = os.path.dirname(__file__)


class CameraSettings(wx.Dialog):
    """
    Dialog box that appears when Camera Settings button is pressed with
    options to control image exposure settings
    """

    def __init__(self, parent, id, title):
        self.parent = parent

        # default exposure settings
        self.ExpTime = float(parent.camera.shutter_speed / 1e3)
        self.Col = DialogOptions.Col
        self.ExpAuto = DialogOptions.ExpAuto
        self.ROIxminval = DialogOptions.ROIxminval
        self.ROIxmaxval = DialogOptions.ROIxmaxval
        self.ROIyminval = DialogOptions.ROIyminval
        self.ROIymaxval = DialogOptions.ROIymaxval

        ##init UI
        wx.Dialog.__init__(self, parent, id, title, size=(350, 700))
        self.initUI()

        # init plot
        self.nBins = 64
        (self.line,) = self.ax_hist.plot(
            np.linspace(0, 1023, self.nBins), np.zeros(self.nBins), color=DialogOptions.linecol, lw=2
        )
        self.HistPanel.draw()

    def initUI(self):
        """Generate the UI for the dialog box"""
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add((-1, 20), 0, wx.EXPAND)

        # Exposure mode (auto/manual)
        ExpAutoCtrl = wx.CheckBox(self, label="Auto Exposure Time")
        self.Bind(wx.EVT_CHECKBOX, self.OnExpAutoCtrl, ExpAutoCtrl)
        ExpAutoCtrl.SetValue(self.ExpAuto)
        ExpAutoCtrl.SetToolTip(
            wx.ToolTip(
                "Automatically adjust exposure \
				time based on spot-metering. Ignores set value of exposure time "
            )
        )
        ET = wx.BoxSizer(wx.HORIZONTAL)
        ET.Add((20, -1), 1, wx.EXPAND)
        ET.Add(ExpAutoCtrl, 0, wx.EXPAND)
        ET.Add((20, -1), 1, wx.EXPAND)
        vbox.Add(ET, 0, wx.EXPAND)

        # Exposure time
        ExpTimeLabel = wx.StaticText(self, label="Exposure Time (ms):")
        self.ExpCtrl = wx.TextCtrl(self, value=str(self.ExpTime), size=(120, -1), style=wx.TE_PROCESS_ENTER)
        self.Bind(wx.EVT_TEXT_ENTER, self.OnExpCtrl, self.ExpCtrl)
        ET = wx.BoxSizer(wx.HORIZONTAL)
        ET.Add((20, -1), 0, wx.EXPAND)
        ET.Add(ExpTimeLabel, 0, wx.EXPAND)
        ET.Add((10, -1), 1, wx.EXPAND)
        ET.Add(self.ExpCtrl, 0, wx.EXPAND)
        ET.Add((20, -1), 0, wx.EXPAND)
        vbox.Add(ET, 0, wx.EXPAND)

        vbox.Add((-1, 20), 0, wx.EXPAND)

        # Color/Interpolation selection
        ColChoices = ["Red", "Green", "Blue", "Interpolated"]
        ColLabel = wx.StaticText(self, label="Color")
        self.ColCtrl = wx.ComboBox(self, value=self.Col, choices=ColChoices, style=wx.CB_READONLY, size=(120, -1))
        self.Bind(wx.EVT_COMBOBOX, self.OnColCtrl, self.ColCtrl)
        Colbox = wx.BoxSizer(wx.HORIZONTAL)
        Colbox.Add((20, -1), 0, wx.EXPAND)
        Colbox.Add(ColLabel, 0, wx.EXPAND)
        Colbox.Add((10, -1), 1, wx.EXPAND)
        Colbox.Add(self.ColCtrl, 0, wx.EXPAND)
        Colbox.Add((20, -1), 0, wx.EXPAND)
        vbox.Add(Colbox, 0, wx.EXPAND)

        # Region-of-Interest select
        ROILabel = wx.StaticText(self, label="Region of Interest (fraction of image)")
        self.ROIxmin = wx.TextCtrl(self, value=str(self.ROIxminval), size=(60, -1))
        self.ROIxmax = wx.TextCtrl(self, value=str(self.ROIxmaxval), size=(60, -1))
        self.ROIymin = wx.TextCtrl(self, value=str(self.ROIyminval), size=(60, -1))
        self.ROIymax = wx.TextCtrl(self, value=str(self.ROIymaxval), size=(60, -1))
        ROIUseZoom = wx.Button(self, label="Use Graph Zoom")
        self.Bind(wx.EVT_TEXT, self.OnROIxmin, self.ROIxmin)
        self.Bind(wx.EVT_TEXT, self.OnROIxmax, self.ROIxmax)
        self.Bind(wx.EVT_TEXT, self.OnROIymin, self.ROIymin)
        self.Bind(wx.EVT_TEXT, self.OnROIymax, self.ROIymax)
        self.Bind(wx.EVT_BUTTON, self.OnROIUseZoom, ROIUseZoom)

        ROIReset = wx.Button(self, label="Reset to full CMOS area")
        self.Bind(wx.EVT_BUTTON, self.OnROIReset, ROIReset)

        vbox.Add((-1, 20), 0, wx.EXPAND)
        vbox.Add(ROILabel, 0, wx.ALIGN_LEFT | wx.LEFT, border=20)
        vbox.Add((-1, 10), 0, wx.EXPAND)

        ROIXsizer = wx.BoxSizer(wx.HORIZONTAL)
        ROIXsizer.Add(wx.StaticText(self, label="X min:", size=(80, -1)), 0, wx.EXPAND)
        ROIXsizer.Add(self.ROIxmin, 0, wx.EXPAND)
        ROIXsizer.Add((10, -1), 0, wx.EXPAND)
        ROIXsizer.Add(wx.StaticText(self, label="X max:", size=(80, -1)), 0, wx.EXPAND)
        ROIXsizer.Add(self.ROIxmax, 0, wx.EXPAND)

        ROIYsizer = wx.BoxSizer(wx.HORIZONTAL)
        ROIYsizer.Add(wx.StaticText(self, label="Y min:", size=(80, -1)), 0, wx.EXPAND)
        ROIYsizer.Add(self.ROIymin, 0, wx.EXPAND)
        ROIYsizer.Add((10, -1), 0, wx.EXPAND)
        ROIYsizer.Add(wx.StaticText(self, label="Y max:", size=(80, -1)), 0, wx.EXPAND)
        ROIYsizer.Add(self.ROIymax, 0, wx.EXPAND)

        vbox.Add(ROIXsizer, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        vbox.Add(ROIYsizer, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        vbox.Add((-1, 10), 0, wx.EXPAND)
        vbox.Add(ROIUseZoom, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        vbox.Add((-1, 10), 0, wx.EXPAND)
        vbox.Add(ROIReset, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)

        # Histogram of pixel values
        self.histfig = plt.figure(2, (4, 3), 80, facecolor=(230.0 / 255, 230.0 / 255, 230.0 / 255))
        self.histfig.subplots_adjust(left=0.2, bottom=0.14)
        self.ax_hist = self.histfig.add_subplot(111)
        self.ax_hist.autoscale(False)
        self.ax_hist.set_xlim(0, 1024)
        self.ax_hist.set_ylim(0, 1)
        self.ax_hist.set_xlabel("Pixel Value")
        self.ax_hist.set_ylabel("No. pixels (relative)")
        self.ax_hist.set_yticklabels([])
        self.HistPanel = FigureCanvasWxAgg(self, wx.ID_ANY, self.histfig)
        vbox.Add((-1, 20), 1, wx.EXPAND)
        vbox.Add(self.HistPanel, 0, wx.EXPAND)

        # Generate histogram button
        HistBtn = wx.Button(self, label="Create Histogram")
        self.Bind(wx.EVT_BUTTON, self.OnGenHist, HistBtn)
        vbox.Add(HistBtn, 0, wx.ALIGN_CENTER_HORIZONTAL)

        # Apply button
        ApplyBtn = wx.Button(self, label="Apply Settings")
        self.Bind(wx.EVT_BUTTON, self.OnApply, ApplyBtn)
        vbox.Add((-1, 20), 0, wx.EXPAND)
        vbox.Add(ApplyBtn, 0, wx.ALIGN_CENTER)

        # Button bar - ok and cancel (standard buttons)
        btnBar = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add((-1, 20), 0, wx.EXPAND)
        vbox.Add(btnBar, 0, wx.ALIGN_CENTER)
        vbox.Add((-1, 20), 0, wx.EXPAND)
        self.SetSizer(vbox)

    # functions that execute when events are triggered
    def OnExpCtrl(self, event):
        """When exposure controls are used"""
        try:
            self.ExpTime = float(event.GetString())
        except ValueError:
            pass
        print(self.ExpTime)
        self.parent.camera.shutter_speed = int(self.ExpTime * 1e3)
        exp_time = float(self.parent.camera.shutter_speed) / 1e3
        print(exp_time)
        self.ExpCtrl.ChangeValue(str(round(exp_time, 3)))

    def OnExpAutoCtrl(self, event):
        """When auto-exposure tickbox is clicked"""
        self.ExpAuto = bool(event.Checked())
        if self.ExpAuto:
            self.parent.camera.auto_exp = "auto"
            # update value shown in exposure control box
            exp_time = float(self.parent.camera.shutter_speed) / 1e3
            self.ExpCtrl.ChangeValue(str(round(exp_time, 3)))
        else:
            self.parent.camera.auto_exp = "off"

    def OnColCtrl(self, event):
        """When colour drop-down box is selected"""
        self.Col = self.ColCtrl.GetValue()
        self.parent.camera.col = self.Col

    def OnApply(self, event):
        """When 'Apply' button is clicked"""
        if self.ExpAuto:
            self.parent.camera.auto_exp = "auto"
            # update value shown in exposure control box
            exp_time = float(self.parent.camera.shutter_speed) / 1e3
            time.sleep(0.05)
            self.ExpCtrl.ChangeValue(str(round(exp_time, 3)))

        # Update dialog options
        DialogOptions.ExpAuto = self.ExpAuto
        DialogOptions.Col = self.Col
        DialogOptions.ROIxminval = self.ROIxminval
        DialogOptions.ROIxmaxval = self.ROIxmaxval
        DialogOptions.ROIyminval = self.ROIyminval
        DialogOptions.ROIymaxval = self.ROIymaxval

        self.parent.camera.roi = [self.ROIxminval, self.ROIxmaxval, self.ROIyminval, self.ROIymaxval]

        try:
            self.parent.camera.shutter_speed = int(round(float(self.ExpCtrl.GetValue()) * 1e3, 2))
        except ValueError:
            print(" Shutter speed set incorrectly!! ")

        self.parent.camera.capture_image()
        self.parent.update_main_imshow()

    def OnGenHist(self, event):
        """When generate histogram button is clicked"""
        hdata, bins = np.histogram(self.parent.camera.image, bins=self.nBins, range=(0, 1023))
        self.line.set_ydata(hdata.astype(np.float64) / hdata.max())
        self.HistPanel.draw()

    def OnROIUseZoom(self, event):
        """When region-of-interest controls are used"""
        # alias
        imgplot = self.parent.ax_im
        xlims = imgplot.get_xlim()
        ylims = imgplot.get_ylim()

        # change UI numbers
        self.ROIxmin.ChangeValue(str(round(xlims[0], 3)))
        self.ROIxmax.ChangeValue(str(round(xlims[1], 3)))
        self.ROIymin.ChangeValue(str(round(ylims[1], 3)))
        self.ROIymax.ChangeValue(str(round(ylims[0], 3)))

        self.ROIxminval = xlims[0]
        self.ROIxmaxval = xlims[1]
        self.ROIyminval = ylims[1]
        self.ROIymaxval = ylims[0]

        self.setCrop()

    def OnROIReset(self, event):
        """When ROI reset button is clicked"""

        # alias
        imgplot = self.parent.ax_im

        # set roi to full sensor range
        roi = [0.0, 3.67, 0.0, 2.74]

        self.ROIxmin.ChangeValue(str(round(roi[0], 3)))
        self.ROIxmax.ChangeValue(str(round(roi[1], 3)))
        self.ROIymin.ChangeValue(str(round(roi[2], 3)))
        self.ROIymax.ChangeValue(str(round(roi[3], 3)))

        self.ROIxminval = roi[0]
        self.ROIxmaxval = roi[1]
        self.ROIyminval = roi[2]
        self.ROIymaxval = roi[3]

        self.setCrop()

    def OnROIxmin(self, event):
        """When ROI xmin is changed"""
        try:
            self.ROIxminval = float(event.GetString())
        except ValueError:
            pass
        self.setCrop()

    def OnROIxmax(self, event):
        """When ROI xmax is changed"""
        try:
            self.ROIxmaxval = float(event.GetString())
        except ValueError:
            pass
        self.setCrop()

    def OnROIymin(self, event):
        """When ROI ymin is changed"""
        try:
            self.ROIyminval = float(event.GetString())
        except ValueError:
            pass
        self.setCrop()

    def OnROIymax(self, event):
        """When ROI ymax is changed"""
        try:
            self.ROIymaxval = float(event.GetString())
        except ValueError:
            pass
        self.setCrop()

    def setCrop(self):
        """Update camera crop settings - common method for all ROI controls"""
        cam = self.parent.camera
        if self.ROIxminval < 0:
            self.ROIxminval = 0
        if self.ROIyminval < 0:
            self.ROIyminval = 0
        if self.ROIxmaxval > cam.ccd_xsize:
            self.ROIxmaxval = cam.ccd_xsize
        if self.ROIymaxval > cam.ccd_ysize:
            self.ROIymaxval = cam.ccd_ysize
        # cam.crop = (self.ROIxminval/cam.ccd_xsize,
        # 			self.ROIyminval/cam.ccd_ysize,
        # 			(self.ROIxmaxval-self.ROIxminval)/cam.ccd_xsize,
        # 			(self.ROIymaxval-self.ROIyminval)/cam.ccd_ysize)
        cam.roi = [self.ROIxminval, self.ROIxmaxval, self.ROIyminval, self.ROIymaxval]


class DialogDefaults:
    """Dummy class for holding default (and subsequently edited) values for the dialog boxes"""

    # Image
    ExpAuto = True
    ExpTime = "20.0"
    Col = "Red"
    linecol = d_purple
    ROIxminval = 0.0
    ROIxmaxval = 3.67
    ROIyminval = 0.0
    ROIymaxval = 2.74  # full-range of the sensor
    crop = (ROIxminval, ROIxmaxval - ROIxminval, ROIyminval, ROIymaxval - ROIyminval)

    # Scan - all dimensions in mm
    set_pos = 12.5
    scan_start_pos = 0.0
    scan_stop_pos = 25.0
    step_size = 0.15

    # save each image
    SaveEachImage = False


# Instantiate the defaults
DialogOptions = DialogDefaults()


class ScanSettings(wx.Dialog):
    """
    Dialog box for controlling the scan settings,
    including manual positioning of the stage
    """

    def __init__(self, parent, id, title):
        self.parent = parent
        wx.Dialog.__init__(self, parent, id, title, size=(400, 500), pos=(0, 0))

        # defaults
        self.set_pos = DialogOptions.set_pos
        self.scan_start_pos = DialogOptions.scan_start_pos
        self.scan_stop_pos = DialogOptions.scan_stop_pos
        self.step_size = DialogOptions.step_size

        self.initUI()

    def initUI(self):
        """Create dialog box UI elements and layout"""
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add((-1, 10), 0, wx.EXPAND)
        vbox.Add(wx.StaticText(self, label="Position Control"), 0, wx.ALIGN_LEFT | wx.LEFT, border=20)
        vbox.Add((-1, 10), 0, wx.EXPAND)

        # Button to re-calibrate zero
        CalibrateButton = wx.Button(self, label="Re-calibrate zero position", size=(200, -1))
        self.Bind(wx.EVT_BUTTON, self.OnCalibrate, CalibrateButton)
        vbox.Add(CalibrateButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        vbox.Add((-1, 5), 0, wx.EXPAND)

        # Static text (not editable by user) to show current translation position
        PositionText = wx.StaticText(self, label="Current Position (mm):")
        self.CurrentPosValue = wx.TextCtrl(
            self,
            value=str(round(self.parent.Stepper.get_position(), 3)),
            style=wx.TE_READONLY | wx.TE_RIGHT,
            size=(80, -1),
        )
        CurPosSizer = wx.BoxSizer(wx.HORIZONTAL)
        CurPosSizer.Add(PositionText, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        CurPosSizer.Add((20, -1), 1, wx.EXPAND)
        CurPosSizer.Add(self.CurrentPosValue, 0, wx.EXPAND | wx.RIGHT, border=50)
        vbox.Add(CurPosSizer, 0, wx.EXPAND)
        vbox.Add((-1, 5), 0, wx.EXPAND)

        # Editable text to set desired translation position
        SetPosText = wx.StaticText(self, label="Set Position (mm)")
        SetPosValue = wx.TextCtrl(self, value=str(round(self.set_pos, 3)), style=wx.TE_RIGHT, size=(80, -1))
        self.Bind(wx.EVT_TEXT, self.OnSetPos, SetPosValue)
        SetPosSizer = wx.BoxSizer(wx.HORIZONTAL)
        SetPosSizer.Add(SetPosText, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        SetPosSizer.Add((20, -1), 1, wx.EXPAND)
        SetPosSizer.Add(SetPosValue, 0, wx.EXPAND | wx.RIGHT, border=50)
        vbox.Add((-1, 5), 0, wx.EXPAND)
        vbox.Add(SetPosSizer, 0, wx.EXPAND)

        # Button to move translation stage to set position
        SetPosButton = wx.Button(self, label="Move to Set Position", size=(200, -1))
        self.Bind(wx.EVT_BUTTON, self.OnSetPosButton, SetPosButton)
        vbox.Add(SetPosButton, 0, wx.LEFT, border=40)

        # Tick box to auto-save each image in a scan
        SaveEachButton = wx.CheckBox(self, label="Save each image?")
        SaveEachButton.SetValue(DialogOptions.SaveEachImage)
        self.Bind(wx.EVT_CHECKBOX, self.OnSaveEachImage, SaveEachButton)

        vbox.Add((-1, 40), 0, wx.EXPAND)

        vbox.Add(wx.StaticText(self, label="Scan Control"), 0, wx.ALIGN_LEFT | wx.LEFT, border=20)
        vbox.Add((-1, 10), 0, wx.EXPAND)
        ScanStartText = wx.StaticText(self, label="Start Position (mm)")
        ScanStartValue = wx.TextCtrl(self, value=str(round(self.scan_start_pos, 3)), style=wx.TE_RIGHT, size=(80, -1))
        self.Bind(wx.EVT_TEXT, self.OnScanStartPos, ScanStartValue)
        ScanStartSizer = wx.BoxSizer(wx.HORIZONTAL)
        ScanStartSizer.Add(ScanStartText, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        ScanStartSizer.Add((20, -1), 1, wx.EXPAND)
        ScanStartSizer.Add(ScanStartValue, 0, wx.EXPAND | wx.RIGHT, border=50)
        vbox.Add(ScanStartSizer, 0, wx.EXPAND)
        vbox.Add((-1, 5), 0, wx.EXPAND)

        ScanStopText = wx.StaticText(self, label="Stop Position")
        ScanStopValue = wx.TextCtrl(self, value=str(round(self.scan_stop_pos, 3)), style=wx.TE_RIGHT, size=(80, -1))
        self.Bind(wx.EVT_TEXT, self.OnScanStopPos, ScanStopValue)
        ScanStopSizer = wx.BoxSizer(wx.HORIZONTAL)
        ScanStopSizer.Add(ScanStopText, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        ScanStopSizer.Add((20, -1), 1, wx.EXPAND)
        ScanStopSizer.Add(ScanStopValue, 0, wx.EXPAND | wx.RIGHT, border=50)
        vbox.Add(ScanStopSizer, 0, wx.EXPAND)
        vbox.Add((-1, 5), 0, wx.EXPAND)

        StepSizeText = wx.StaticText(self, label="Step Size")
        StepSizeValue = wx.TextCtrl(self, value=str(self.step_size), style=wx.TE_RIGHT, size=(80, -1))
        self.Bind(wx.EVT_TEXT, self.OnStepSize, StepSizeValue)
        StepSizeSizer = wx.BoxSizer(wx.HORIZONTAL)
        StepSizeSizer.Add(StepSizeText, 0, wx.ALIGN_LEFT | wx.LEFT, border=40)
        StepSizeSizer.Add((20, -1), 1, wx.EXPAND)
        StepSizeSizer.Add(StepSizeValue, 0, wx.EXPAND | wx.RIGHT, border=50)
        vbox.Add(StepSizeSizer, 0, wx.EXPAND)
        vbox.Add((-1, 5), 0, wx.EXPAND)

        vbox.Add((-1, 30), 0, wx.EXPAND)
        vbox.Add(SaveEachButton, 0, wx.LEFT | wx.RIGHT, border=40)
        vbox.Add((-1, 5), 0, wx.EXPAND)

        # button bar - ok and cancel (standard buttons)
        btnBar = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        vbox.Add((-1, 20), 1, wx.EXPAND)
        vbox.Add(btnBar, 0, wx.ALIGN_CENTER)
        vbox.Add((-1, 20), 0, wx.EXPAND)
        self.SetSizer(vbox)

    # functions that execute on events
    def OnSetPos(self, event):
        try:
            self.set_pos = float(event.GetString())
        except ValueError:
            pass

    def OnSetPosButton(self, event):
        self.parent.Stepper.set_position(self.set_pos)
        self.CurrentPosValue.SetValue(str(round(self.parent.Stepper.get_position(), 3)))

    def OnCalibrate(self, event):
        pass
        self.parent.Stepper.calibrate()
        self.CurrentPosValue.SetValue(str(round(self.parent.Stepper.get_position(), 3)))

    def OnScanStartPos(self, event):
        try:
            self.scan_start_pos = float(event.GetString())
        except ValueError:
            pass

    def OnScanStopPos(self, event):
        try:
            self.scan_stop_pos = float(event.GetString())
        except ValueError:
            pass

    def OnStepSize(self, event):
        try:
            self.step_size = float(event.GetString())
        except ValueError:
            pass

    def OnSaveEachImage(self, event):
        self.parent.SaveEachImage = bool(event.Checked())
        DialogOptions.SaveEachImage = self.parent.SaveEachImage

    def get_values(self):
        return self.set_pos, self.scan_start_pos, self.scan_stop_pos, self.step_size


class MainWin(wx.Frame):
    """Class that contains the main frame of the application"""

    def __init__(self, parent, title):
        wx.Frame.__init__(self, None, title=title, size=(1200, 900))

        self.SaveEachImage = False

        ## initialise camera
        self.camera = MyCamera()

        # if the window is closed, exit
        self.Bind(wx.EVT_CLOSE, self.OnExit)

        # main panel for adding everything to
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(230, 230, 230))

        ##  Statusbar at the bottom of the window
        # self.CreateStatusBar() - not used in the end, but could add live plot coordinates, tooltips or something similar

        # Plot panel - canvas and toolbar
        self.fig = plt.figure(1, (4.5 / 2, 3.0 / 2), 80, facecolor=(230.0 / 255, 230.0 / 255, 230.0 / 255))
        self.fig.subplots_adjust(left=0.08, bottom=0.07, right=0.97, top=0.97, wspace=0.11, hspace=0.15)
        self.ax_im = plt.subplot2grid((12, 6), (0, 0), rowspan=6, colspan=5)
        self.axX = plt.subplot2grid((12, 6), (6, 0), colspan=5, sharex=self.ax_im)
        self.axY = plt.subplot2grid((12, 6), (0, 5), rowspan=6, sharey=self.ax_im)
        self.axXwidth = plt.subplot2grid((12, 6), (8, 0), rowspan=2, colspan=6)
        self.axYwidth = plt.subplot2grid((12, 6), (10, 0), rowspan=2, colspan=6, sharex=self.axXwidth)

        # Axis labels
        self.axX.set_xlabel("CCD x (mm)")
        self.ax_im.set_ylabel("CCD y (mm)")
        self.axYwidth.set_xlabel("Translation stage position (mm)")
        self.axXwidth.set_ylabel(r"Wx ($\mu$m)")
        self.axYwidth.set_ylabel(r"Wy ($\mu$m)")
        # Turn off unneeded labels
        plt.setp(self.ax_im.get_xticklabels(), visible=False)
        plt.setp(self.axY.get_yticklabels(), visible=False)
        plt.setp(self.axXwidth.get_xticklabels(), visible=False)

        ## Create initial dummy image to be updated with camera data later.
        ## Take x and y partial sums and add these to the plot too
        CM = cm_new.inferno  # cm.PuOr_r #gist_heat #afmhot # binary_r
        im_array = np.zeros((300, 400))
        self.im_obj = self.ax_im.imshow(
            im_array, cmap=CM, aspect="auto", extent=self.camera.extent, interpolation="none", vmin=0, vmax=1023
        )  # 10-bit raw
        self.xfitdata = [[], []]
        self.yfitdata = [[], []]
        (self.xslice,) = self.axX.plot(
            np.linspace(0, 3.67, 400), im_array.sum(axis=0), "o", color=d_purple, ms=4, mec=d_purple, mfc="w"
        )
        (self.yslice,) = self.axY.plot(
            im_array.sum(axis=1), np.linspace(0, 2.74, 300), "o", color=d_purple, ms=4, mec=d_purple, mfc="w"
        )
        (self.xfit,) = self.axX.plot(np.linspace(0, 3.67, 400), np.zeros(400), "k--", lw=2)
        (self.yfit,) = self.axY.plot(np.zeros(300), np.linspace(0, 2.74, 300), "k--", lw=2)
        self.axX.set_xlim(0, 3.67)
        self.axY.set_ylim(0, 2.74)

        # Add dummy data to the width plots to be updated later (data and fit lines)
        self.xposdata = []
        self.xwidthdata = []
        self.yposdata = []
        self.ywidthdata = []
        self.xwidtherr = []
        self.ywidtherr = []

        self.xfitparams = [1, 1, 1]
        self.xfiterrs = [0, 0, 0]
        self.yfitparams = [1, 1, 1]
        self.yfiterrs = [0, 0, 0]

        (self.xwfit,) = self.axXwidth.plot([0], [0], "k-", lw=2)
        (self.ywfit,) = self.axYwidth.plot([0], [0], "k-", lw=2)

        self.xwline, self.xwcaplines, self.xwbarlines = self.axXwidth.errorbar(
            [-1],
            [0],
            yerr=[0.1],
            linestyle="None",
            ms=5,
            marker="o",
            mec=d_purple,
            mfc="w",
            mew=2,
            color="k",
            lw=1.5,
            capsize=0,
        )
        self.ywline, self.ywcaplines, self.ywbarlines = self.axYwidth.errorbar(
            [-1],
            [0],
            yerr=[0.1],
            linestyle="None",
            ms=5,
            marker="o",
            mec=d_purple,
            mfc="w",
            mew=2,
            color="k",
            lw=1.5,
            capsize=0,
        )

        self.axXwidth.set_xlim(0, 25)
        self.axYwidth.set_xlim(0, 25)

        self.canvas = FigureCanvasWxAgg(panel, wx.ID_ANY, self.fig)
        self.toolbar = Toolbar(self.canvas)  # matplotlib toolbar (pan, zoom, save etc)

        # Plot text
        self.imagefitparams = [0, 0, 0, 0]
        self.xfit_text = self.fig.text(
            0.85,
            0.48,
            r"$w_x =$ " + str(round(self.imagefitparams[0], 1)) + r" $\pm$ " + str(round(self.imagefitparams[1], 1)),
        )
        self.yfit_text = self.fig.text(
            0.85,
            0.45,
            r"$w_y =$ " + str(round(self.imagefitparams[1], 1)) + r" $\pm$ " + str(round(self.imagefitparams[2], 1)),
        )

        self.im_min = self.fig.text(0.2, 0.4, "Min pixel value:" + str(int(self.camera.image.min())))
        self.im_max = self.fig.text(0.5, 0.4, "Max pixel value:" + str(int(self.camera.image.max())))

        # Plot panel sizer:
        plotpanel = wx.BoxSizer(wx.VERTICAL)
        plotpanel.Add(self.canvas, 1, wx.LEFT | wx.RIGHT | wx.GROW, border=0)
        plotpanel.Add(self.toolbar, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, border=0)

        # Standard button vertical size
        btnsize = 30

        ## Live View
        ImageSettingsLabel = wx.StaticText(panel, label="Image Setup", style=wx.ALIGN_LEFT)
        font = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        ImageSettingsLabel.SetFont(font)

        self.LiveViewActive = False
        self.LiveViewButton = wx.ToggleButton(panel, label="Live View (off)", size=(180, 30))
        self.Bind(wx.EVT_TOGGLEBUTTON, lambda event: self.OnToggleLiveView(event, self.camera), self.LiveViewButton)
        # LiveViewRateText = wx.StaticText(panel,label="Update Delay")
        # LiveViewRateSlider = wx.Slider(panel, -1, 0, 0, 100, size=(120, -1))

        LV_sizer = wx.BoxSizer(wx.VERTICAL)
        LV_sizer.Add((-1, 10), 0, wx.EXPAND)
        LV_sizer.Add(ImageSettingsLabel, 0, wx.ALIGN_LEFT | wx.LEFT, border=30)
        LV_sizer.Add((-1, 10), 0, wx.EXPAND)
        LV_sizer.Add(
            wx.StaticLine(panel, -1, size=(250, 1)), 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, border=30
        )
        LV_sizer.Add((-1, 10), 0, wx.EXPAND)
        LV_sizer.Add(self.LiveViewButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)
        # LV_sizer.Add(LiveViewRateH,1,wx.EXPAND)

        ## Camera settings
        CS_sizer = wx.BoxSizer(wx.VERTICAL)
        CamSet = wx.Button(panel, label="Camera settings", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnCamSet, CamSet)
        CS_sizer.Add(CamSet, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)

        ## Single acquisition
        ACQ_sizer = wx.BoxSizer(wx.VERTICAL)
        AcquisitionButton = wx.Button(panel, label="Analyse Single Image", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnAcqSet, AcquisitionButton)
        ACQ_sizer.Add(AcquisitionButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)
        ACQ_sizer.Add((-1, 10), 0, wx.EXPAND)
        DarkFrame = wx.Button(panel, label="Capture Dark Frame", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnGetDarkFrame, DarkFrame)
        ACQ_sizer.Add(DarkFrame, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)

        ## Scan settings
        Scan_sizer = wx.BoxSizer(wx.VERTICAL)
        ScanSettingsLabel = wx.StaticText(panel, label="Scan Setup", style=wx.ALIGN_LEFT)
        font = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        ScanSettingsLabel.SetFont(font)
        Scan_sizer.Add(ScanSettingsLabel, 0, wx.ALIGN_LEFT | wx.LEFT, border=30)
        Scan_sizer.Add((-1, 10), 0, wx.EXPAND)
        Scan_sizer.Add(
            wx.StaticLine(panel, -1, size=(250, 1)), 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, border=30
        )
        Scan_sizer.Add((-1, 10), 0, wx.EXPAND)

        ScanSettingsButton = wx.Button(panel, label="Translation settings", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnScanSet, ScanSettingsButton)
        Scan_sizer.Add(ScanSettingsButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)
        Scan_sizer.Add((-1, 10), 0, wx.EXPAND)

        ScanStartStop = wx.BoxSizer(wx.HORIZONTAL)
        ScanStartButton = wx.Button(panel, label="Start Scan", size=(85, 30))
        self.Bind(wx.EVT_BUTTON, self.OnStartScan, ScanStartButton)
        ScanStopButton = wx.Button(panel, label="Stop Scan", size=(85, 30))
        self.Bind(wx.EVT_BUTTON, self.OnStopScan, ScanStopButton)
        ScanStartStop.Add(ScanStartButton, 0, wx.LEFT, border=0)
        ScanStartStop.Add((10, -1), 0, wx.EXPAND)
        ScanStartStop.Add(ScanStopButton, 0, wx.EXPAND)
        Scan_sizer.Add(ScanStartStop, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)

        Scan_sizer.Add((-1, 10), 0, wx.EXPAND)
        ClearDataButton = wx.Button(panel, label="Clear Previous Data", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnClearDataButton, ClearDataButton)
        Scan_sizer.Add(ClearDataButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)

        ## Post-acquisition - save fig, export data ...
        self.save_image = False

        PostAcq_sizer = wx.BoxSizer(wx.VERTICAL)
        PostAcqLabel = wx.StaticText(panel, label="Export options", style=wx.ALIGN_LEFT)
        font = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        PostAcqLabel.SetFont(font)
        PostAcq_sizer.Add(PostAcqLabel, 0, wx.ALIGN_LEFT | wx.LEFT, border=30)
        PostAcq_sizer.Add((-1, 10), 0, wx.EXPAND)
        PostAcq_sizer.Add(
            wx.StaticLine(panel, -1, size=(250, 1)), 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, border=30
        )
        PostAcq_sizer.Add((-1, 10), 0, wx.EXPAND)

        ExportDataButton = wx.Button(panel, label="Export Data as csv", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnExport, ExportDataButton)
        ExportDataButton.SetToolTip(wx.ToolTip("Export width data to csv files"))

        ExportImageButton = wx.Button(panel, label="Export Image as pkl", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnExportImage, ExportImageButton)
        ExportImageButton.SetToolTip(
            wx.ToolTip(
                "Export current image as python pickled data file. \
			This can be converted to 2d-csv data lataer. CAUTION - this takes a while to process!"
            )
        )

        SaveFigButton = wx.Button(panel, label="Save 2D figure", size=(180, 30))
        self.Bind(wx.EVT_BUTTON, self.OnSaveFig, SaveFigButton)
        SaveFigButton.SetToolTip(wx.ToolTip("This does the same as the matplotlib toolbar button"))

        PostAcq_sizer.Add(ExportDataButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)
        PostAcq_sizer.Add((-1, 10), 0, wx.EXPAND)
        PostAcq_sizer.Add(ExportImageButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)
        # PostAcq_sizer.Add((-1,10),0,wx.EXPAND)
        # PostAcq_sizer.Add(Make3DplotButton,0,wx.ALIGN_LEFT|wx.LEFT,border=60)
        PostAcq_sizer.Add((-1, 10), 0, wx.EXPAND)
        PostAcq_sizer.Add(SaveFigButton, 0, wx.ALIGN_LEFT | wx.LEFT, border=60)

        ## Logo
        jqclogo = wx.Image(os.path.join(bp_dir, "images/jqc-logo.png"), wx.BITMAP_TYPE_ANY)
        jqc_bmp = wx.StaticBitmap(panel, wx.ID_ANY, wx.BitmapFromImage(jqclogo), size=(191, -1))

        image_sizer = wx.BoxSizer(wx.HORIZONTAL)
        image_sizer.Add((10, -1), 1, wx.EXPAND)
        image_sizer.Add(jqc_bmp, 0, wx.EXPAND)
        image_sizer.Add((10, -1), 1, wx.EXPAND)

        ## Bottom Buttons / bar
        exitbutton = wx.Button(panel, wx.ID_CLOSE, size=(-1, btnsize))
        self.Bind(wx.EVT_BUTTON, self.OnExit, exitbutton)

        AboutButton = wx.Button(panel, wx.ID_ABOUT)
        self.Bind(wx.EVT_BUTTON, self.OnAbout, AboutButton)

        shutdownbutton = wx.Button(panel, wx.ID_EXIT, label="Shutdown RPi", size=(-1, btnsize))
        self.Bind(wx.EVT_BUTTON, self.OnShutdown, shutdownbutton)

        buttonbar = wx.BoxSizer(wx.HORIZONTAL)
        buttonbar.Add((20, -1), 1, wx.EXPAND)
        buttonbar.Add(AboutButton, 0, wx.RIGHT, border=20)
        buttonbar.Add(exitbutton, 0, wx.RIGHT, border=20)
        buttonbar.Add(shutdownbutton, 0, wx.RIGHT, border=20)

        ## Main sizer - do this last: place everything together and layout the entire panel
        ## two parts - left and right.
        ##		left contains only the plot
        ## 		right contains all the menus/buttons etc

        left = wx.BoxSizer(wx.VERTICAL)
        left.Add(plotpanel, 1, wx.EXPAND, border=5)

        right = wx.BoxSizer(wx.VERTICAL)
        right.Add((-1, 40), 0, wx.EXPAND)
        right.Add(image_sizer, 0, wx.EXPAND)
        right.Add((-1, 20), 0, wx.EXPAND)
        right.Add(LV_sizer, 0, wx.EXPAND)
        right.Add((-1, 10), 0, wx.EXPAND)
        right.Add(CS_sizer, 0, wx.EXPAND)
        right.Add((-1, 10), 0, wx.EXPAND)
        right.Add(ACQ_sizer, 0, wx.EXPAND)
        right.Add((-1, 60), 0, wx.EXPAND)
        right.Add(Scan_sizer, 0, wx.EXPAND)
        right.Add((-1, 60), 0, wx.EXPAND)
        right.Add(PostAcq_sizer, 0, wx.EXPAND)
        right.Add((-1, 60), 1, wx.EXPAND)
        right.Add(buttonbar, 0, wx.EXPAND)
        right.Add((-1, 10), 0, wx.EXPAND)

        finalsizer = wx.BoxSizer(wx.HORIZONTAL)
        finalsizer.Add(left, 1, wx.EXPAND)
        finalsizer.Add(wx.StaticLine(panel, -1, size=(1, -1), style=wx.LI_VERTICAL), 0, wx.EXPAND)
        finalsizer.Add(right, 0, wx.EXPAND)

        panel.SetSizer(finalsizer)
        panel.Layout()
        self.Center()

        # Initialise stepper motor
        self.Stepper = StepMotorControl(self)
        # Call stepper calibration after a small delay
        wx.FutureCall(500, self.TranslationStageCalibration)

        ## Show main window
        print("Loading main window...")
        self.Show(True)

    #
    ##
    ######################  Actions for events...	 #############################
    ##
    #
    def OnToggleLiveView(self, event, cam):
        if not self.LiveViewActive:
            cam.framerate = 30
            cam.preview_fullscreen = False
            cam.preview_window = (100, 100, 1000, 750)
            self.prev_exp_mode = cam.exposure_mode
            cam.exposure_mode = "auto"
            cam.start_preview()
            self.LiveViewActive = True
            self.LiveViewButton.SetLabel("LiveView (ON)")
        else:
            cam.stop_preview()
            cam.framerate = 1
            cam.exposure_mode = self.prev_exp_mode
            self.LiveViewActive = False
            self.LiveViewButton.SetLabel("LiveView (off)")

    def OnCamSet(self, event):
        dlg = CameraSettings(self, wx.ID_ANY, "Camera Settings")

        if dlg.ShowModal() == wx.ID_OK:
            # UPDATE DEFAULT VALUES SO THE NEXT TIME THIS IS CALLED THE NUMBERS CHANGE
            DialogOptions.ExpTime = str(dlg.ExpTime)
            DialogOptions.Col = dlg.Col
            DialogOptions.ExpAuto = dlg.ExpAuto
            DialogOptions.ROIxminval = dlg.ROIxminval
            DialogOptions.ROIxmaxval = dlg.ROIxmaxval
            DialogOptions.ROIyminval = dlg.ROIyminval
            DialogOptions.ROIymaxval = dlg.ROIymaxval
            DialogOptions.crop = (
                dlg.ROIxminval,
                dlg.ROIxmaxval - dlg.ROIxminval,
                dlg.ROIyminval,
                dlg.ROIymaxval - dlg.ROIyminval,
            )

        dlg.Destroy()

    def OnScanSet(self, event):
        dlg = ScanSettings(self, wx.ID_ANY, "Translation Scan Settings")

        if dlg.ShowModal() == wx.ID_OK:
            ## update defaults on OK
            setpos, startpos, stoppos, stepsize = dlg.get_values()
            DialogOptions.set_pos = setpos
            DialogOptions.scan_start_pos = startpos
            DialogOptions.scan_stop_pos = stoppos
            DialogOptions.step_size = stepsize

        dlg.Destroy()

    def OnClearDataButton(self, event):
        self.xposdata = []
        self.xwidthdata = []
        self.yposdata = []
        self.ywidthdata = []
        self.xwidtherr = []
        self.ywidtherr = []

        self.update_main_imshow()

    def OnAcqSet(self, event):
        print("Acquiring image...")
        self.camera.capture_image()
        print("Fitting image...")
        params = self.fit_image()
        self.update_main_imshow()

    def update_main_imshow(self):
        # create a more compact alias
        cam = self.camera

        # testing:
        # print cam.image
        # print 'All pixels zero??', cam.image.sum()

        self.im_obj.set_array(cam.image)
        self.xslice.set_data(cam.Xs, cam.imageX)
        self.yslice.set_data(cam.imageY, cam.Ys)

        self.ax_im.set_xlim(cam.roi[0], cam.roi[1])
        self.ax_im.set_ylim(cam.roi[3], cam.roi[2])

        self.axX.set_ylim(min(0, 1.1 * min(self.xslice.get_ydata())), 1.1 * max(self.xslice.get_ydata()))
        self.axY.set_xlim(min(0, 1.1 * min(self.xslice.get_ydata())), 1.1 * max(self.yslice.get_xdata()))

        # update axes limits for bottom plots
        self.axXwidth.set_xlim(DialogOptions.scan_start_pos, DialogOptions.scan_stop_pos)
        if len(self.xposdata) > 0:
            self.axXwidth.set_ylim(self.xwline.get_data()[1].min() * 0.8, self.xwline.get_data()[1].max() * 1.1)
            self.axYwidth.set_ylim(self.ywline.get_data()[1].min() * 0.8, self.ywline.get_data()[1].max() * 1.1)

        # update image fits
        self.xfit.set_data(self.xfitdata)
        self.yfit.set_data(self.yfitdata)

        # update plot text
        # self.imagefitparams #////
        self.xfit_text.set_text(
            r"$w_x =$ " + str(round(self.imagefitparams[0], 1)) + r" $\pm$ " + str(round(self.imagefitparams[1], 1))
        )
        self.yfit_text.set_text(
            r"$w_y =$ " + str(round(self.imagefitparams[2], 1)) + r" $\pm$ " + str(round(self.imagefitparams[3], 1))
        )

        self.im_min.set_text("Min pixel value:" + str(int(cam.image.min())))
        self.im_max.set_text("Max pixel value:" + str(int(cam.image.max())))

        self.canvas.draw()

    def fit_image(self):
        img = self.camera
        ## gaussian fitting routine here...

        # NOTE: img.Xs and img.Ys are taken from only the current region-of-interest
        p0 = [img.imageX.max(), img.Xs[img.imageX.argmax()], 0.1 * (img.roi[1] - img.roi[0]), 10]
        try:
            print("Initial params X:", p0)
            xpopt, xperr = curve_fit(gaussian, img.Xs, img.imageX, p0=p0)
            xpopt[2] = abs(xpopt[2])
            xerrs = np.sqrt(xperr.diagonal())
        except RuntimeError:
            print("Runtime Error (X fit) - probably caused by fitting not converging. Using initial params")
            xpopt = p0
            xperr = np.ones((len(xpopt), len(xpopt))) * p0[0]
            xerrs = np.sqrt(xperr.diagonal())
        try:
            p0 = [img.imageY.max(), img.Ys[img.imageY.argmax()], 0.1 * (img.roi[3] - img.roi[2]), 0]
            print("Initial params Y:", p0)
            ypopt, yperr = curve_fit(gaussian, img.Ys, img.imageY, p0=p0)
            ypopt[2] = abs(ypopt[2])
            yerrs = np.sqrt(yperr.diagonal())
        except RuntimeError:
            print("Runtime Error (Y fit) - probably caused by fitting not converging. Using initial params")
            ypopt = p0
            yperr = np.ones((len(xpopt), len(xpopt))) * p0[0]
            yerrs = np.sqrt(yperr.diagonal())

        # update plot data
        self.xfitdata[0] = img.Xs
        self.xfitdata[1] = gaussian(img.Xs, *xpopt)
        self.yfitdata[0] = gaussian(img.Ys, *ypopt)
        self.yfitdata[1] = img.Ys

        # update data for text strings
        self.imagefitparams = xpopt[2] * 1e3, xerrs[2] * 1e3, ypopt[2] * 1e3, yerrs[2] * 1e3

        # return widths
        return xpopt[2] * 1e3, xerrs[2] * 1e3, ypopt[2] * 1e3, yerrs[2] * 1e3  # convert to microns

    def OnStartScan(self, event):
        ######## IMPLEMENT THREADING here ? ####

        if self.SaveEachImage:
            # bring up dialog for save file names
            SaveFileDialog = wx.FileDialog(
                self, "Autosave each image", "/media", "bp_scan_images_", "Pickle files (*.pkl)|*.pkl", wx.FD_SAVE
            )

            if SaveFileDialog.ShowModal() == wx.ID_OK:
                output_filename_prefix = SaveFileDialog.GetPath()
                SaveFileDialog.Destroy()
            else:
                return

        self.scanning = True
        positions_array = np.arange(
            DialogOptions.scan_start_pos, DialogOptions.scan_stop_pos + DialogOptions.step_size, DialogOptions.step_size
        )

        # loop around positions
        i = 0
        while i < len(positions_array):
            # go to correct position
            self.Stepper.set_position(positions_array[i])
            print("Testing - position:", self.Stepper.get_position())

            # yield to allow other buttons to process
            wx.Yield()
            if not self.scanning:
                print("Quitting scan loop...")
                break

            # get image
            self.camera.capture_image()

            # save it if required
            if self.SaveEachImage:
                img_fn = output_filename_prefix[:-4] + str(i) + ".pkl"
                pickle.dump(self.camera.image, open(img_fn, "wb"))

            # yield to allow other buttons to process
            wx.Yield()
            if not self.scanning:
                print("Quitting scan loop...")
                break

            # fit image
            xw, xwerr, yw, ywerr = self.fit_image()

            # yield to allow other buttons to process
            wx.Yield()
            if not self.scanning:
                print("Quitting scan loop...")
                break

            # update fit arrays
            self.xposdata.append(self.Stepper.get_position())
            self.yposdata.append(self.Stepper.get_position())
            self.xwidthdata.append(xw)
            self.xwidtherr.append(xwerr)
            self.ywidthdata.append(yw)
            self.ywidtherr.append(ywerr)

            x = np.array(self.xposdata)
            y = np.array(self.xwidthdata)
            yerr = np.array(self.xwidtherr)

            # update fit plots - messy due to the errorbars!!
            # update data
            self.xwline.set_data(x, y)
            # find end points of errorbars
            error_positions = (x, y), (x, y), (x, y - yerr), (x, y + yerr)
            # update caplines
            # print self.xwcaplines[0]
            # for i,pos in enumerate(error_positions):
            # 	self.xwcaplines[i].set_data(pos)
            # update bars
            self.xwbarlines[0].set_segments(np.array([[x, y - yerr], [x, y + yerr]]).transpose((2, 0, 1)))

            x = np.array(self.yposdata)
            y = np.array(self.ywidthdata)
            yerr = np.array(self.ywidtherr)

            # update fit plots - messy due to the errorbars!!
            # update data
            self.ywline.set_data(x, y)
            # find end points of errorbars
            # error_positions = (x,y),(x,y),(x,y-yerr),(x,y+yerr)
            # update caplines
            # for i,pos in enumerate(error_positions):
            # 	self.ywcaplines[i].set_data(pos)
            # update bars
            self.ywbarlines[0].set_segments(np.array([[x, y - yerr], [x, y + yerr]]).transpose((2, 0, 1)))

            self.update_main_imshow()

            i += 1

        # after scan complete - if it hasn't been cancelled
        else:  ##   << else belongs to the while construct
            print("Scan completed without quitting...")

            # sort data with increasing position for fitting
            ZXY = list(zip(self.xposdata, self.xwidthdata, self.xwidtherr, self.ywidthdata, self.ywidtherr))
            ZXY = sorted(ZXY, key=lambda f: f[0])
            pos, xw, xe, yw, ye = list(zip(*ZXY))

            # fit waist function to position/width data (x and y)
            try:
                xfocus, xfocuserr = curve_fit(focussed_gaussian, pos, xw, sigma=xe)
            except:
                print("!! Caution - some issue with X width fitting !!")
                try:
                    print("Trying fitting without using errorbars...", end=" ")
                    xfocus, xfocuserr = curve_fit(focussed_gaussian, pos, xw)  # , sigma=xe)
                except:
                    print("But that didn't work either \nContinuing without fitting")
                    xfocus, xfocuserr = np.array([1, 1, 1]), np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0]])

            try:
                yfocus, yfocuserr = curve_fit(focussed_gaussian, pos, yw, sigma=ye)
            except:
                print("!! Caution - some issue with Y width fitting !!")
                try:
                    print("Trying fitting without using errorbars...", end=" ")
                    yfocus, yfocuserr = curve_fit(focussed_gaussian, pos, yw)
                except:
                    print("But that didn't work either \nContinuing without fitting")
                    yfocus, yfocuserr = np.array([1, 1, 1]), np.array([[0, 0, 0], [0, 0, 0], [0, 0, 0]])

            xfocuserr = np.sqrt(xfocuserr.diagonal())
            yfocuserr = np.sqrt(yfocuserr.diagonal())

            # update plot lines
            xx = np.linspace(DialogOptions.scan_start_pos, DialogOptions.scan_stop_pos, 400)
            self.xwfit.set_data(xx, focussed_gaussian(xx, *xfocus))
            self.ywfit.set_data(xx, focussed_gaussian(xx, *yfocus))

            # print on plot the x and y fit values
            # at = AnchoredText("Waist: "+str(round(xfocus[0],2))+"$\pm$"+str(round(xfocuserr[0],2))+" units",frameon=False,loc=0)
            # self.axXwidth.add_artist(at)

            self.canvas.draw()

            # finally, change 'scanning' back to false
            self.scanning = False

    def OnStopScan(self, event):
        self.scanning = False
        print("Scan stopping....")

    def OnExport(self, event):
        SaveFileDialog = wx.FileDialog(
            self,
            "Save Output File",
            "/media",
            "beamprofiler_output",
            "CSV files (*.csv)|*.csv",
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )

        if SaveFileDialog.ShowModal() == wx.ID_OK:
            output_filename = SaveFileDialog.GetPath()
            SaveFileDialog.Destroy()

            ## profile data
            profile_filename = output_filename  # [:-4] + ".csv"
            # check for overwrite current files
            if os.path.isfile(profile_filename):
                OverwriteDialog = wx.MessageDialog(
                    self, "Warning: file exists already! Overwrite?", "Overwrite?", wx.YES_NO | wx.NO_DEFAULT
                )

                if OverwriteDialog.ShowModal() == wx.NO:
                    OverwriteDialog.Destroy()
                    print("No save this time...")
                    return
                else:
                    OverwriteDialog.Destroy()
                    time.sleep(0.05)
            z, x, xe, y, ye = self.xposdata, self.xwidthdata, self.xwidtherr, self.ywidthdata, self.ywidtherr
            dataout = list(zip(z, x, xe, y, ye))
            dataout = sorted(dataout, key=lambda f: f[0])  # sort by position
            write_csv(dataout, profile_filename)  ## << should use numpy.writetxt instead...

            ## profile fit data
            fits_filename = output_filename[:-4] + "_profilefitparams.csv"
            with open(fits_filename, "wb") as csvfile:
                csv_writer = csv.writer(csvfile, delimiter=",")
                csv_writer.writerow(["X axis", "", "errors on line below"])
                csv_writer.writerow(["1/e2 radius (micron)", "Rayleigh range (mm)", "Position of center (mm)"])
                csv_writer.writerow(self.xfitparams)
                csv_writer.writerow(self.xfiterrs)
                csv_writer.writerow(["Y axis", "", "errors on line below"])
                csv_writer.writerow(["1/e2 radius (micron)", "Rayleigh range (mm)", "Position of center (mm)"])
                csv_writer.writerow(self.yfitparams)
                csv_writer.writerow(self.yfiterrs)

            SaveMessage = wx.MessageDialog(
                self,
                "Files created:\n\n  -- Beam profile data: "
                + profile_filename
                + "\n -- Profile fit parameters: "
                + fits_filename,
                "Files created",
                wx.OK | wx.ICON_INFORMATION,
            )
            SaveMessage.ShowModal()
            SaveMessage.Destroy()
            print("Data Save finished")

    def OnExportImage(self, event):
        """Saves the image data to a pkl file"""
        SaveFileDialog = wx.FileDialog(
            self,
            "Save Output File",
            "/media",
            "beamprofiler_output",
            "Pickle files (*.pkl)|*.pkl",
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )

        if SaveFileDialog.ShowModal() == wx.ID_OK:
            output_filename = SaveFileDialog.GetPath()
            SaveFileDialog.Destroy()

            ## profile data
            # profile_filename = output_filename + ".pkl"
            # check for overwrite current files
            # if os.path.isfile(profile_filename):
            # 	OverwriteDialog = wx.MessageDialog(self,"Warning: file exists already! Overwrite?",\
            # 		"Overwrite?",wx.YES_NO|wx.NO_DEFAULT)
            #
            # 	if OverwriteDialog.ShowModal() == wx.NO:
            # 		OverwriteDialog.Destroy()
            # 		print 'No save this time...'
            # 		return
            # 	else:
            # 		OverwriteDialog.Destroy()
            # 		time.sleep(0.05)

            im_filename = output_filename[:-4] + "_image.pkl"
            write_pkl(self.camera.image, im_filename)

            SaveMessage = wx.MessageDialog(
                self,
                "Files created:\n\n -- Current image data: "
                + im_filename
                + "\n\nThis can be read in again with xy <2d-array> = \
				cPickle.load(open(<filename>,'rb'))\n",
                "Files created",
                wx.OK | wx.ICON_INFORMATION,
            )
            SaveMessage.ShowModal()
            SaveMessage.Destroy()
            print("Image Save finished")

    def OnGetDarkFrame(self, event):
        """Get the background count level - block the laser beam first!"""
        self.camera.capture_background()

    def OnSaveFig(self, event):
        """Save figure panel as image file"""
        # widcards for file type selection
        wilds = "PDF (*.pdf)|*.pdf|" "PNG (*.png)|*.png|" "EPS (*.eps)|*.eps|" "All files (*.*)|*.*"
        exts = [".pdf", ".png", ".eps", ".pdf"]  # default to pdf
        SaveFileDialog = wx.FileDialog(
            self,
            message="Save Output File",
            defaultDir="/media",
            defaultFile="beamprofiler_figure",
            wildcard=wilds,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        SaveFileDialog.SetFilterIndex(0)

        if SaveFileDialog.ShowModal() == wx.ID_OK:
            output_filename = SaveFileDialog.GetPath()

            self.fig.savefig(output_filename + exts[SaveFileDialog.GetFilterIndex()])

        SaveFileDialog.Destroy()

    # exit button/menu item
    def OnExit(self, event):
        print("Closing application...")
        self.camera.cleanup()
        GPIO.cleanup()
        self.Destroy()
        app.ExitMainLoop()

    def OnAbout(self, event):
        caption = "About this application"

        dlg = wx.MessageDialog(self, about_message, caption, wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def OnShutdown(self, event):
        # bring up confirmation dialog box
        doshutdown = 0
        dlg = wx.MessageDialog(
            self,
            "Are you sure you want to shut down the device?",
            "Confirm Shutdown",
            wx.OK | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_INFORMATION,
        )
        if dlg.ShowModal() == wx.ID_OK:
            ## do shutdown ...
            self.camera.cleanup()
            self.Destroy()
            GPIO.cleanup()
            app.ExitMainLoop()
            doshutdown = 1
            print("Shutting down now...")
        dlg.Destroy()
        if doshutdown:
            os.system("shutdown -h now")

    # translation stage initialisation
    def TranslationStageCalibration(self):
        print("Calibrating..", end=" ")
        dlg = wx.MessageDialog(
            self, "Click OK to start translation stage position calibration", "Initial Calibration", wx.ICON_EXCLAMATION
        )

        if dlg.ShowModal():
            retVal = self.Stepper.calibrate()  # returns 1 if no error, 0 if error
        dlg.Destroy()

        if retVal:
            dlg2 = wx.MessageDialog(
                self,
                "Translation stage position calibration completed",
                "Initial Calibration Complete",
                wx.ICON_INFORMATION,
            )
            if dlg2.ShowModal():
                pass
            dlg2.Destroy()
        else:
            # error
            dlg2 = wx.MessageDialog(
                self,
                "Translation stage position calibration failed to complete - please check for hardware errors...",
                "Initial Calibration Failed",
                wx.ICON_INFORMATION,
            )
            if dlg2.ShowModal():
                pass
            dlg2.Destroy()


# functions for fitting
def gaussian(x, a, c, w, o):
    """Gaussian function, with amplitude a, centred at c, width w = 1/e^2 radius, and offset o"""
    return a * np.exp(-2 * (x - c) ** 2 / (w**2)) + o


def focussed_gaussian(z, zr, w0, c):
    """
    Expected form for the width of a gaussian beam at a position z,
    with the focal position c, Rayleigh range zr and width at the focus of w0.
    """
    w = w0 * np.sqrt(1.0 + ((z - c) / zr) ** 2)
    return w


# csv writer
def write_csv(xy, filename):
    """
    Module for writing csv data with arbitrary
    number of columns to filename.
    Takes in xy, which should be of the form [[x1,y1],[x2,y2] ...]
    this can be done by zipping arrays, e.g.
            xy = zip(x,y,z)
            where x,y and z are 1d arrays
    """

    np.savetxt(filename, xy, delimiter=",")

    # with open(filename, 'wb') as csvfile:
    # 	csv_writer = csv.writer(csvfile,delimiter=',')
    # 	for xy_line in xy:
    # 		csv_writer.writerow(xy_line)


def write_pkl(xy, filename):
    """Shortcut method for pickling data"""
    pickle.dump(xy, open(filename, "wb"))


# redirect: error messages go to a pop-up box
app = wx.App(redirect=True)
frame = MainWin(None, "Raspberry Pi Beam Profiler v1.0:Jan2018")
frame.Maximize()
app.MainLoop()
