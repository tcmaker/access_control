
cmake_minimum_required(VERSION 2.8.4)
set(CMAKE_TOOLCHAIN_FILE ${CMAKE_SOURCE_DIR}/cmake/ArduinoToolchain.cmake)
set(CMAKE_CXX_STANDARD 98)
set(PROJECT_NAME door_firmware)

set(${PROJECT_NAME}_BOARD atmega328)
#set(ARDUINO_CPU atmega328p)
#set(MCU atmega328p)
#set(atmega328.build.mcu atmega328p)
project(${PROJECT_NAME})

# Define additional source and header files or default arduino sketch files
# set(${PROJECT_NAME}_SRCS)
# set(${PROJECT_NAME}_HDRS)

### Additional static libraries to include in the target.
# set(${PROJECT_NAME}_LIBS)

### Main sketch file
set(${PROJECT_NAME}_SKETCH tcmakerdoor.ino)

### Add project directories into the build
# add_subdirectory()

### Additional settings to add non-standard or your own Arduino libraries.
# For this example (libs will contain additional arduino libraries)
# An Arduino library my_lib will contain files in libs/my_lib/: my_lib.h, my_lib.cpp + any other cpp files
# link_directories(${CMAKE_CURRENT_SOURCE_DIR}/)
#message("CCSD: ${CMAKE_CURRENT_SOURCE_DIR} AAAAHHH")
link_directories(${CMAKE_CURRENT_SOURCE_DIR}/libraries/)
#link_directories(/home/rdahlstrom/tcmakerdoor/libraries/)

# For nested library sources replace ${LIB_NAME} with library name for each library
set(WIEGAND26_RECURSE true)
set(PCATTACH_RECURSE true)
set(Adafruit_MCP23017_RECURSE true)

#### Additional settings for programmer. From programmers.txt
set(${PROJECT_NAME}_PROGRAMMER arduinoisp)
set(${PROJECT_NAME}_PORT /dev/ttyUSB0)
# set(diecimila.upload.speed 9600)
 set(atmega328.upload.speed 57600)


## Verbose build process
set(${PROJECT_NAME}_AFLAGS -v)

generate_arduino_firmware(${PROJECT_NAME})


#print_board_list()
#print_programmer_list()
