from tkinter.constants import ACTIVE, CENTER, DISABLED, FLAT, NORMAL, S, SOLID, GROOVE, RAISED, RIDGE, SUNKEN
from tkinter import Checkbutton, filedialog as fd
from tkinter import ttk
import tkinter as tk
from typing import Text
from typing_extensions import IntVar
import RPi.GPIO as GPIO
from datetime import datetime
import time
from PIL import ImageTk, Image
from pathlib import Path
import glob
import os
import json

# export DISPLAY=localhost:10.0

# GPIO Setup
SimOut        = [11, 13, 15] # Output signal to RPis
InPins        = [18, 36, 40]
TriggerEnable = [16, 32, 38]
TriggerReset  = 22
TriggerLatch  = 29
EndEvent      = 31
Error_LED     = 38
Trig_0_LED    = 37

GPIO.setmode(GPIO.BOARD) # use Physical GPIO Numbering
GPIO.setup(InPins, GPIO.IN)
GPIO.setup(TriggerEnable, GPIO.OUT)
GPIO.output(TriggerEnable, GPIO.LOW)
GPIO.setup(SimOut, GPIO.OUT)
GPIO.output(SimOut, GPIO.LOW)
GPIO.setup(Error_LED, GPIO.OUT)
GPIO.output(Error_LED, GPIO.LOW)
GPIO.setup(Trig_0_LED, GPIO.OUT)
GPIO.output(Trig_0_LED, GPIO.LOW)
GPIO.setup(TriggerReset, GPIO.OUT)
GPIO.output(TriggerReset, GPIO.LOW)
GPIO.setup(TriggerLatch, GPIO.IN)
GPIO.setup(EndEvent, GPIO.OUT)
GPIO.output(EndEvent, GPIO.LOW)


# Tkinter setup
tk_root = tk.Tk()
tk_root.title('Event Builder')
tabControl = ttk.Notebook(tk_root)
tab1 = ttk.Frame(tabControl)
tab2 = ttk.Frame(tabControl)
tab3 = ttk.Frame(tabControl)
tab3 = ttk.Frame(tabControl)
tabControl.add(tab1, text='Run Event')
tabControl.add(tab2, text='Camera Settings')
tabControl.add(tab3, text='Image Viewer')
tabControl.add(tab3, text='Playback Images')
tabControl.pack(expand=1, fill='both')
# Global padding settings
padx = 4
pady = 4


# Initializing the dump folder as the default save path
if not os.path.isdir('/home/pi/camera-data/dump'):
    os.mkdir('/home/pi/camera-data/dump')



##############################################
############# Tab 1: event logic #############
##############################################

### The main event run screen and event run logic. To start an event, first set the 'Max Time' and
### --- 'Trigger Enable' spinner boxes. The Max Time is the maximum run time for an event. The Event Builder (EB)
### --- will send a trigger to stop all RPi and send a trigger reset signal once this time is surpassed.
### --- The Trigger Enable time is the buffer meant to allow the camera's to start up before capturing events. 
### --- The camera's will only look for triggers (motion detection at the moment) once the Trigger Enable time
### --- is passed. This screen also has indicators for the status of the RPi's meant to show which one fails
### --- in the case that one of them stops running or does not send their statecom signal. (Be careful though,
### --- if one of the cameras freezes, then it will not reset its GPIO pins and will appear to be active
### --- and running normally to the EB.) Finally, there is also a button to take single images from each of the
### --- cameras which is currently saved to the 'dump' folder. In order to exit the EB, please use the 'Quit'
### --- button which cleans up/resets all of the GPIO pins before exiting.

