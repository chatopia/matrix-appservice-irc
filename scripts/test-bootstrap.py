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
import os

matrix_homeserver = 'synapse'
bridge_config_file = "/app/config/server-config.yaml"
base_url = "http://%s:8008/_matrix/client/r0/" % matrix_homeserver

retry_backoff_factor = 0.1
max_retries = 10

matrix_room_alias = os.getenv('TEST_MATRIX_ROOM', '#_test')
irc_channel = os.getenv('TEST_IRC_CHANNEL', '#botsbotsbots')
matrix_username = os.getenv('TEST_USERNAME', 'user')
matrix_password = os.getenv('TEST_PASSWORD', 'password')

print("Creating a Matrix user with username '%s'..." % matrix_username)
print("  Waiting for Matrix server to appear...")
sys.stdout.flush()

# Be lenient with the matrix server, as this script may be run before it even exists.
session = requests.Session()
session.mount(base_url, HTTPAdapter(max_retries=Retry(total=max_retries, backoff_factor=retry_backoff_factor)))

socket_retries = 0
create_user_response = None

registration_json = {
    'username': matrix_username,
    'password': matrix_password
}

register_url = base_url + 'register'

# The Matrix homeserver may not even be in the DNS yet, so retry address lookups.
while create_user_response is None and socket_retries <= max_retries:
    try:
        create_user_response = requests.post(register_url, json=registration_json)

    except ConnectionError as error:
        time.sleep(retry_backoff_factor * (2 ** (socket_retries - 1)))
        socket_retries += 1

if create_user_response is None:
    raise TimeoutError()

if create_user_response.status_code == 400 and create_user_response.json()['errcode'] == 'M_USER_IN_USE':
    print("  User already exists. Logging in...")

    login_response = requests.post(base_url + "login", json={
        "type": "m.login.password",
        "identifier": {
            "type": "m.id.user",
            "user": matrix_username
        },
        "password": matrix_password
    })

    if login_response.ok:
        access_token = login_response.json()['access_token']
    else:
        print("  Login failed. Exiting.")
        exit(0)
else:
    session_token = create_user_response.json()['session']

    registration_json['auth'] = {
        "type": "m.login.dummy",
        "session": session_token
    }

    create_user_response_auth = requests.post(register_url, json=registration_json)
    Response.raise_for_status(create_user_response_auth)

    access_token = create_user_response_auth.json()['access_token']

query_params = {'access_token': access_token}

prepended_hash = False
if not matrix_room_alias.startswith('#'):
    prepended_hash = True
    matrix_room_alias = '#' + matrix_room_alias

print("Creating a Matrix room with alias '%s' bridged to IRC channel %s..." % (matrix_room_alias, irc_channel))
if prepended_hash:
    print("  [Warning: prepended missing '#' to room name]")

create_room_response = requests.post(
    base_url + 'createRoom',
    json={"name": "Testing room"},
    params=query_params)

Response.raise_for_status(create_room_response)
matrix_room_id = create_room_response.json()['room_id']
print("  Matrix room id: %s" % matrix_room_id)
sys.stdout.flush()

create_alias_response = requests.put(
    base_url + quote("directory/room/%s:chat.sneakyfrog.com" % matrix_room_alias),
    json={"room_id": matrix_room_id},
    params=query_params)

if create_alias_response.status_code == 409:
    print("  Room with alias '%s' already exists. Exiting.\n" % matrix_room_alias)
    exit(0)

# Fail if unsuccessful.
Response.raise_for_status(create_alias_response)

config_indent = '      '
mapping_config_line_1 = config_indent + 'mappings:\n'
mapping_config_line_2 = config_indent + '  "%s": ["%s"]\n' % (irc_channel, matrix_room_id)

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
