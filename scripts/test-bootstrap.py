#!/usr/bin/env python3

import socket
import requests
from requests import Response
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError
from urllib.parse import quote
from urllib3.util.retry import Retry
import sys
import time

matrix_homeserver = 'synapse'
bridge_config_file = "/app/config/server-config.yaml"
base_url = "http://%s:8008/_matrix/client/r0/" % matrix_homeserver
headers = {'Authorization': "Bearer 34f1a5283a16218970d784acefabf65f4754a79a90a264056387277b7753d11b"}
matrix_room = '_test'
irc_room = '#botsbotsbots'

print("Creating a Matrix room with alias '#%s' bridged to IRC channel %s..." % (matrix_room, irc_room))
print("  Waiting for Matrix server to appear...")
sys.stdout.flush()

# Be lenient with the matrix server, as this script may be run before it even exists.
session = requests.Session()
session.mount(base_url, HTTPAdapter(max_retries=Retry(total=20, connect=30, backoff_factor=0.1)))

socket_retries = 0
max_socket_retries = 10
retry_backoff_factor = 0.1
create_room_response = None

# The Matrix homeserver may not even be in the DNS yet, so retry address lookups.
while create_room_response is None and socket_retries <= max_socket_retries:
    try:
        create_room_response = requests.post(
            base_url + 'createRoom',
            json={"name": "Testing room"},
            headers=headers)

    except ConnectionError as error:
        time.sleep(retry_backoff_factor * (2 ** (socket_retries - 1)))
        socket_retries += 1

if create_room_response is None:
    raise TimeoutError()

matrix_room_id = create_room_response.json()['room_id']
print("  Matrix room id: %s\n" % matrix_room_id)
sys.stdout.flush()

create_alias_response = requests.put(
    base_url + quote("directory/room/#%s:chat.sneakyfrog.com" % matrix_room),
    json={"room_id": matrix_room_id},
    headers=headers)

# Fail if unsuccessful.
Response.raise_for_status(create_alias_response)

config_indent = '      '
mapping_config_line_1 = config_indent + 'mappings:\n'
mapping_config_line_2 = config_indent + '  "%s": ["%s"]\n' % (irc_room, matrix_room_id)

match_string = '__MAPPINGS_MARKER__'

with open(bridge_config_file, 'r+') as fd:
    contents = fd.readlines()
    if match_string in contents[-1]:  # Handle last line to prevent IndexError
        contents.append(mapping_config_line_1)
        contents.append(mapping_config_line_2)
    else:
        for index, line in enumerate(contents):
            if match_string in line and mapping_config_line_1 not in contents[index + 1]:
                contents.insert(index + 1, mapping_config_line_1)
                contents.insert(index + 2, mapping_config_line_2)
                break
    fd.seek(0)
    fd.writelines(contents)