class EB:
    def __init__(self, master):
        self.master = master

        # Trig enable entry box
        self.trig_enable_time_entry = ttk.Spinbox(master=self.master, width=10, from_=0, to=float('inf'), increment=1, format='%10.4f')
        self.trig_enable_time_entry.insert(0, 5) # setting default trig_enable_time to 5 seconds
        self.trig_enable_time_entry.grid(row=0, column=1, padx=padx, pady=pady)
        ttk.Label(self.master, text='Trigger Enable Time: ').grid(row=0, column=0)

        # Max time entry box
        self.max_time_entry = ttk.Spinbox(master=self.master, width=10, from_=0, to=float('inf'), increment=1, format='%10.4f')
        self.max_time_entry.insert(0, 10) # setting default max_time to 10 seconds
        self.max_time_entry.grid(row=1, column=1, padx=padx, pady=pady)
        ttk.Label(self.master, text='Maxium Event Time: ').grid(row=1, column=0)

        # Showing event time 
        self.show_time = tk.StringVar()
        self.show_time.set('Event Time: ' +str(0))
        self.display_time = ttk.Label(self.master, textvariable=self.show_time, relief=SUNKEN, width=16, padding=pady)
        self.display_time.grid(row=11, column=0, padx=padx, pady=pady)

        # Initializing start, stop, quit buttons
        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=12, column=0, padx=padx, pady=pady)

        self.buttonmantrig = ttk.Button(self.master, text='Stop Event', state=DISABLED)
        self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)

        self.buttonsingletake = ttk.Button(self.master, text='Take Image', command=self.trig_enable_pulse)
        self.buttonsingletake.grid(row=14, column=0, padx=padx, pady=pady)
        
        self.buttonquit = ttk.Button(self.master, text='Quit', command=self.leave)
        self.buttonquit.grid(row=15, column=0, padx=padx, pady=pady)

        # RPi status labels (set initially to neutral when event is not running)
        status_label = ttk.Label(self.master, text='    RPi Status', relief=RIDGE, width=12, padding=pady, justify=CENTER)
        status_label.grid(row=11, column=1, padx=4*padx, pady=pady)
        for i in range(len(InPins)):
            self.set_status_neutral(i)

        # Making space for error labels -> sets tkinter window size appropriately
        # --- so that the window doess not get resized when an error occurs.
        self.error = ttk.Label(self.master, text='')
        self.error.grid(row=25, column=0, padx=padx, pady=pady)
        self.waiting_label = ttk.Label(self.master, text='')
        self.waiting_label.grid(row=26, column=0, padx=padx, pady=pady)

        self.trig_0_state = False
        self.run_state = False
        self.event_time = 0

        
    # The following three functions are for changing the status labels for the RPis
    def set_status_neutral(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='gray')
        status.grid(row=cam+12, column=1, padx=padx, pady=pady)

    def set_status_on(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='green')
        status.grid(row=cam+12, column=1, padx=padx, pady=pady)

    def set_status_off(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='red')
        status.grid(row=cam+12, column=1, padx=padx, pady=pady)


    # Returns false if all InPins are not recieving a high signal
    # Helper for fifo_signal and iterate. Also used in end_event to 
    # --- save status of pins when the event ends
    def check_in_pins(self):
        for i in range(len(InPins)):
            if not GPIO.input(InPins[i]):
                return False
        return True

    # Returns true when all in pins are inactive
    # Used in wait_for_end to make sure that all RPis are inactive
    # --- before a new event can start
    def check_all_in_pins(self):
        for i in range(len(InPins)):
            if GPIO.input(InPins[i]):
                return False
        return True


    # Following two functions enable and disable the trigger_enable pin
    # --- that is sent to all the RPis.
    # send_trig_enable is used when running an event and is called after 
    # --- trig_enable_time
    def send_trig_enable(self):
        for i in range(len(TriggerEnable)):
            GPIO.output(TriggerEnable[i], GPIO.HIGH)

    # Called when an event ends
    def disable_trig_enable(self):
        for i in range(len(TriggerEnable)):
            GPIO.output(TriggerEnable[i], GPIO.LOW)

    def trig_enable_pulse(self):
        self.send_trig_enable()
        time.sleep(0.01)
        self.disable_trig_enable()


    # Send 10 millisecond trigger_reset signal.
    # Called when starting an event, if trig_latch is enabled when trying
    # --- to start an event, after an event finishes.
    def send_trig_reset(self):
        GPIO.output(TriggerReset, GPIO.HIGH)
        time.sleep(0.01)
        GPIO.output(TriggerReset, GPIO.LOW)


    # Checks evry 10 ms (for a total of 1 second) if all RPis respond and are ready. 
    # Sets trig_0_state to false if all RPis are ready (event can keep running)
    def fifo_signal(self):
        for i in range(100):
            if (self.check_in_pins()): # input signals from RPis
                # need to add (?): send output signal to arduino once all RPi_State == Active
                for i in range(len(InPins)):
                    self.set_status_on(i)
                self.buttonstart.grid_forget()
                self.buttonstart = ttk.Button(self.master, text='Start Event', state=DISABLED)
                self.buttonstart.grid(row=12, column=0, padx=padx, pady=pady)
                self.buttonsingletake.grid_forget()
                self.buttonsingletake = ttk.Button(self.master, text='Take Image', state=DISABLED)
                self.buttonsingletake.grid(row=14, column=0, padx=padx, pady=pady)
                make_folder()
                self.trig_0_state = False
                return False
            else:
                time.sleep(0.01)
        self.trig_0_state = True
        return True


    # Recursively calls itself (keeps the event running) until timer exceeds max time,
    # Stop Event button is pressed, Trigger_latch is enabled, or one of the RPi pins becomes inactive
    def iterate(self):
        self.event_time = time.perf_counter() - self.tic
        self.latch_status = GPIO.input(TriggerLatch)
        if self.latch_status:
            print('trigger latched')
            self.save_event()
        elif (self.event_time > self.max_time or self.trig_0_state or (not self.check_in_pins())):
            GPIO.output(EndEvent, GPIO.HIGH)
            time.sleep(0.01)
            GPIO.output(EndEvent, GPIO.LOW)
            self.master.after(10, self.iterate)
        else: 
            self.show_time.set('Event Time: '+str(round(self.event_time, 4)))
            self.master.after(10, self.iterate)


    # If Man_Trigger button is pressed, sets trig_0_state to true and ends the event
    # before timer passes max time.
    def set_trig(self):
        self.trig_0_state = True


    # The function that is called by the Start Event button
    def run_event(self):
        # Reset error label
        self.error.grid_forget()
        self.error = ttk.Label(self.master, text='')
        self.error.grid(row=25, column=0, padx=padx, pady=pady)

        # Output signal sent to RPis (state_com)
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.HIGH)

        # Check if trigger latch is enabled then check that all RPis are active
        self.send_trig_reset()
        self.disable_trig_enable()
        self.latch_status = GPIO.input(TriggerLatch)

        if not self.latch_status:
            fifo_status = self.fifo_signal()
        else: fifo_status = True

        # If above checks pass: save max_time (error if invalid input), send a trig_reset signal, 
        # --- switch state of buttons to start and stop the event, start the timer, send trig enable signal
        # --- after time set in the trig_enable entry box, and call iterate to run the timer.
        if (not self.latch_status) and (not fifo_status):
            try:
                self.run_state = True
                self.max_time = float(self.max_time_entry.get())
                self.send_trig_reset()
                self.buttonmantrig.grid_forget()
                self.buttonmantrig = ttk.Button(self.master, text='Stop Event', command=self.set_trig)
                self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)
                self.tic = time.perf_counter()
                self.master.after(int(float(self.trig_enable_time_entry.get())*1000), self.send_trig_enable)
                self.iterate()
            except ValueError:
                self.error = ttk.Label(self.master, text='Error: Invalid input!')
                self.error.grid(row=25, column=0, padx=padx, pady=pady)
                for i in range(len(SimOut)):
                    GPIO.output(SimOut[i], GPIO.LOW)

        # If either of the above checks fail: reset error label, if the trig_latch is enabled, print 
        # --- error for trig_latch and send a trig_reset signal to reset latch. The user can then re-run 
        # --- the event. If one of the RPi pins is inactive, error label and update status labels of RPis
        # --- to indicate which RPi is inactive. Call cleanup to reset GPIO and RPi status.
        else:
            # Initializing soft link to the dump folder
            os.symlink('/home/pi/camera-data/dump', 'temp')
            os.rename('temp', '/home/pi/camera-data/Images')
            self.error.grid_forget()
            self.error = ttk.Label(self.master, text='')
            self.error.grid(row=25, column=0, padx=padx, pady=pady)
            if self.latch_status:
                label = self.error.cget('text')
                label = label + 'Trigger Latch enabled,\nTrigger Reset signal sent.\nPlease try again.\n'
                self.error.configure(text=label)
            if fifo_status:
                label = self.error.cget('text')
                label = label + 'Error: Inactive RPi!\n'
                self.error.configure(text=label)
            self.run_state = False
            self.cleanup() 


    # Create a text file with info on Max Time, run time, and what 
    # --- caused the event to end. Call cleanup.
    def save_event(self):
        # Saving information
        global today
        global index
        f = open(curr_directory+'/info.txt', 'x+')
        f.write('Date: '+today+'\n')
        f.write('Event: '+str(index)+'\n')
        f.write('Time Saved: '+datetime.now().strftime('%H:%M:%S')+'\n')
        f.write('Trigger Enable Time: '+str(self.trig_enable_time_entry.get())+'\n')
        f.write('Max Time: '+str(self.max_time)+'\n')
        f.write(self.show_time.get()+'\n')
        f.write('End condition: ')
        if self.event_time > self.max_time:
            f.write('Exceeded max time; ')
        if self.trig_0_state:
            f.write('Man_Trigger button pressed; ')
        if not self.check_in_pins():
            f.write('Camera(s) ')
            for i in range(len(InPins)):
                if not GPIO.input(InPins[i]):
                    f.write(str(i+1)+' ')
            f.write('were inactive; ')
        if self.latch_status:
            f.write('Trigger_latch was enabled')
        f.close()
        print('Saved!')
        self.cleanup()


    # Set the status of all the RPi pins before turning off the state_com (useful for determining 
    # --- which RPi(s) failed, if any, before some other method for ending the event). Set state_com 
    # --- to inactive. Turn off trig_enable signal. Send a trig_reset and EndEvent signal. Call wait_for_end.
    def cleanup(self):
        for i in range(len(InPins)):
            if not GPIO.input(InPins[i]):
                self.set_status_off(i)
            else: self.set_status_neutral(i)
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.LOW)
        self.disable_trig_enable()
        GPIO.output(EndEvent, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(EndEvent, GPIO.LOW)
        self.send_trig_reset()
        if self.run_state:
            self.waiting_label = ttk.Label(self.master, text='Waiting for RPis to save...')
            self.waiting_label.grid(row=26, column=0, padx=padx, pady=pady)
            self.buttonmantrig.grid_forget()
            self.buttonmantrig = ttk.Button(self.master, text='Stop Event', state=DISABLED)
            self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)
            self.buttonsingletake.grid_forget()
            self.buttonsingletake = ttk.Button(self.master, text='Take Image', state=DISABLED)
            self.buttonsingletake.grid(row=14, column=0, padx=padx, pady=pady)
        self.wait_for_end()


    # Waits until all RPis are inactive. This prevents starting a new event before 
    # --- camera's are done saving their images by keeping the start event button disabled.
    def wait_for_end(self):
        if not self.check_all_in_pins():
            self.master.after(5, self.wait_for_end)
        else: self.reset_buttons()


    # Reset the start and stop event buttons
    def reset_buttons(self):
        if self.waiting_label.winfo_exists():
            self.waiting_label.grid_forget()
        self.buttonstart.grid_forget()
        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=12, column=0, padx=padx, pady=pady)
        self.buttonmantrig.grid_forget()
        self.buttonmantrig = ttk.Button(self.master, text='Stop Event', state=DISABLED)
        self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)
        self.buttonsingletake.grid_forget()
        self.buttonsingletake = ttk.Button(self.master, text='Take Image', command=self.trig_enable_pulse)
        self.buttonsingletake.grid(row=14, column=0, padx=padx, pady=pady)


    # Clears GPIO pins and closes tkinter window
    def leave(self):
        os.symlink('/home/pi/camera-data/dump', 'temp')
        os.rename('temp', '/home/pi/camera-data/Images')
        self.cleanup()
        GPIO.cleanup()
        tk_root.quit()
        exit()


