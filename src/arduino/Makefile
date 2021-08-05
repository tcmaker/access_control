ARDUINO_DIR   = /usr/share/arduino
ARDMK_DIR     = /usr/share/arduino
AVR_TOOLS_DIR = /usr

AVRDUDE_CONF=/usr/share/arduino/hardware/tools/avrdude.conf
BOARD_TAG = uno
BOARD_SUB = atmega328

#USER_LIB_PATH := /home/rdahlstrom/access_control/src/arduino/libraries # $(realpath Libraries)
USER_LIB_PATH := $(realpath .)/libraries
ARDUINO_LIBS=Wire WIEGAND26 PCATTACH DS1307 Adafruit_MCP23017
#include Arduino.mk
include /usr/share/arduino/Arduino.mk
