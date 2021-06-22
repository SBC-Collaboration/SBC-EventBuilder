from tkinter.constants import DISABLED
from tkinter import filedialog as fd
from tkinter import ttk
import RPi.GPIO as GPIO
import tkinter as tk
from datetime import datetime
from PIL import ImageTk, Image
from pathlib import Path
import time
import os
import sys

# export DISPLAY=localhost:10.0

# GPIO Setup
SimOut     = [11, 13, 15]
InPins     = [18, 36, 40] # InPins includes the trigger latch signal from the arduino!
OutPins    = [16, 32, 38]
Error_LED  = 38
Trig_0_LED = 37

GPIO.setmode(GPIO.BOARD) # use Physical GPIO Numbering
GPIO.setup(InPins, GPIO.IN)
GPIO.setup(OutPins, GPIO.OUT)
GPIO.output(OutPins, GPIO.LOW)
GPIO.setup(SimOut, GPIO.OUT)
GPIO.output(SimOut, GPIO.LOW)
GPIO.setup(Error_LED, GPIO.OUT)
GPIO.output(Error_LED, GPIO.LOW)
GPIO.setup(Trig_0_LED, GPIO.OUT)
GPIO.output(Trig_0_LED, GPIO.LOW)


# Tkinter setup
tk_root = tk.Tk()
tk_root.title('Event Builder')
tabControl = ttk.Notebook(tk_root)
tab1 = ttk.Frame(tabControl)
tab2 = ttk.Frame(tabControl)
tab2 = ttk.Frame(tabControl)
tabControl.add(tab1, text='Event run')
tabControl.add(tab2, text='Save Directory')
tabControl.add(tab2, text='Image Viewer')
tabControl.pack(expand=1, fill='both')

##############################################
############# Tab 1: event logic #############
##############################################
class EB:
    def __init__(self, master, max_time):
        self.master = master
        self.max_time = max_time

        self.show_time = tk.DoubleVar()
        self.show_time.set(0)
        self.display_time = ttk.Label(self.master, text='Event time: ', textvariable=self.show_time)
        self.display_time.grid(row=0, column=0)

        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=1, column=0)

        self.buttonmantrig = ttk.Button(self.master, text='Man_Trigger', command=self.set_trig)
        self.buttonmantrig.grid(row=2, column=0)
        
        self.buttonquit = ttk.Button(self.master, text='Quit', command=self.leave)
        self.buttonquit.grid(row=3, column=0)

        self.trig_0_state = False
        self.trig_reset = True
        self.event_time = 0

    # Sets trig_reset to false and sends activate signal to all camera RPis
    def event_start(self):
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.HIGH)
        return False

    # Helper for fifo_signal: returns false if all InPins are not recieving a high signal
    def check_in_pins(self):
        for i in range(len(InPins)):
            if not GPIO.input(InPins[i]):
                return False
        return True

    # Checks if all RPis respond and are ready. Sets trig_0_state false if all RPis 
    # are ready (event can keep running)
    def fifo_signal(self):
        if (self.check_in_pins() and not self.trig_reset): # input signals from RPis
            # send output signal to arduino once all RPi_State == Active
            for i in range(len(OutPins)):
                GPIO.output(OutPins[i], GPIO.HIGH)
            self.buttonstart.grid_forget()
            self.buttonstart = ttk.Button(self.master, text='Start Event', state=DISABLED)
            self.buttonstart.grid(row=1, column=0)
            make_folder()
            return False
        else: # Error indicator
            event_error_label = ttk.Label(self.master, text='Error: All pins are not active')
            event_error_label.grid(row=4, column=0)
            event_error_label.after(3000, event_error_label.destroy)
            return True

    # Recursively calls itself (keeps the event running) until timer exceeds max time 
    # or Man_Trigger button is pressed.
    def iterate(self):
        self.event_time = time.perf_counter() - self.tic
        in_pins_status = not self.check_in_pins()
        if (self.event_time > self.max_time or self.trig_0_state or in_pins_status):
            for i in range(len(OutPins)):
                GPIO.output(OutPins[i], GPIO.LOW)
            # if in_pins_status:
            #     for i in range(10):
            #         GPIO.output(Error_LED, GPIO.HIGH)
            #         time.sleep(0.1)
            #         GPIO.output(Error_LED, GPIO.LOW)
            #         time.sleep(0.1)
            # if not self.trig_0_state:
            #     # Make sure to remove this LED indicator section later!
            #     GPIO.output(Trig_0_LED, GPIO.HIGH)
            #     time.sleep(2)
            #     GPIO.output(Trig_0_LED, GPIO.LOW)
            self.buttonstart.grid_forget()
            self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
            self.buttonstart.grid(row=1, column=0)
            self.end_event()
        else: 
            self.show_time.set(round(self.event_time, 4))
            self.master.after(10, self.iterate)

    # If Man_Trigger button is pressed, sets trig_0_state to true and ends the event
    # before timer passes max time.
    def set_trig(self):
        self.trig_0_state = True

    def run_event(self):
        self.trig_reset = self.event_start()
        self.trig_0_state = self.fifo_signal()
        self.tic = time.perf_counter()
        self.iterate()
        
    def end_event(self):
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.LOW)
        self.trig_reset = True


    def leave(self):
        GPIO.cleanup()
        tk_root.quit()
        exit()

