import RPi.GPIO as GPIO
import time
import numpy as np
import os

# initialisation
sdiPin = 22
dacClkPin = 16
dacCsPin = 18
dinPin = 11
doutPin = 7
adcClkPin = 15
adcCsPin = 13

errorPin = 
motor_switch_pin = 

GPIO.setmode(GPIO.BOARD)

# Set up a pin which can be attached to an LED to show errors
GPIO.setup(errorPin, GPIO.OUT, initial = GPIO.LOW)
# Set the data pin to the DAC as an output, starting low
GPIO.setup(sdiPin, GPIO.OUT, initial = GPIO.LOW)
# Set a pin for the DAC's clock, starting high and will be set low
# and returned high on each write to the DAC.
GPIO.setup(dacClkPin, GPIO.OUT, initial = GPIO.HIGH)
# Set a pin for the DAC's chip select. Starting high (not writing).
GPIO.setup(dacCsPin, GPIO.OUT, initial = GPIO.HIGH)
# Set the data pin to the ADC as an output, start low
GPIO.setup(dinPin, GPIO.OUT, initial = GPIO.LOW)
# Set the ADC clock pin, as for the DAC
GPIO.setup(adcClkPin, GPIO.OUT, initial = GPIO.HIGH)
# Set the ADC chip select pin, as for the DAC
GPIO.setup(adcCsPin, GPIO.OUT, initial = GPIO.HIGH)

# Set the data input pin, which will read a word from the
# ADC on each write/read operation
GPIO.setup(doutPin, GPIO.IN, pull_up_down = GPIO.PUD_UP)

# Set the motor switch pin, which will define when the motor is
# fully in or out
GPIO.setup(motor_switch_pin, GPIO.IN, pull_up_down = GPIO.PUD_UP)

# Create booleans to define when the motor is moving, and when the led is in
motor_move = False
motor_in = False

# Define a callback to tell the motor when to stop turning
def motor_callback(pin_number):
     motor_move = False
     motor_in = not motor_in

GPIO.add_event_detect(motor_switch_pin, GPIO.FALLING, callback = motor_callback)

# Define the voltage of the voltage reference chip
voltage_reference = 2.5

# Define a function to write a voltage to the DAC
def DAC(dac_channel,voltage):
     
     # Define the maximum voltage of the DAC (set to the
     # reference voltage)
     maxvoltage = voltage_reference

     # Flash the error pin twice if the voltage is out
     # of range, repeat 5 times
     if not (maxvoltage >= voltage >= 0):
          for i in range(0, 5):
               GPIO.output(errorPin, GPIO.HIGH)
               time.sleep(.5)
               GPIO.output(errorPin, GPIO.LOW)
               time.sleep(.5)
               GPIO.output(errorPin, GPIO.HIGH)
               time.sleep(.5)
               GPIO.output(errorPin, GPIO.LOW)
               time.sleep(3)

     # channel is set by the first four address bits - address is simply
     # the binary equivalent of the channel number
     address = ''
     address = '{0:04b}'.format(int( dac_channel))
    
     # reformat value to 8bit binary string
     value = '{0:08b}'.format(int( (255*(float(voltage)/float(maxvoltage))) % 256 ))
    
     # address byte preceeds value byte
     word = address + value
    
     # drop CS to low to prepare the chip to read SDI pin
     GPIO.output(dacCsPin,0)
     # put our digit on the feed line, then clock the strobe line
     for digit in word:
          GPIO.output(dacClkPin,0)
          GPIO.output(sdiPin,int(digit))
          # clocked on rising edge
          GPIO.output(dacClkPin,1)
          
     GPIO.output(dacCsPin,1)

# Create a helper function to get the 3 bit address from the
# ADC digital output
def get_address(bit_string):
     
     address_string=''
     
     for i, digit in enumerate(bit_string):
          if i>0 and i<4:  # Ignore the first leading zero
               address_string += digit

     return address_string

# Create a helper function to get the 8 bit voltage from the
# ADC digital output. Note that this changes depending on the
# range mode and coding mode - still need to add capability to
# decode two's complement word.
def get_voltage(bit_string, range_mode='1'):
     
     # Set the maximum voltage to the reference voltage (range mode 1)
     maxV = voltage_reference

     binary_voltage = ''

     # If range mode is 0, maximum voltage is twice the reference
     if range_mode == '0':
          maxV = 2 * voltage_reference
          
     for i, digit in enumerate(bit_string):
          if i>3 and i<12: # Ignore the first leading zero and 3 address bits
               binary_voltage += digit

     # Convert the binary string into an analogue voltage value
     voltage = (float(int(binary_voltage, 2))/256.)*maxV
               
     return voltage

