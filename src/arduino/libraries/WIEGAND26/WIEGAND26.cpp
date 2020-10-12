#include <WIEGAND26.h>

extern byte reader1Pins[];          // Reader 1 connected to pins 4,5
extern byte reader2Pins[];          // Reader2 connected to pins 6,7
extern long readerBuffer[2];
extern int  readerCounts[2];



volatile bool bitsRead[2] = {false,false};
unsigned long firstBitMicros[2] = { 0,0};


WIEGAND26::WIEGAND26(){
}

WIEGAND26::~WIEGAND26(){
}



/* Wiegand Reader code. Modify as needed or comment out unused readers.
 *  system supports up to 3 independent readers.
 */


void WIEGAND26::initReaderOne(void) {
    //Serial.println("Init reader 1");
    for(byte i=0; i<2; i++){
    pinMode(reader1Pins[i], OUTPUT);
    digitalWrite(reader1Pins[i], HIGH); // enable internal pull up causing a one
    digitalWrite(reader1Pins[i], LOW); // disable internal pull up causing zero and thus an interrupt
    pinMode(reader1Pins[i], INPUT);
    digitalWrite(reader1Pins[i], HIGH); // enable internal pull up
  }
  delay(10);
  readerCounts[0]=0;
  readerBuffer[0]=0;
  bitsRead[0] = false;

}


void  WIEGAND26::initReaderTwo(void) {
    for (byte i = 0; i < 2; i++) {
        pinMode(reader2Pins[i], OUTPUT);
        digitalWrite(reader2Pins[i], HIGH); // enable internal pull up causing a one
        digitalWrite(reader2Pins[i], LOW); // disable internal pull up causing zero and thus an interrupt
        pinMode(reader2Pins[i], INPUT);
        digitalWrite(reader2Pins[i], HIGH); // enable internal pull up
    }
    delay(10);
    readerCounts[1] = 0;
    readerBuffer[1] = 0;
    bitsRead[1] = false;
}
void WIEGAND26::readerOne(char reader) {
    if (!bitsRead[reader]) {
        bitsRead[reader] = true;
        readerBuffer[reader] = 0;
        readerCounts[reader] = 0;
        firstBitMicros[reader] = micros();
    }

    readerCounts[reader]++;
    readerBuffer[reader] = readerBuffer[reader] << 1;
    readerBuffer[reader] |= 1;
}

void WIEGAND26::readerZero(char reader) {
    if (!bitsRead[reader]) {
        bitsRead[reader] = true;
        readerBuffer[reader] = 0;
        readerCounts[reader] = 0;
        firstBitMicros[reader] = micros();
    }

    readerCounts[reader]++;
    readerBuffer[reader] = readerBuffer[reader] << 1;
}

void  WIEGAND26::reader1One()
{
    if(digitalRead(reader1Pins[1]) == LOW)
    {
        readerOne(0);
    }
}

void  WIEGAND26::reader2One() {
    if(digitalRead(reader2Pins[1]) == LOW){
        readerOne(1);
    }
}

void  WIEGAND26::reader1Zero() {
  if(digitalRead(reader1Pins[0]) == LOW) {
      readerZero(0);
  }
}

void  WIEGAND26::reader2Zero(void) {
    if(digitalRead(reader1Pins[0]) == LOW) {
        readerZero(1);
    }
}


 
