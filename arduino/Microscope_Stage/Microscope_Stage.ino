/**
 * Welcome to my absolute rats nest of firmware.
 * Whoever you are I hope you enjoy your stay🥴
 * 
 * Serial Command Format:
 * "Move {X or Y}, {distance}"
 * "Speed {Home or Move}, {speed}"
 * "Home"
 *
 * Author: Kevin Lau
 * Class: EE 4951W (Team Micromanagers)
 * Date: 3/16/2023
 *
 */

#include <stdio.h>
#include <string>
// Defines pins
#define stepPinOne 1
#define dirPinOne 2

#define stepPinTwo 3
#define dirPinTwo 4

#define limitOne 5
#define limitTwo 6
 
#define msOne 21
#define msTwo 20

// Strings for serial communication
String serialInput = ""; 
String command = "";
String data = "";

// Define speeds (higher value = slower, smaller value = faster)
int homeSpeed = 64;
int moveSpeed = 64;

// Track X and Y motor indexes
int indexOne; 
int indexTwo;

int factor = 1; // Factor default for MS: 00=1/8

void setup() {
  // Serial Setup
  Serial.begin(9600); 
  Serial.setTimeout(32);  
  Serial.println("Setup Beginning");

  // Sets the step, dir, ms pins as Outputs
  pinMode(stepPinOne,OUTPUT); 
  pinMode(dirPinOne,OUTPUT);
  pinMode(stepPinTwo,OUTPUT); 
  pinMode(dirPinTwo,OUTPUT);
  pinMode(msOne,OUTPUT);
  pinMode(msTwo,OUTPUT);

  // Sets the limit pins as Inputs
  pinMode(limitOne,INPUT); 
  pinMode(limitTwo,INPUT);

  // Microstep resolution (MS2, MS1: 00=1/8, 01=1/32, 10=1/64, 11=1/16)
  digitalWrite(msTwo,HIGH);
  digitalWrite(msOne,LOW);

  // Set Factor
  if(digitalRead(msTwo) == 0 && digitalRead(msOne) == 1) {
    factor = 4; // For MS: 01=1/32
  } else if(digitalRead(msTwo) == 1 && digitalRead(msOne) == 0) {
    factor = 8; // For MS: 10=1/64
  } else if(digitalRead(msTwo) == 1 && digitalRead(msOne) == 1) {
    factor = 2; // For MS: 11=1/16
  }

  // Motor/Stage Homing
  home();

  // End of Setup()
  Serial.println("Setup Complete");
}

void home() {
  // Stage Homing for one
  digitalWrite(dirPinOne,HIGH);
  while (1){
    digitalWrite(stepPinOne,HIGH);
    delayMicroseconds(homeSpeed/factor);
    digitalWrite(stepPinOne,LOW);
    delayMicroseconds(homeSpeed/factor);
    if(digitalRead(limitOne) == LOW){
      indexOne = 0;
      break;
    }
  }
  // Stage Homing for two
  digitalWrite(dirPinTwo,HIGH); 
  while (1){
    digitalWrite(stepPinTwo,HIGH);
    delayMicroseconds(homeSpeed/factor);
    digitalWrite(stepPinTwo,LOW);
    delayMicroseconds(homeSpeed/factor);
    if(digitalRead(limitTwo) == LOW){
      indexTwo = 0;
      break;
    }
  }
  Serial.println("Stage is Home");
}

void set_speed(String type, int speed) {
  if(speed < 0) {
    Serial.println("Speed value cannot be negative");
  } else if(type == "Home") {
    homeSpeed = speed;
    Serial.println("homeSpeed = " + String(speed));
  } else if(type == "Move") {
    moveSpeed = speed;
    Serial.println("moveSpeed = " + String(speed));
  }
}

void move_motor(int dist, char axis) {
  int stepPin;
  int dirPin;
  int limit;
  int* index;

  // Set step, direction, limit, and index based on axis
  switch(axis) {
    case 'X':
      stepPin = stepPinTwo;
      dirPin = dirPinTwo;
      limit = limitTwo;
      index = &indexTwo; 
      break;
    case 'Y':
      stepPin = stepPinOne;
      dirPin = dirPinOne;
      limit = limitOne;
      index = &indexOne;
      break;
    default:
      Serial.println("Error: Inputted axis not valid");
  }
  
  // Set motor direction
  if(dist < 0) {
    digitalWrite(dirPin, HIGH);
  } else if(dist > 0) {
    digitalWrite(dirPin, LOW);
  }

  // Send signals to move motor
  for(int i = 0; i < abs(dist); i++) {
    digitalWrite(stepPin,HIGH);
    delayMicroseconds(moveSpeed/factor);
    digitalWrite(stepPin,LOW);
    delayMicroseconds(moveSpeed/factor);
    if(*index >= (81000 * factor) && dist > 0){ // Stops at physical limit in pos direction
      break;
    } else if(digitalRead(limit) == LOW && dist < 0) { // Stops at limit switch in neg direction
      *index = 0;
      break;
    }

    // Update index of axis
    if(dist < 0) {
      *index -= 1;
    } else if(dist > 0) {
      *index += 1;
    }
  }
  Serial.println("Index: " + String(*index)); // Sends status and index to serial
}

void loop() {
  if (Serial.available() > 0) { // Check for serial input
    serialInput = Serial.readString();
    int comma = serialInput.indexOf(","); // Find index of "," delimiter parsing command and index
    command = serialInput.substring(0, comma).trim();
    data = serialInput.substring(comma + 1).trim();
    CommandProcessor(command.toLowerCase(), data);  // Send command and data to command processor
  }
}
