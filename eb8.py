from tkinter.constants import CENTER, DISABLED, GROOVE, RAISED, RIDGE, SUNKEN
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
tabControl.add(tab1, text='Event run')
tabControl.add(tab2, text='Image Viewer')
tabControl.pack(expand=1, fill='both')
padx = 4
pady = 4

##############################################
############# Tab 1: event logic #############
##############################################
class EB:
    def __init__(self, master):
        self.master = master
        self.max_time_entry = ttk.Spinbox(master=self.master, width=10, from_=0, to=float('inf'), increment=1, format='%10.4f')
        self.max_time_entry.grid(row=0, column=1, padx=padx, pady=pady)

        ttk.Label(self.master, text='Maxium Event Time: ').grid(row=0, column=0)

        self.show_time = tk.StringVar()
        self.show_time.set('Event Time: ' +str(0))
        self.display_time = ttk.Label(self.master, textvariable=self.show_time, relief=SUNKEN, width=16, padding=pady)
        self.display_time.grid(row=1, column=0, padx=padx, pady=pady)

        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=2, column=0, padx=padx, pady=pady)

        self.buttonmantrig = ttk.Button(self.master, text='Man_Trigger', command=self.set_trig)
        self.buttonmantrig.grid(row=3, column=0, padx=padx, pady=pady)
        
        self.buttonquit = ttk.Button(self.master, text='Quit', command=self.leave)
        self.buttonquit.grid(row=4, column=0, padx=padx, pady=pady)

        status_label = ttk.Label(self.master, text='RPi Status', relief=RIDGE, width=12, padding=pady, justify=CENTER)
        status_label.grid(row=1, column=1, padx=4*padx, pady=pady)
        for i in range(len(InPins)):
            self.set_status_neutral(i+1)

        self.trig_0_state = False
        self.trig_reset = True
        self.event_time = 0
        
    def set_status_neutral(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='gray')
        status.grid(row=cam+1, column=1, padx=padx, pady=pady)

    def set_status_on(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='green')
        status.grid(row=cam+1, column=1, padx=padx, pady=pady)

    def set_status_off(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='red')
        status.grid(row=cam+1, column=1, padx=padx, pady=pady)

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
                self.set_status_on(i+1)
            self.buttonstart.grid_forget()
            self.buttonstart = ttk.Button(self.master, text='Start Event', state=DISABLED)
            self.buttonstart.grid(row=2, column=0, padx=padx, pady=pady)
            make_folder()
            return False
        else: # Error indicator
            event_error_label = ttk.Label(self.master, text='Error: Inactive RPi!')
            event_error_label.grid(row=5, column=0)
            event_error_label.after(3000, event_error_label.destroy)
            return True

    # Recursively calls itself (keeps the event running) until timer exceeds max time,
    # Man_Trigger button is pressed, or one of the RPi pins becomes inactive
    def iterate(self):
        self.event_time = time.perf_counter() - self.tic
        in_pins_status = not self.check_in_pins()
        if (self.event_time > self.max_time or self.trig_0_state or in_pins_status):
            self.end_event()
        else: 
            self.show_time.set('Event Time: '+str(round(self.event_time, 4)))
            self.master.after(10, self.iterate)

    # If Man_Trigger button is pressed, sets trig_0_state to true and ends the event
    # before timer passes max time.
    def set_trig(self):
        self.trig_0_state = True

    def run_event(self):
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.HIGH)
        try:
            self.max_time = float(self.max_time_entry.get())
            self.trig_reset = False
            self.trig_0_state = self.fifo_signal()
            self.tic = time.perf_counter()
            self.iterate()
        except ValueError:
            error = ttk.Label(self.master, text='Error: Invalid input!')
            error.grid(row=5, column=0, padx=padx, pady=pady)
            error.after(3000, error.destroy)
            for i in range(len(SimOut)):
                GPIO.output(SimOut[i], GPIO.LOW)

    def end_event(self):
        # Saving information
        f = open(curr_directory+'/info.txt', 'x+')
        f.write('Max Time: '+str(self.max_time)+'\n')
        f.write(self.show_time.get()+'\n')
        f.write('End condition: ')
        if self.event_time > self.max_time:
            f.write('Exceeded max time')
        if self.trig_0_state:
            f.write('Man_Trigger button pressed')
        if not self.check_in_pins():
            f.write('Camera(s) ')
            for i in len(InPins):
                if not GPIO.input(InPins[i]):
                    f.write(str(i+1)+' ')
            f.write('were inactive')
        f.close()
        print('Saved!')
        # Cleaning up
        for i in range(len(InPins)):
            if not GPIO.input(InPins[i]):
                self.set_status_off(i+1)
            else: self.set_status_neutral(i+1)
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.LOW)
        for i in range(len(OutPins)):
            GPIO.output(OutPins[i], GPIO.LOW)
        self.buttonstart.grid_forget()
        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=2, column=0, padx=padx, pady=pady)
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
    today = now.strftime('%Y') + now.strftime('%m') + now.strftime('%d')

    try:
        os.mkdir('/home/pi/camera-data/'+ today)
    except FileExistsError:
        print('Directory for today already exists')

    index = 0
    for root, dirs, files in os.walk('/home/pi/camera-data/' + today):
        for d in dirs:
            index += 1
    try:
        os.mkdir('/home/pi/camera-data/'+ today + '/' + str(index))
    except Exception as e:
        print(e)

    curr_directory = '/home/pi/camera-data/'+today+'/'+str(index)

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
        img_0.grid(row=0, column=0, columnspan=3, padx=padx, pady=pady)
        img_1 = ttk.Label(tab2, image=image_list1[0])
        img_1.grid(row=0, column=3, columnspan=3, padx=padx, pady=pady)
        img_2 = ttk.Label(tab2, image=image_list2[0])
        img_2.grid(row=0, column=6, columnspan=3, padx=padx, pady=pady)
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
button_select_dir.grid(row=1, column=4, padx=padx, pady=pady)

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

    img_0.grid(row=0, column=0, columnspan=3, padx=padx, pady=pady)
    img_1.grid(row=0, column=3, columnspan=3, padx=padx, pady=pady)
    img_2.grid(row=0, column=6, columnspan=3, padx=padx, pady=pady)
    button_back.grid(row=1, column=3, padx=padx, pady=pady)
    button_forward.grid(row=1, column=5, padx=padx, pady=pady)


def back(event=None): # place 'event=None' in parens for arrow keys
    global image_number
    global button_back
    if image_number > 0:
        image_number -= 1
        image_buttons()
    else:
        button_back = ttk.Button(tab2, text='<<', state=DISABLED)
        button_back.grid(row=1, column=3, padx=padx, pady=pady)

def forward(event=None): # place 'event=None' in parens for arrow keys
    global image_number
    global button_forward
    image_number += 1
    if (image_number < len(image_list0) and image_number < len(image_list1) and image_number < len(image_list2)):
        image_buttons()
    else:
        button_forward = ttk.Button(tab2, text='>>', state=DISABLED)
        button_forward.grid(row=1, column=5, padx=padx, pady=pady)

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
    button_back.grid(row=1, column=3, padx=padx, pady=pady)
    button_quit.grid(row=2, column=4, padx=padx, pady=pady)
    button_forward.grid(row=1, column=5, padx=padx, pady=pady)

initialize_buttons()

tk_root.bind('<Left>', back)
tk_root.bind('<Right>', forward)

#####################

event = EB(tab1)
tk_root.mainloop()
