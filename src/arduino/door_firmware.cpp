#define MODEL "TCM-ACCX"
#define VERSION "0.03"

#include <Arduino.h>
#include <HardwareSerial.h>
#include <WIEGAND26.h>          // Wiegand 26 reader format libary
#include <PCATTACH.h>
#include <Wire.h>
#include <Adafruit_MCP23017.h>  // Library for the MCP23017 i2c I/O expander
WIEGAND26 wiegand26;  // Wiegand26 (RFID reader serial protocol) library
PCATTACH pcattach;    // Software interrupt library
Adafruit_MCP23017 mcp;

// MCP pins
#define DOORPIN1       6                // Define the pin for electrified door 1 hardware. (MCP)
#define DOORPIN2       7                // Define the pin for electrified door 2 hardware  (MCP)
#define ALARMSTROBEPIN 8                // Define the "non alarm: output pin. Can go to a strobe, small chime, etc. Uses GPB0 (MCP pin 8).
#define ALARMSIRENPIN  9                // Define the alarm siren pin. This should be a LOUD siren for alarm purposes. Uses GPB1 (MCP pin9).
#define READER1GRN     10
#define READER1BUZ     11
#define READER2GRN     12
#define READER2BUZ     13
#define STATUSLED       14              // MCP pin 14


#define R1ZERO          2
#define R1ONE           3
#define R2ZERO          4
#define R2ONE           5

#define KP_ESCAPE 10
#define KP_ENTER 11
#define KP_BUTTON_TIMEOUT_MS 2000

uint8_t reader1Pins[]={R1ZERO, R1ONE};           // Reader 1 pin definition
uint8_t reader2Pins[]={R2ZERO, R2ONE};           // Reade  2 pin definition

volatile long readerBuffer[2] = { 0, 0};         // Reader buffers
volatile int  readerCounts[2] = {0,0};
volatile bool buzz = false;
volatile bool buzzHigh = false;

extern volatile bool bitsRead[2];// = {false, false};
extern unsigned long firstBitMicros[2];// = {0,0};

void setEchoMode(char rc);
void helpText(char rc);
void openRelay(char rc);
void closeRelay(char rc);
void deviceInfo(char rc);
void setLed(char rc);
void callReader1Zero();
void callReader1One();
void processButtonPress(int,int);
void doCli();
long decodeCard(long input);

struct command
{
    char code;
    char responseCode;
    char* helpText;
    void (*func)(char rc);
};



#define OUTBUFFER_SIZE 50
char outputBuffer[OUTBUFFER_SIZE];

command commands[] = { { '?','?',"show this help", helpText},
                       { 'e','E',"configure echo: 0=off, 1=on", setEchoMode},
                       { 'i','I',"get device info", deviceInfo},
                       { 'o','O',"open relay: relay num", openRelay},
                       { 'c','C',"close relay: relay num", closeRelay},
                       { 'l','L',"set LED: led num, 0=off, 1=on", setLed},
                       };

int numCommands;
void setup() {
    numCommands = (sizeof(commands) / sizeof(commands[0]));
    Wire.begin();   // start Wire library as I2C-Bus Master
    mcp.begin();      // use default address 0

    Serial.begin(57600);

    for(int i=0; i<=15; i++)        // Initialize the I/O expander pins
    {
        mcp.pinMode(i, OUTPUT);
    }

    pcattach.PCattachInterrupt(reader1Pins[0], callReader1Zero, CHANGE);
    pcattach.PCattachInterrupt(reader1Pins[1], callReader1One,  CHANGE);


    //Clear and initialize readers
    wiegand26.initReaderOne(); //Set up Reader 1 and clear buffers.
    wiegand26.initReaderTwo();

    //Start up with everything OFF
    mcp.digitalWrite(DOORPIN1, LOW);
    mcp.digitalWrite(DOORPIN2, LOW);
    mcp.digitalWrite(ALARMSTROBEPIN, LOW);
    mcp.digitalWrite(ALARMSIRENPIN, LOW);

    mcp.digitalWrite(STATUSLED, LOW);           // Turn the status LED green

    Serial.println("Firmware version " VERSION);
    snprintf(outputBuffer,OUTBUFFER_SIZE,"Num commands: %d",numCommands);
    Serial.println(outputBuffer);
    Serial.println("Ready. Enter ? for help");

}
volatile uint8_t readerByte = 0;
volatile uint8_t readBits = 0;



unsigned long now = 0;
unsigned long lastButtonPress[2] = {0,0};

