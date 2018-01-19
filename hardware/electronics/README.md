These are the electronic design files for the RPi beam profiler. 

The design files use KiCAD (http://kicad-pcb.org/). The PCB designs can be uploaded in their current .kicad_pcb file format to oshpark.com for board manufacture. If gerber files are required, open the pcb file in KiCAD first and output gerber files from there.

The daughter board sits on top of the RPi GPIO pins, and includes:

> A high-current 5V voltage regulator to power the RPi
> The Pololu DRV8825 motor controller breakout board

This should be powered by a high current (> 2A) DC voltage supplied via the barrel connector (centre positive).