# Makes new folder for current event and sets softlink to the created folder
curr_directory = 'temp'
today = ''
index = 0
def make_folder():
    global curr_directory
    global today
    global index
    now = datetime.now()
    today = now.strftime('%Y') + now.strftime('%m') + now.strftime('%d')

    try:
        os.mkdir('/home/pi/camera-data/'+ today)
    except FileExistsError:
        print('Directory for today already exists')

    # Determine how many folders events are already in the folder to 
    # make a new folder with updated index
    index = 0
    for root, dirs, files in os.walk('/home/pi/camera-data/' + today):
        for d in dirs:
            index += 1
    try:
        os.mkdir('/home/pi/camera-data/'+ today + '/' + str(index))
    except Exception as e:
        print(e)

    # Create the symbolic (aka soft) link to the newly created folder
    curr_directory = '/home/pi/camera-data/'+ today +'/'+str(index)
    os.symlink(curr_directory, 'temp')
    os.rename('temp', '/home/pi/camera-data/Images')
    print('Made directory: ', curr_directory)


# Making the tab
event = EB(tab1)



##############################################
######### Tab 2: Camera Settings #############
##############################################

### Makes a new tab with several entry boxes to adjust the camera configX.json files. 
### Makes three config files, one for each camera. All config files have the same settings
### --- except for 'cam_name'

