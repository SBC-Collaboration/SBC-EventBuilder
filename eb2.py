import RPi.GPIO as GPIO
import time

SimOut  = [11, 13, 15]
InPins  = [18, 36, 40]
OutPins = [16, 32, 38]
State_Com = 12         # Physical button to indicate start for camera RPis
State_Com_LED = 35
Trig_0 = 22            # Physical button to send stop signal (interrupt)
Trig_0_LED = 37
# trig_latch_out = 29
trig_latch = 31

def setup():
    GPIO.setmode(GPIO.BOARD) # use Physical GPIO Numbering
    GPIO.setup(InPins, GPIO.IN)
    GPIO.setup(OutPins, GPIO.OUT)
    GPIO.output(OutPins, GPIO.LOW)
    GPIO.setup(SimOut, GPIO.OUT)
    GPIO.output(SimOut, GPIO.LOW)
    GPIO.setup(State_Com_LED, GPIO.OUT)
    GPIO.setup(State_Com, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(Trig_0_LED, GPIO.OUT)
    GPIO.setup(Trig_0, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(trig_latch, GPIO.IN)
    # GPIO.setup(trig_latch_out, GPIO.OUT)
    # GPIO.output(trig_latch_out, GPIO.HIGH)

def event_start():
    while True:
        if (GPIO.input(State_Com)==GPIO.LOW): # Wait for State_Com button press
            GPIO.output(State_Com_LED, GPIO.HIGH)
            print('State_Com = True')
            GPIO.output(11, GPIO.HIGH) # 'output' signals to RPis. For now, assume RPi_State == Active for all
            GPIO.output(13, GPIO.HIGH)
            GPIO.output(15, GPIO.HIGH)
            time.sleep(0.2)
            GPIO.output(State_Com_LED, GPIO.LOW)
            return False
        if (GPIO.input(Trig_0)==GPIO.LOW): # temporarily using Trig_0 button to indicate RPi_State != Active for all
            GPIO.output(Trig_0_LED, GPIO.HIGH)
            time.sleep(0.2)
            GPIO.output(Trig_0_LED, GPIO.LOW)
            return True

def fifo_signal():
    if (GPIO.input(18) == GPIO.HIGH and
        GPIO.input(36) == GPIO.HIGH and
        GPIO.input(40) == GPIO.HIGH and
        trig_reset == False): # input signals from RPis
        GPIO.output(16, GPIO.HIGH)  # send output signal to arduino once all RPi_State == Active
        GPIO.output(32, GPIO.HIGH)
        GPIO.output(38, GPIO.HIGH)
        return False
    else: # Error indicator
        for i in range(5):
            GPIO.output(38, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(38, GPIO.LOW)
            time.sleep(0.1)
        return True

def end_event():
    while True:
        Timer = time.perf_counter() - tic
        if ((GPIO.input(Trig_0)==GPIO.LOW or Timer > Max_time
            or trig_0_state) ): # and GPIO.input(trig_latch)==GPIO.LOW
            GPIO.output(16, GPIO.LOW)
            GPIO.output(32, GPIO.LOW)
            GPIO.output(38, GPIO.LOW)
            if (GPIO.input(Trig_0)==GPIO.LOW):
                GPIO.output(Trig_0_LED, GPIO.HIGH)
                time.sleep(0.25)
                GPIO.output(Trig_0_LED, GPIO.LOW)
            return Timer

if __name__ == '__main__':             
    print ('Program started')
    Max_time = 5
    setup()                                                                                                                                                                                                                                                                                                               
    while True:
        trig_reset = True
        trig_0_state = False
        try:
            if (GPIO.input(trig_latch) == GPIO.LOW):
                print('Trig_latch == True')
            ### Waiting for event start button or error
            trig_reset = event_start()

            ### Send FIFO signal or error
            trig_0_state = fifo_signal()
            tic = time.perf_counter() # Timer start
            
            # State_com = False (reseting GPIO pins represent RPi_State = false (previewing))
            GPIO.output(11, GPIO.LOW)
            GPIO.output(13, GPIO.LOW)
            GPIO.output(15, GPIO.LOW)

            ### Wait to end program or hit trig_0 button
            Time = end_event()

            print('Time:', Time, 'seconds')
            print('Reset')

        except KeyboardInterrupt: # Press ctrl-c to end the program.
            break
    
    print('\nProgram exiting...')
    GPIO.cleanup() # Release all GPIO