# Makes new folder for current event and sets softlink to the created folder
curr_directory = 'temp'
def make_folder():
    global curr_directory
    now = datetime.now()
    today = now.strftime('%d') + '_' + now.strftime('%m') + '_' + now.strftime('%Y')

    try:
        os.mkdir('./'+ today)
    except FileExistsError:
        print('Directory for today already exists')

    index = 0
    for root, dirs, files in os.walk('./' + today):
        for d in dirs:
            index += 1
    try:
        os.mkdir(today + '/' + str(index))
    except Exception as e:
        print(e)

    curr_directory = '~/camera-data/'+today+'/'+str(index)

    os.symlink(curr_directory, 'temp')
    os.rename('temp', '/home/pi/camera-data/Images')

    print('Made directory: ', curr_directory)


##############################################
########### Tab 2: Image viewer ##############
##############################################
baseheight = 200

# returns a list of all the images (png, jpg) in a directory resized to height = baseheight pixels
def image_walk(directory, camera):
    image_list = []
    os.chdir(directory)
    for root, dirs, files in os.walk(directory):
        for file in files:
            filename, extension = os.path.splitext(file)
            if extension == '.png' or '.jpg':
                if filename.endswith(str(camera)):
                    # rescaling images to height of 500 pixels
                    img = Image.open(file)
                    hpercent = (baseheight / float(img.size[1]))
                    wsize = int((float(img.size[0]) * float(hpercent)))
                    img = img.resize((wsize, baseheight), Image.ANTIALIAS)
                    image = ImageTk.PhotoImage(img)
                    image_list.append(image)
    return image_list

# Initialize image lists
image_list0 = []
image_list1 = []
image_list2 = []
img_0 = None
img_1 = None
img_2 = None

def check():
    global img_0
    global img_1
    global img_2
    if len(image_list0) > 0 and len(image_list1) > 0 and len(image_list2) > 0:
        img_0 = ttk.Label(tab2, image=image_list0[0])
        img_0.grid(row=0, column=0, columnspan=3)
        img_1 = ttk.Label(tab2, image=image_list1[0])
        img_1.grid(row=0, column=3, columnspan=3)
        img_2 = ttk.Label(tab2, image=image_list2[0])
        img_2.grid(row=0, column=6, columnspan=3)
        return True
    else: return False

images_present = check()

# Loads a new directory with images seperated into three lists based off ending character.
def load_dir():
    global image_list0
    global image_list1
    global image_list2
    global images_present
    directory = fd.askdirectory(parent=tk_root, initialdir=curr_directory)
    image_list0 = image_walk(directory, 0)
    image_list1 = image_walk(directory, 1)
    image_list2 = image_walk(directory, 2)
    images_present = check()
    image_buttons()
    back()

button_select_dir = ttk.Button(tab2, text='Choose directory', command=load_dir)
button_select_dir.grid(row=1, column=1)

image_number = 0

# updates forward and backward buttons depending on which image number is being displayed 
# (the code is the same for forward and backward, just use diff parts!)
def image_buttons():
    global img_0
    global img_1
    global img_2
    global image_number

    if images_present:
        img_0.grid_forget()
        img_0 = ttk.Label(tab2, image=image_list0[image_number])
        img_1.grid_forget()
        img_1 = ttk.Label(tab2, image=image_list1[image_number])
        img_2.grid_forget()
        img_2 = ttk.Label(tab2, image=image_list2[image_number])

    button_forward = ttk.Button(tab2, text='>>', command=forward)
    button_back = ttk.Button(tab2, text='<<', command=back)

    img_0.grid(row=0, column=0, columnspan=3)
    img_1.grid(row=0, column=3, columnspan=3)
    img_2.grid(row=0, column=6, columnspan=3)
    button_back.grid(row=1, column=0)
    button_forward.grid(row=1, column=2)


def back(event=None): # place 'event=None' in parens for arrow keys
    global image_number
    global button_back
    if image_number > 0:
        image_number -= 1
        image_buttons()
    else:
        button_back = ttk.Button(tab2, text='<<', state=DISABLED)
        button_back.grid(row=1, column=0)

def forward(event=None): # place 'event=None' in parens for arrow keys
    global image_number
    global button_forward
    image_number += 1
    if (image_number < len(image_list0) and image_number < len(image_list1) and image_number < len(image_list2)):
        image_buttons()
    else:
        button_forward = ttk.Button(tab2, text='>>', state=DISABLED)
        button_forward.grid(row=1, column=2)

def leave():
    GPIO.cleanup()
    tk_root.quit()
    exit()

# Initialize buttons 
def initialize_buttons():
    global images_present
    global button_back
    global button_forward
    button_back = ttk.Button(tab2, text='<<', command=back, state=DISABLED)
    button_quit = ttk.Button(tab2, text='Quit', command=leave)
    if images_present:
        button_forward = ttk.Button(tab2, text='>>', command=forward)
    else:
        button_forward = ttk.Button(tab2, text='>>', state=DISABLED)
    button_back.grid(row=1, column=0)
    button_quit.grid(row=2, column=1)
    button_forward.grid(row=1, column=2)

initialize_buttons()

tk_root.bind('<Left>', back)
tk_root.bind('<Right>', forward)

#####################

event = EB(tab1, 5)
tk_root.mainloop()
