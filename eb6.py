from tkinter.constants import DISABLED
from tkinter import ttk
import RPi.GPIO as GPIO
import tkinter as tk
from datetime import datetime
from PIL import ImageTk, Image
from pathlib import Path
import time
import os

# GPIO Setup
SimOut     = [11, 13, 15]
InPins     = [18, 36, 40]
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
######## Tab 1: event start/end etc. #########
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

    # Sets trig_reset to false and sends activate signal to all camera RPis
    def event_start(self):
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.HIGH)
        make_folder()
        return False

    # Helper for fifo_signal
    def check_in_pins(self):
        for i in range(len(InPins)):
            if GPIO.input(InPins[i]) != GPIO.HIGH:
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
            return False
        else: # Error indicator
            event_error_label = ttk.Label(self.master, text='Error: All pins are not active')
            event_error_label.grid(row=4, column=0)
            event_error_label.after(3000, event_error_label.destroy)
            return True

    # Recursively calls itself (keeps the event running) until timer exceeds max time 
    # or Man_Trigger button is pressed.
    def iterate(self):
        timer = time.perf_counter() - self.tic
        if (timer > self.max_time or self.trig_0_state):
            for i in range(len(OutPins)):
                GPIO.output(OutPins[i], GPIO.LOW)
            if self.trig_0_state:
                # Make sure to remove this LED indicator section later!
                GPIO.output(Trig_0_LED, GPIO.HIGH)
                time.sleep(0.1)
                GPIO.output(Trig_0_LED, GPIO.LOW)
            self.buttonstart.grid_forget()
            self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
            self.buttonstart.grid(row=1, column=0)
        else: 
            self.show_time.set(round(timer, 4))
            self.master.after(50, self.iterate)

    # If Man_Trigger button is pressed, sets trig_0_state to true and ends the event
    # before timer passes max time.
    def set_trig(self):
        self.trig_0_state = True

    def run_event(self):
        self.trig_reset = self.event_start()
        self.trig_0_state = self.fifo_signal()
        self.tic = time.perf_counter()

        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.LOW)
        
        self.iterate()


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

    curr_directory = './Desktop/'+today+'/'+str(index)

    os.symlink(curr_directory, 'temp')
    os.rename('temp', '/home/pi/Images')

    print('Made directory: ', curr_directory)


##############################################
########### Tab 2: Image viewer ##############
##############################################
baseheight = 500

# returns a list of all the images (png, jpg) in a directory resized to height = 500 pixels
def image_walk(directory, camera):
    image_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            filename, extension = os.path.splitext(file)
            if extension == '.png' or '.jpg':
                if filename[-1] == str(camera):
                    # rescaling images to height of 500 pixels
                    img = Image.open('images0/'+file)
                    hpercent = (baseheight / float(img.size[1]))
                    wsize = int((float(img.size[0]) * float(hpercent)))
                    img = img.resize((wsize, baseheight), Image.ANTIALIAS)
                    image = ImageTk.PhotoImage(img)
                    image_list.append(image)
    return image_list

curr_directory_path = Path(curr_directory)
image_list0 = image_walk(curr_directory_path, 0)
image_list1 = image_walk(curr_directory_path, 1)

def check():
    if len(image_list0) > 0 and len(image_list1) > 0:
        left_img = ttk.Label(tab2, image=image_list0[0])
        left_img.grid(row=0, column=0, columnspan=3)
        right_img = ttk.Label(tab2, image=image_list1[0])
        right_img.grid(row=0, column=4, columnspan=3)
        return True
    else: return False
    
images_present = check()

image_number = 0

# updates forward and backward buttons depending on which image number is being displayed 
# (the code is the same for forward and backward, just use diff parts!)
def image_buttons():
    global left_img
    global right_img
    global button_forward
    global button_back
    global image_number

    if images_present:
        left_img.grid_forget()
        left_img = ttk.Label(tab2, image=image_list0[image_number])
        right_img.grid_forget()
        right_img = ttk.Label(tab2, image=image_list1[image_number])

    # use lambda when you want to use buttons to call a function with a value
    button_forward = ttk.Button(tab2, text='>>', width=25, command=forward)
    button_back = ttk.Button(tab2, text='<<', width=25, command=back)

    left_img.grid(row=0, column=0, columnspan=3)
    right_img.grid(row=0, column=4, columnspan=3)
    button_back.grid(row=1, column=0)
    button_forward.grid(row=1, column=2)


def back(event):
    global image_number
    if image_number != 0:
        image_number -= 1
        image_buttons()
    if image_number == 0:
        button_back = ttk.Button(tab2, width=25, text='<<', state=DISABLED)
        button_back.grid(row=1, column=0)

def forward(event):
    global image_number
    if (image_number < len(image_list0) and image_number < len(image_list1)):
        image_number += 1
        image_buttons()
    else:
        button_forward = ttk.Button(tab2, width=25, text='>>', state=DISABLED)
        button_forward.grid(row=1, column=2)

def leave():
    GPIO.cleanup()
    tk_root.quit()
    exit()

# Initialize buttons 
def initialize_buttons():
    global images_present
    button_back = ttk.Button(tab2, text='<<', width=25, command=back, state=DISABLED)
    button_quit = ttk.Button(tab2, text='Quit', command=leave)
    if images_present:
        button_forward = ttk.Button(tab2, text='>>', width=25, command=lambda: forward(2)) 
    else:
        button_forward = ttk.Button(tab2, text='>>', width=25, state=DISABLED)
    button_back.grid(row=1, column=0)
    button_quit.grid(row=1, column=1)
    button_forward.grid(row=1, column=2)

initialize_buttons()

tab2.bind('<Left>', back)
tab2.bind('<Right>', forward)

#####################

event = EB(tab1, 2)
tk_root.mainloop()