# Setting labels on the left side
ttk.Label(tab2, text='Exposure: ').grid(row=10, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='Buffer Length: ').grid(row=11, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='Frames After: ').grid(row=12, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='ADC Threshold: ').grid(row=13, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='Pixel Threshold: ').grid(row=14, column=0, padx=padx, pady=pady)


# The following entry boxes can have their minimum and maximum values set (using from_, to) 
# --- as well as how much to increment by and how many digits and decimal positions to show (format)

# Exposure entry box
exposure_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
exposure_spinbox.insert(0, 300)
exposure_spinbox.grid(row=10, column=1)

# Buffer Length entry box
buffer_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
buffer_spinbox.insert(0, 100)
buffer_spinbox.grid(row=11, column=1)

# Frames after entry box
fafter_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
fafter_spinbox.insert(0, 50)
fafter_spinbox.grid(row=12, column=1)

# ADC Threshold entry box
adc_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
adc_spinbox.insert(0, 10)
adc_spinbox.grid(row=13, column=1)

# Pixel Threshold entry box
pix_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
pix_spinbox.insert(0, 300)
pix_spinbox.grid(row=14, column=1)


# Makes the config dictionary for each config.json file.
# Some values are set as their defaults and cannot be changed (yet) by the event builder.
config = {}
def make_config(cam):
    config['exposure'] = int(exposure_spinbox.get())
    config["resolution"] = [1280,800]
    config["frame_sync"] = True
    config["mode"] = 11 #5
    config["buffer_len"] = int(buffer_spinbox.get())
    config["frames_after"] = int(fafter_spinbox.get())
    config["adc_threshold"] = int(adc_spinbox.get())
    config["pix_threshold"] = int(pix_spinbox.get())
    config["save_path"] = "/mnt/event-builder/Images/"
    config["config_path"]= "/mnt/event-builder/cam"+str(cam)+"-config.json"
    config["cam_name"] = 'cam'+str(cam)
    config["image_format"] = ".bmp"
    config["date_format"] = "%Y-%m-%d_%H:%M:%S"
    config["input_pins"] = {"state_com": 5,
                            "trig_en": 6,
                            "trig_latch": 13}
    config["output_pins"] = {"state": 23,
                            "trig": 24}


