#include <string>

void CommandProcessor(String command, String data) {
  // Execute based on command
  if(command == "move x") {
      move_motor(data.toInt(),'X');
  } else if(command == "move y") {
      move_motor(data.toInt(),'Y');
  } else if(command == "speed home") {
      set_speed("Home", data.toInt());
  } else if(command == "speed move") {
      set_speed("Move", data.toInt());
  } else if(command == "home") {
      home();
  } 
  else {
      Serial.println("Error: Command not valid");
  }
}
