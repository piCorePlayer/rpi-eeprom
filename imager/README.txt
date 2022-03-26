Raspberry Pi 4 EEPROM bootloader rescue image
*********************************************

The Raspberry Pi 4 contains a small EEPROM used to store the bootloader.

This rescue image reverts the bootloader EEPROM to factory default settings.

This rescue image also updates the USB 3 controller (VL805) firmware to the
latest version, 138a1, which has better full-speed isochronous endpoint 
support.

Raspberry Pi 4 board revisions 1.1 and 1.2 contain a separate EEPROM 
which contains firmware for the USB 3 controller (VL805): on newer revisions 
the USB controller firmware is stored in the bootloader EEPROM along with 
the bootloader.

The easiest method for creating EEPROM rescue images, and formatting SD 
cards, is to use Raspberry Pi Imager from https://raspberrypi.com/software.
Raspberry Pi Imager provides a GUI for downloading the latest version of 
this rescue image and flashing it to a spare SD card.

Alternatively, copy the contents of this zip file to a blank
FAT formatted SD card. The FAT partition must be < 32 GB.

To update the EEPROM:

1. Power off the Raspberry Pi
2. Insert the bootloader update SD card
3. Power on the Raspberry Pi
4. Wait at least 10 seconds

If successful, the green LED on the Raspberry Pi will blink rapidly forever.
An unsuccessful update of the EEPROM is indicated by a different blinking 
pattern corresponding to the specific error.

If an HDMI display is attached, then the screen will display green for
success or red if a failure occurs.

Once the EEPROM is updated, the SD card can be removed. In order to make
the entire capacity of the SD card available again, you must then reformat
the SD card using Raspberry Pi Imager by selecting the 'format card as 
FAT32' option.
