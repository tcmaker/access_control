# Door Display

This service runs as a webserver to show fob scan results on the display by the door.

# Setup procedure

1. Setup virtualenv. TODO
2. Edit display.ini to have appropriate values. Run with --help to see options.
2. Edit appropriate values from door_display.service, then copy it to /etc/systemd/system
2. run `sudo systemctl enable door_display.service`
3. Point a webbrowser at the server, and you should be good to go. 