# Create a helper function to convert the voltage across a K type thermocouple
# to a temperature
def voltage_to_temperature(voltage):
     # Set coefficients for the conversion of voltage to temperature in the
     # range -100 deg C to 100 deg C
     t_0 = -8.7935962
     v_0 = -0.34489914
     p_1 = 25.678719
     p_2 = -0.49887904
     p_3 = -0.44705222
     p_4 = -0.044869203
     q_1 = 0.00023893439
     q_2 = -0.020397750
     q_3 = -0.0018424107
     
     # If tempereture is greater than 100 deg C, the coefficients change
     # value slightly
     if voltage > 0.41:
               t_0 = 31.018976
               v_0 = 12.631386
               p_1 = 24.061949
               p_2 = 4.0158622
               p_3 = 0.26853917
               p_4 = -0.0097188544
               q_1 = 0.16995872
               q_2 = 0.011413069
               q_3 = -0.00039275155
     
     # Calculate the temperature given the voltage and the coefficients
     temperature = t_0 + ( (voltage - v_0) * (p_1 + (voltage - v_0) * (p_2 +  (voltage - v_0) * (p_3 + p_4 * (voltage - v_0) ) ) ) ) / (1 + (voltage - v_0) * (q_1 +  (voltage - v_0) * (q_2 + q_3 *  (voltage - v_0) ) ) )
    
     return temperature

# Create a function to write to (and read from) the ADC. Note that, on power-up, there
# should be two dummy conversions ADC(channel_number) where all options are set to '1'.
# Reading from these conversions will give invalid data so they should be ignored. Options
# can be set on the third conversion, and valid data read from the 4th conversion.
def ADC(adc_channel, write_mode='1', sequence='1', shadow='1', range_mode='1', coding='1'):

     # For default range mode, maximum voltage is the reference
     maxvoltage = voltage_reference

     # If range mode is changed to zero, maximum voltage is twice the reference
     if range_mode == '0':
          maxvoltage = 2 * voltage_reference

     # channel is set by the three address bits - address is simply
     # the binary equivalent of the channel number
     address = ''
     address = '{0:03b}'.format(int( adc_channel))
    
     # we need to define the control register before writing or reading
     # anything. This is 
     # |write|seq|DC|ADD2|ADD1|ADD0|PM1|PM0|shadow|DC|range|coding
     # The default values set all bits to 1 for a dummy conversion.
     # Don't care bits can be anything, so we set them to 1 for default
     # dummy conversions. We must write 16 bits, but only 12 are read, so
     # again we set the final 4 bits to 1.
     control_register = write_mode + sequence + '1' + address + '11' + shadow + '1' + range_mode + coding + '1111'

     # create a private variable to store the conversion
     digital_conversion = ''

     # drop CS to low to prepare the chip to read the DIN pin
     GPIO.output(adcCsPin,0)
     
     # Control is written to the register on falling edge. So raise the
     # clock, put a digit on the feed line and drop the clock. Conversions
     # are clocked out onto the DOUT pin on the same falling edge, but just
     # before data is clocked into the DIN pin. The first leading zero is
     # placed on the DOUT feed line right after CS is dropped, so this should
     # be read first
     for digit in control_register:

          # read the digital output
          if GPIO.input(doutPin):
               digital_conversion += '1'
          else:
               digital_conversion += '0'                
    
          # place a digit on the feed line
          GPIO.output(dinPin, int(digit))
          
          # clock the digit into the control register
          GPIO.output(adcClkPin,0)
                    
          # raise the clock again ready for the next cycle
          GPIO.output(adcClkPin,1)

     GPIO.output(adcCsPin,1)
     
     return digital_conversion

     
# Set the ADC channel
pd_channel = 0
temp_channel = 1

# Set the DAC channels
led_channel = 0
motor_channel = 0

# Initialise the ADC to be ready to read voltages from the photodiode
ADC(pd_channel)
ADC(pd_channel)
# Use the sequence and shadow mode (both set to high) to convert on a
# sequence of channels. The first conversion will be channel zero, the second
# channel one, etc.
ADC(temp_channel, write_mode='1', sequence='1', shadow='1', range_mode='1')

# Create a loop for the main program
while TRUE:
     # Define values for the thresholds
     pd_low = 
     pd_high = 
     # Create a boolean variable to define if sunlight is bright (true) or dim (false). Start by assuming it is bright
     pd_sun_on = True
     # Read the voltage from the photodiode
     pd_voltage = get_voltage(ADC(temp_channel, write_mode = '0', sequence = '1', shadow = '1', range_mode = '1'), range_mode = '1')
     # Assess the sun level based on photodiode voltage
     if pd_sun_on and pd_voltage < pd_low:
          pd_sun_on = not pd_sun_on
     elif not (pd_sun_on) and pd_voltage > pd_high:
          pd_sun_on = not pd_sun_on

     # Create a boolean variable to assess whether the led has overheated
     temp_led_overheat = False

     # Create a boolean variable to define when the LED is on
     led_on = False

     # Find the voltage across the thermocouple to check the temperature of the led
     temp_voltage = get_voltage(ADC(temp_channel, write_mode = '0', sequence = '1', shadow = '1', range_mode = '1'), range_mode = '1')

     temp = voltage_to_temperature(temp_voltage)

     # If the temperature gets too high, set the overheat variable high
     if temp > 70:
          temp_led_overheat = True
     
     # Turn off the led if it is on
     if temp_led_overheat and led_on:
          led_on = False
 
     # If the sun goes down, move the motor and then turn on the led
     if not(pd_sun_on and motor_in):
          motor_move = True
     elif pd_sun_on and motor_in:
          motor_move = True

     while motor_move and not(motor_in):
          DAC(motor_channel, 2)
          
     while motor_move and motor_in:
          DAC(motor_channel, 1)

     # Set the brightness of the LED
     #################################
     # Calibrate this!!
     #################################
     if motor_in:
          DAC(led_channel, pd_sun_level)


  
GPIO.cleanup()
