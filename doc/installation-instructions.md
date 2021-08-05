2021-01-11 Raspios Buster Lite
Using raspi-config:
  * change pi password
  * change keyboard layout
  * change timezone 
  * configure wifi

1. apt-get update

1. apt-get install vim python3-venv libmariadbclient-dev sqlite3 libusb-1.0 git

1. Add udev rules for the ftdi device
    ```
    # /etc/udev/rules.d/11-ftdi.rules
    
    
    # FT232AM/FT232BM/FT232R
    SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6001", GROUP="plugdev", MODE="0664"
    # FT2232C/FT2232D/FT2232H
    SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6010", GROUP="plugdev", MODE="0664"
    # FT4232/FT4232H
    SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6011", GROUP="plugdev", MODE="0664"
    # FT232H
    SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6014", GROUP="plugdev", MODE="0664"
    # FT230X/FT231X/FT234X
    SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6015", GROUP="plugdev", MODE="0664"
    ```

1. Setup python virtual environment
1. clone repo to pi
1. Activate virtual environment, install python dependencies:
      
   `pip install -r pyrequirements`

   It might complain about pyrsistent but it seems to actually install it

1. Make door_config.yaml and put it in a directory in the home folder
1. Copy tcdoor.service to `/etc/systemd/system`. Edit file as necessary to match
location of venv, repo checkout, and working directory
1. Run the service with `sudo systemctl start tcdoor` and verify everything is working correctly.
1. Make it autostart, `sudo systemctl enable tcdoor`, reboot and see that it comes up automatically


NOTES:

```
{
  "action": "deactivate",
  "code": "0010649959",
  "member": 8331,
  "access_level": 0
}

{
  "action": "activate",
  "code": "0010649959",
  "member": 8331,
  "access_level": 4
}
```

ssh tcmadmin@tcm-web01.tcmaker.org
mysql -h tcm-mariadb -u rdahlstrom -p

Me: Contact Id 3870 - Robert Dahlstrom

civicrm_membership where id == whatever, status_id


tunnel via db server
ssh -L 22444:localhost:22445 tcmadmin@tcm-web01.tcmaker.org
connect to pi:
ssh -p 22444 -L 8844:localhost:8443 pi@localhost


