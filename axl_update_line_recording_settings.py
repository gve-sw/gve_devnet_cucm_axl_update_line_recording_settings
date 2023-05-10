"""
Copyright (c) 2023 Cisco and/or its affiliates.

This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at

               https://developer.cisco.com/docs/licenses

All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

from lxml import etree
from requests import Session
from requests.auth import HTTPBasicAuth

from zeep import Client, Settings, Plugin, xsd
from zeep.transports import Transport
from zeep.exceptions import Fault
import sys
import urllib3

# Edit .env file to specify your Webex site/user details
import os
from dotenv import load_dotenv

load_dotenv()

# Change to true to enable output of request/response headers and XML
DEBUG = False

# The WSDL is a local file in the working directory, see README
WSDL_FILE = "schema/AXLAPI.wsdl"

# Automatic Call Recording Enabled | * Selective Call Recording Enabled
RECORDING_OPTION = "Automatic Call Recording Enabled"
# Imagicle Call Recording Profile | * MediaSense
RECORDING_PROFILE = "MediaSense"
# * Gateway Preferred | Phone Preferred | BuiltInBridge
RECORDING_MEDIA_SOURCE = "Phone Preferred"


# This class lets you view the incoming and outgoing http headers and XML
class MyLoggingPlugin(Plugin):
    def egress(self, envelope, http_headers, operation, binding_options):
        # Format the request body as pretty printed XML
        xml = etree.tostring(envelope, pretty_print=True, encoding="unicode")

        print(f"\nRequest\n-------\nHeaders:\n{http_headers}\n\nBody:\n{xml}")

    def ingress(self, envelope, http_headers, operation):
        # Format the response body as pretty printed XML
        xml = etree.tostring(envelope, pretty_print=True, encoding="unicode")

        print(f"\nResponse\n-------\nHeaders:\n{http_headers}\n\nBody:\n{xml}")


# The first step is to create a SOAP client session
session = Session()

# We avoid certificate verification by default
# And disable insecure request warnings to keep the output clear
session.verify = False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# To enabled SSL cert checking (recommended for production)
# place the CUCM Tomcat cert .pem file in the root of the project
# and uncomment the line below

# session.verify = 'changeme.pem'

# Add Basic Auth credentials
session.auth = HTTPBasicAuth(os.getenv("AXL_USERNAME"), os.getenv("AXL_PASSWORD"))

# Create a Zeep transport and set a reasonable timeout value
transport = Transport(session=session, timeout=10)

# strict=False is not always necessary, but it allows zeep to parse imperfect XML
settings = Settings(strict=False, xml_huge_tree=True)

# If debug output is requested, add the MyLoggingPlugin callback
plugin = [MyLoggingPlugin()] if DEBUG else []

# Create the Zeep client with the specified settings
client = Client(WSDL_FILE, settings=settings, transport=transport, plugins=plugin)

# Create the Zeep service binding to AXL at the specified CUCM
service = client.create_service(
    "{http://www.cisco.com/AXLAPIService/}AXLAPIBinding",
    f'https://{os.getenv( "CUCM_ADDRESS" )}:8443/axl/',
)

# Retrieve the UUID of the recording profile with name stored in RECORDING_PROFILE
# and store in recording_profile_uuid to be able to use in the call below that updates the profile
try:
    resp = service.listRecordingProfile(
        searchCriteria={"name": RECORDING_PROFILE}, returnedTags={"name": xsd.Nil}
    )
except Fault as err:
    print(f"Zeep error: listRecordingProfile: { err }")
    sys.exit(1)
if resp["return"] and "recordingProfile" in resp["return"]:
    recording_profile_full = resp["return"]["recordingProfile"][0]

# now process all users in the user_ids.txt file
with open("user_ids.txt", "r") as f:
    for line in f.readlines():
        user_id = line.rstrip()
        theLen = len(user_id)
        print(f"UserID: {user_id} length: {theLen}")
        # Execute the addLine request
        try:
            # Get the user data
            user_resp = service.getUser(userid=user_id)
        except Fault as err:
            print(f"Zeep error: getUser: { err }")
            continue

        # Create an empty list to store the device names
        device_list = []

        # Loop through the list of devices and add the device names to the list
        for device in user_resp["return"]["user"]["associatedDevices"]["device"]:
            device_list.append(device)

        # Print the list of associated devices
        print(device_list)

        # Print the list of associated devices
        for device in device_list:
            device_name = device
            print("Device name: ", device_name)

            try:
                # Get the lines associated with the device
                dev_resp = service.getDeviceProfile(name=device_name)
            except Fault as err:
                print(f"Zeep error: getDeviceProfile: { err }")
                # sys.exit(1)

            the_uuid = dev_resp["return"]["deviceProfile"]["uuid"]

            # Loop through each deviceProfile and update the recordingMediaSource field
            for line in dev_resp["return"]["deviceProfile"]["lines"]["line"]:
                theDisplay = line["display"]
                print(f"Processing line {theDisplay}")
                line["recordingFlag"] = RECORDING_OPTION
                line["recordingMediaSource"] = RECORDING_MEDIA_SOURCE
                line["recordingProfileName"] = recording_profile_full

            try:
                update_resp = service.updateDeviceProfile(
                    uuid=the_uuid, lines=dev_resp["return"]["deviceProfile"]["lines"]
                )
                print(
                    f"Lines updated with new recordings settings = {update_resp['return']}"
                )
            except Fault as err:
                print(f"Zeep error: updateDeviceProfile: { err }")
