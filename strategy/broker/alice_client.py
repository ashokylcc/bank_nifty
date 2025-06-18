import json
import requests
import hashlib

USER_ID = "1293756"
API_KEY = "G9oJBg4VLZt9CmrS0ATxB8DQ6iM2MAJIzeR8EmdNdyYIhCnDhqkdrzhYns5NrP7xdzzn8DF7MyGlpeXnrunfqIKlc7QG6z4iSC4dHKdK5jY8BnFHrG6fB70b2kH8cFW0"

BASE_URL = "https://ant.aliceblueonline.com/rest/AliceBlueAPIService/api/"

def get_encryption_key(user_id):
    url = BASE_URL + f"customer/getAPIEncpkey?userId={user_id}"
    payload = json.dumps({
    "userId": USER_ID
    })
    headers = {
    'Content-Type': 'application/json'
    }
    resp = requests.post(url, headers=headers, data=payload)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("stat") == "Ok":
            return data["encKey"]
        else:
            raise Exception(f"Failed to get encKey: {data.get('emsg')}")
    else:
        raise Exception(f"HTTP Error: {resp.status_code}")

def get_session_id(user_id, api_key, enc_key):
    concat_str = user_id + api_key + enc_key
    sha256_hash = hashlib.sha256(concat_str.encode()).hexdigest()
    payload = {
        "userId": user_id,
        "userData": sha256_hash
    }
    url = BASE_URL + "customer/getUserSID"
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("stat") == "Ok":
            return data["sessionID"]
        else:
            raise Exception(f"Failed to get sessionID: {data.get('emsg')}")
    else:
        raise Exception(f"HTTP Error: {resp.status_code}")