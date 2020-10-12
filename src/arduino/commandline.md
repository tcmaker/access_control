# Commandline Interface

Each command will consist of a single character, an optional number of arguments, followed by a carriage return.

Arguments will be seperated by commas.

Responses will also follow the same format, but with a newline following the carriage return. 

Host-initiated requests will have lowercase letters. Responses will have the same, upper case letter.

The door controller will start up in echo mode, and debug mode OFF.

### Commands

Unless indicated, the device will reply to a command with a confirmation consisting of the command character, in uppercase.

| Character |  Description | Parameters | Example| 
| --- | --- | --- | --- |
| ? | Show Help | | 
| e | Change Echo Mode | 0 for off, 1 for on |
| o | Open Relay | 1 based relay number | o1\r |
| c | Close Relay | 1 based relay number | c1\r |
| q | Query / 1 based relay number | q1\r
| b | Buzz | 1 based reader number | b1\r |
| r | LED | 1 based reader number | l1\r |
| i | Device Info | | n\r |
  

### Responses and Notifications

| Character | Description | Parameters | Example |
| --- | --- | --- | ---|
| F | Keyfob scanned | Integer of fob id, Scanner | f16294934,1\n |
| P | Passcode entered | Integer of passcode, Scanner | p43949261,1\n |
| V | Firmware version | | V0.1\n
| G | Invalid input | | G\n |