# Function that is called by the save button. 
# Overwrites the pre-existing config.json files or creates new ones.
def save_config():
    for i in range(3):
        config_path = '/home/pi/camera-data/cam'+str(i)+'-config.json'
        make_config(i)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    save_label = ttk.Label(tab2, text='Saved!')
    save_label.grid(row=101, column=1, padx=padx, pady=pady)
    save_label.after(1000, save_label.destroy)

save_button = ttk.Button(tab2, text='Save', command=save_config)
save_button.grid(row=100, column=1, padx=padx, pady=pady)



##############################################
########## Tab 3: Playback Images ############
##############################################

### Image viewer to view and playback images. To use, first select which cameras you
### --- want to view then click on 'Choose Directory' and choose the directory where
### --- the desired camera images are saved. If you ran an event, the default directory
### --- for the file browser will already be the most recently run event. After 
### --- choosing the directory and camera, the image viewer will load them into memory 
### --- and you can hit play to play back the images. You can also pause and manually
### --- scroll through the images using the arrow keys or onscreen buttons. 
### In order to change which camera's you want to view, you can reselect/deselect the 
### --- the cameras and then click on 'Reload' to load the appropriate images into memory.
### --- Then you can hit play and view the images the same as before.

class PI:
    def __init__(self, master):
        self.master = master
        self.img0_list = []
        self.img1_list = []
        self.img2_list = []
        self.img0_names = []
        self.img1_names = []
        self.img2_names = []
        self.img_number = 0
        self.baseheight = 300

        self.cam0 = tk.IntVar()
        self.cam1 = tk.IntVar()
        self.cam2 = tk.IntVar()

        self.img0_name = ttk.Label(tab3)
        self.img1_name = ttk.Label(tab3)
        self.img2_name = ttk.Label(tab3)
        self.img0 = ttk.Label(tab3)
        self.img1 = ttk.Label(tab3)
        self.img2 = ttk.Label(tab3)

        self.img0_name.grid(row=10, column=10, columnspan=5, padx=padx, pady=pady)
        self.img0.grid(row=11, column=10, columnspan=5, padx=padx, pady=pady)
        self.img1_name.grid(row=10, column=15, columnspan=5, padx=padx, pady=pady)
        self.img1.grid(row=11, column=15, columnspan=5, padx=padx, pady=pady)
        self.img2_name.grid(row=10, column=20, columnspan=5, padx=padx, pady=pady)
        self.img2.grid(row=11, column=20, columnspan=5, padx=padx, pady=pady)

        self.button_play = ttk.Button(tab3, text='Play', command=self.init_play, state=DISABLED)
        self.button_play.grid(row=20, column=17, padx=padx, pady=pady)

        self.button_forward = ttk.Button(tab3, text='>>', command=self.forward, state=DISABLED)
        self.button_back = ttk.Button(tab3, text='<<', command=self.back, state=DISABLED)
        self.button_back.grid(row=20, column=16, padx=padx, pady=pady)
        self.button_forward.grid(row=20, column=18, padx=padx, pady=pady)

        ttk.Label(tab3, text='Camera Select: ').grid(row=31, column=14, columnspan=2, padx=padx, pady=pady)
        Checkbutton(tab3, text='Cam0', variable=self.cam0).grid(row=31, column=16, padx=padx, pady=pady)
        Checkbutton(tab3, text='Cam1', variable=self.cam1).grid(row=31, column=17, padx=padx, pady=pady)
        Checkbutton(tab3, text='Cam2', variable=self.cam2).grid(row=31, column=18, padx=padx, pady=pady)

        self.button_reload = ttk.Button(tab3, text='Reload', command=self.reload)
        self.button_reload.grid(row=34, column=17, padx=padx, pady=pady)

        ttk.Label(tab3, text='Frequency: ').grid(row=32, column=14, padx=padx, pady=pady)
        self.frequency_spinbox = ttk.Spinbox(master=tab3, width=20, from_=0, to=10000, increment=10, format='%5.0f')
        self.frequency_spinbox.insert(0, 1)
        self.frequency_spinbox.grid(row=32, column=16, columnspan=3)

        button_select_dir = ttk.Button(tab3, text='Choose directory', command=self.load_dir)
        button_select_dir.grid(row=33, column=17, padx=padx, pady=pady)

        self.directory_label = ttk.Label(tab3, text='CurrDir: ')
        self.directory_label.grid(row=35, column=15, columnspan=5, padx=padx, pady=pady)

        self.active_state = False
        self.pause_state = False


    def load_dir(self):
        self.directory = fd.askdirectory(parent=tk_root, initialdir=curr_directory)
        self.reload()


    # Resets the names list, images list, name labels, and image labels then reloads the 
    # new names and image lists of the cameras that are selected.
    def reload(self):
        self.img0_list = []
        self.img1_list = []
        self.img2_list = []
        self.img0_names = []
        self.img1_names = []
        self.img2_names = []
        self.img0_name.config(text='')
        self.img0.config(image=None)
        self.img1_name.config(text='')
        self.img1.config(image=None)
        self.img2_name.config(text='')
        self.img2.config(image=None)
        self.img_number = 0
        if self.cam0.get():
            self.img0_list, self.img0_names = self.image_walk(self.directory, 0)
        if self.cam1.get():
            self.img1_list, self.img1_names = self.image_walk(self.directory, 1)
        if self.cam2.get():
            self.img2_list, self.img2_names = self.image_walk(self.directory, 2)
        self.directory_label.config(text='CurrDir: '+str(self.directory))
        self.button_play.config(state=NORMAL)        


    # Sorts the images in a directory and adds them to the image list and name list. The images and
    # names should have the same index since both are created by the same filename.
    def image_walk(self, directory, camera):
        image_list = []
        name_list = []
        os.chdir(directory)
        for filename in sorted(glob.glob('*.bmp')):
            if filename[3] == str(camera):
                # rescaling images to height = baseheight pixels
                img = Image.open(filename)
                hpercent = (self.baseheight / float(img.size[1]))
                wsize = int((float(img.size[0]) * float(hpercent)))
                img = img.resize((wsize, self.baseheight), Image.ANTIALIAS)
                image = ImageTk.PhotoImage(img)
                image_list.append(image)
                name_list.append(filename)
        return image_list, name_list   


    # Initial load of the name and image labels. Called by the 'play'/'pause' button so has
    # a bypass (pause_state) to skip over to the 'play' function
    def init_play(self):
        self.active_state = True
        if not self.pause_state:
            self.img_number = 0
            if self.cam0.get():
                self.img0_name = ttk.Label(tab3, text=str(self.img0_names[self.img_number]))
                self.img0 = ttk.Label(tab3, image=self.img0_list[self.img_number])
                self.img0_name.grid(row=10, column=10, columnspan=5, padx=padx, pady=pady)
                self.img0.grid(row=11, column=10, columnspan=5, padx=padx, pady=pady)
            if self.cam1.get():
                self.img1_name = ttk.Label(tab3, text=str(self.img1_names[self.img_number]))
                self.img1 = ttk.Label(tab3, image=self.img1_list[self.img_number])
                self.img1_name.grid(row=10, column=15, columnspan=5, padx=padx, pady=pady)
                self.img1.grid(row=11, column=15, columnspan=5, padx=padx, pady=pady)
            if self.cam2.get():
                self.img2_name = ttk.Label(tab3, text=str(self.img2_names[self.img_number]))
                self.img2 = ttk.Label(tab3, image=self.img2_list[self.img_number])
                self.img2_name.grid(row=10, column=20, columnspan=5, padx=padx, pady=pady)
                self.img2.grid(row=11, column=20, columnspan=5, padx=padx, pady=pady)
            self.button_play.config(text='Pause', command=self.pause)
            self.img_number += 1
            tab3.after(int(self.frequency_spinbox.get()), self.play)
        else: 
            self.button_play.config(text='Pause', command=self.pause)
            self.pause_state = False
            self.active_state = True
            self.play()


    def find_max(self):
        max_len = len(self.img0_list)
        if max_len < len(self.img1_list):
            max_len = len(self.img1_list)
        if max_len < len(self.img2_list):
            max_len = len(self.img2_list)
        return max_len


    # Recursively updates calls scroll which updates the images and updates the image number.
    # The rate at which the images are refreshed is determined by the time (in milliseconds) 
    # put in the 'Frequency' spinnerbox.
    def play(self):
        if self.img_number < self.find_max() and self.active_state and not self.pause_state:
            self.scroll()
            self.img_number += 1
            tab3.after(int(self.frequency_spinbox.get()), self.play)      
        else:
            self.button_play.config(text='Play', command=self.init_play)


    def scroll(self):
        if self.img_number < len(self.img0_list):
            self.img0_name.config(text=str(self.img0_names[self.img_number]))
            self.img0.config(image=self.img0_list[self.img_number])
        if self.img_number < len(self.img1_list):
            self.img1_name.config(text=str(self.img1_names[self.img_number]))
            self.img1.config(image=self.img1_list[self.img_number])
        if self.img_number < len(self.img2_list):
            self.img2_name.config(text=str(self.img2_names[self.img_number]))
            self.img2.config(image=self.img2_list[self.img_number])


    def pause(self, event=None):
        self.active_state = False
        self.pause_state = True
        self.button_forward.config(state=NORMAL)
        self.button_back.config(state=NORMAL)


    def forward(self, event=None):
        if (self.img_number+2 == self.find_max()):
            self.img_number += 1
            self.scroll()
            self.button_forward.config(state=DISABLED)
        elif (self.img_number+1 < self.find_max()):
            self.button_back.config(state=NORMAL)
            self.img_number += 1
            self.scroll()
        else:
            self.button_forward.config(state=DISABLED)


    def back(self, event=None):
        if self.img_number == 1:
            self.img_number -= 1
            self.scroll()
            self.button_back.config(state=DISABLED)
        elif self.img_number > 0:
            self.button_forward.config(state=NORMAL)
            self.img_number -= 1
            self.scroll()
        else:
            self.button_back.config(state=DISABLED)


image_viewer = PI(tab3)


tk_root.bind('<Left>', image_viewer.back)
tk_root.bind('<Right>', image_viewer.forward)
tk_root.bind('<space>', image_viewer.init_play)

##############################################
##############################################

tk_root.mainloop()