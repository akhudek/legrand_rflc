# Legrand RF Lighting for Home Assistant

Home Assistant component for Legrand LC7001. This is work by 
[rtyle](https://github.com/rtyle/home-assistant.core/tree/legrand_rflc/homeassistant/components/legrand_rflc) that I simply packaged for easier installation.

To use it, first add it to your `custom_components` directory,
then restart home assistant. Alternatevly you can add the repository
to HACS as a custom repository. 

When you add the integration, it will as you for the host and password. 
Sadly, the mDNS host `LCM1.local` doesn't work due to mDNS not working
inside home assistant docker containers. You should assign a fixed ip
to the LC7001, then use the ip as the hostname. The password is the 
local password for the LC7001. 

This integration does not use the cloud to control the LC7001, it 
communicates locally.