void loop() {

    if(Serial.available()) {
        doCli(); //This should ensure a notification never occurs "in the middle" of a command
        //and its response
    }

    now = millis();
    /*if (debugMode && lastButtonPress > 0 && now - lastButtonPress > KP_BUTTON_TIMEOUT_MS) {
        snprintf(outputBuffer, 50, "DKeypadTimeout");
        Serial.println(outputBuffer);
        lastButtonPress = 0;
    }*/
    /*if(buzz) {
        mcp.digitalWrite(READER1BUZ, buzzHigh ? LOW : HIGH);
        buzzHigh = !buzzHigh;
    }
    else
    {
        mcp.digitalWrite(READER1BUZ, HIGH);
    }*/

    for (int reader = 0; reader < 2; reader++) {
        if (bitsRead[reader]) {
            if (micros() - firstBitMicros[reader] > 75000) {
                if (readerCounts[reader] == 26) {
                    snprintf(outputBuffer, 60, "F%ld,%d", decodeCard(readerBuffer[reader]),reader + 1);
                    Serial.println(outputBuffer);
                } else {
                    processButtonPress(reader, (int) readerBuffer[reader]);
                }

                readerBuffer[reader] = 0;
                readerCounts[reader] = 0;
                bitsRead[reader] = false;

            }
        }
    }


}

bool door[12] = {false};

char passcodeBuffer[2][20];
char passcodeIndex[2] = {0,0};

void processButtonPress(int reader, int button)
{
    if(now - lastButtonPress[reader] > KP_BUTTON_TIMEOUT_MS)
    {
        //We've run out of time, reset buffer
        passcodeIndex[reader] = 0;
        passcodeBuffer[reader][0] = 0;
    }

    if(button == KP_ESCAPE)
    {
        passcodeIndex[reader] = 0;
        passcodeBuffer[reader][0] = 0;
    }
    else if(button == KP_ENTER)
    {
        snprintf(outputBuffer,OUTBUFFER_SIZE,"P%s,%d",passcodeBuffer[reader],reader + 1);
        if(passcodeBuffer[reader][0] == '8')
        {
            mcp.digitalWrite(14,HIGH);
        } else{
            mcp.digitalWrite(14,LOW);
        }
        Serial.println(outputBuffer);
        passcodeIndex[reader] = 0;
        passcodeBuffer[reader][0] = 0;

    } else{
      lastButtonPress[reader] = now;
      passcodeBuffer[reader][passcodeIndex[reader]] = button + 48;
      passcodeBuffer[reader][passcodeIndex[reader] + 1] = 0;
      passcodeIndex[reader]++;
      if(passcodeIndex[reader] > 19)
      {
          passcodeIndex[reader] = 1;
      }
    }
}

#define CARDFORMAT 1

long decodeCard(long input)
{
    if(CARDFORMAT==0)
    {
        return(input);
    }

    if(CARDFORMAT==1)
    {
        bool parityHigh;
        bool parityLow;
        parityLow=bitRead(input,0);
        parityHigh=bitRead(input,26);
        bitWrite(input,25,0);        // Set highest (parity bit) to zero
        input=(input>>1);            // Shift out lowest bit (parity bit)

        return(input);
    }
}


//Unlocking is the powered state of the relay
//Activate the relay and light up the LED
void doorUnlock(int input) {

    uint8_t dp=1;
    uint8_t dpLED=1;

    if(input == 1)
    {
        dp=DOORPIN1;
        dpLED=READER1GRN;
    }
    else
    {
        dp=DOORPIN2;
        dpLED=READER2GRN;
    }
    mcp.digitalWrite(dp, HIGH);
    mcp.digitalWrite(dpLED, HIGH);
}

void doorLock(int input) {          //Send an unlock signal to the door and flash the Door LED
    uint8_t dp=1;
    uint8_t dpLED=1;
    if(input == 1)
    {
        dp=DOORPIN1;
        dpLED=READER1GRN;
    }
    else
    {
        dp=DOORPIN2;
        dpLED=READER2GRN;
    }

    mcp.digitalWrite(dp, LOW);
    mcp.digitalWrite(dpLED, LOW);
}

void callReader1Zero(){
    wiegand26.reader1Zero();
}
void callReader1One(){
    wiegand26.reader1One();
}

//Console

char ch;
char input[21];
char inputIndex = 0;
bool echoMode = true;

void clearInputBuffer()
{
    //for(int i = 0; i < 20; i++)
    //{
    //    input[i] = 0x00;
    //}
    input[0] = 0;
    inputIndex = 0;
}

void indicateGarbage()
{
    snprintf(outputBuffer,OUTBUFFER_SIZE,"G%s",input);
    Serial.println(outputBuffer);
}

void doCli()
{
    ch = Serial.read();

    if(echoMode)
    {
        Serial.print(ch);
    }

    if( ch != '\r')
    {
        input[inputIndex] = ch;
        input[inputIndex + 1] = 0;
        inputIndex++;
        if(inputIndex == 20)
        {
            indicateGarbage();
            clearInputBuffer(); //Indicate garbage and reset buffer
        }
    }
    else
    {
        if(echoMode)
        {
            Serial.print("\n");
        }


        bool foundCommand = false;
        for(int c = 0; c<numCommands; c++)
        {
            if(input[0] == commands[c].code)
            {
                foundCommand=true;
                commands[c].func(commands[c].responseCode);
                break;
            }
        }
        if(!foundCommand)
        {
            indicateGarbage();
        }


        switch(input[0]) {
            /*case 'm': {
                char pin = input[1] - 48;
                char low = input[2] - 48;
                mcp.digitalWrite(pin, low == 0 ? LOW : HIGH);
                snprintf(outputBuffer, OUTBUFFER_SIZE, "M%d,%d", pin,low);
                Serial.println(outputBuffer);
                break;
            }
            case 'b': //Buzz
            {
                char pin = input[1] - 48 == 1 ? READER1BUZ : READER2BUZ;
                char low = input[2] - 48 == 1;
                mcp.digitalWrite(pin, low == 0 ? LOW : HIGH);
                snprintf(outputBuffer, OUTBUFFER_SIZE, "B%d,%d", pin,low);
                Serial.println(outputBuffer);
                break;
            }
            case 'r': //led buzzing
                {
                char pin = input[1] - 48 == 1 ? READER1GRN : READER2GRN;
                char low = input[2] - 48 == 1;
                mcp.digitalWrite(pin, low == 0 ? LOW : HIGH);
                snprintf(outputBuffer,OUTBUFFER_SIZE,"L%d,%d",pin, low);
                Serial.println(outputBuffer);
                break;}
            default:
                break;
            */
        }

        clearInputBuffer();
    }
}
void helpText(char rc)
{
    Serial.println("Help:");
    for(int c = 0; c<numCommands; c++) {
        snprintf(outputBuffer,OUTBUFFER_SIZE,"\t%c : %s",commands[c].code,commands[c].helpText);
        Serial.println(outputBuffer);
    }
}

void setEchoMode(char rc) {
    //snprintf(outputBuffer, OUTBUFFER_SIZE, "II:%d,%d", inputIndex, input[1]);
    //Serial.println(outputBuffer);

    if (inputIndex != 2) {
        indicateGarbage();
    } else {
        echoMode = input[1] == '1';
        snprintf(outputBuffer, OUTBUFFER_SIZE, "E%d", echoMode ? 1 : 0);
        Serial.println(outputBuffer);
    }
}

void setLed(char rc)
{
    char doorNum = input[1] - 48;
    bool on = input[3] == '1';
    if (doorNum < 1 || doorNum > 4 || inputIndex != 4) {
        indicateGarbage();
    } else {
        buzz = on;
        mcp.digitalWrite(READER1GRN, on ? LOW : HIGH);
        mcp.digitalWrite(READER2GRN, on ? LOW : HIGH);
        //mcp.digitalWrite(READER1BUZ, on ? LOW : HIGH);
        //mcp.digitalWrite(READER2BUZ, on ? LOW : HIGH);
        snprintf(outputBuffer,OUTBUFFER_SIZE,"%c%d", rc,doorNum);
        Serial.println(outputBuffer);
    }
}

void deviceInfo(char rc)
{
    snprintf(outputBuffer,OUTBUFFER_SIZE,"%cm:%s,v:%s,s:%d,r:%d",rc,MODEL,VERSION,2,4);
    Serial.println(outputBuffer);
}

void openRelay(char rc)
{
    char doorNum = input[1] - 48;
    if (doorNum < 1 || doorNum > 4 || inputIndex != 2) {
        indicateGarbage();
    } else {
            mcp.digitalWrite(doorNum + 5, LOW);
            snprintf(outputBuffer,OUTBUFFER_SIZE,"%c%d", rc,doorNum);
        Serial.println(outputBuffer);
    }
}

void closeRelay(char rc)
{
    char doorNum = input[1] - 48;
    if (doorNum < 1 || doorNum > 4 || inputIndex != 2) {
        indicateGarbage();
    } else {
        mcp.digitalWrite(doorNum + 5, HIGH);
        snprintf(outputBuffer, OUTBUFFER_SIZE, "%c%d",rc, doorNum);
        Serial.println(outputBuffer);
    }
}