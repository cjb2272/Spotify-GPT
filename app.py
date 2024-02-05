from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, session
import urllib.parse
import requests
import openai
from openai import OpenAI
import ast
import json
import os

import os

api_key = os.environ.get('OPENAI_APIKEY') # Open AI API Key https://platform.openai.com/api-keys
openai.api_key = api_key

client = OpenAI(api_key=api_key)

app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRETKEY') # flask secret key

CLIENT_ID = os.environ.get('CLIENT_ID') # Spotify Client ID: Get this info from your Spotify Dashboard https://developer.spotify.com/dashboard
CLIENT_SECRET = os.environ.get('CLIENT_SECRET') # Spotify Client Secret: https://developer.spotify.com/dashboard
REDIRECT_URI = 'http://localhost:5000/callback' # Use Your domain name and add "/callback" on the end

AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_BASE_URL = 'https://api.spotify.com/v1/'

@app.route("/")
def index():
    """Landing Page for Spotify Authentication"""
    return "Welcome to my Spotify App <a href='/login'>Login with Spotify</a>"

@app.route("/login")
def login():
    """Redirects to Official Spotify Login Page"""
    scope = "user-library-read playlist-modify-public playlist-modify-private"
    auth_headers = {
    "client_id": CLIENT_ID,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": scope,
    "show_dialog": True
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_headers)}"
    return redirect(auth_url)

@app.route("/callback")
def callback():
    """Grants user access token info and redirects to Spotify-GPT App"""
    if 'error' in request.args:
        return jsonify({"error": request.args['error']})
    
    if 'code' in request.args:
        req_body = {
            'code': request.args['code'],
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET 
        }
        response = requests.post(TOKEN_URL, data=req_body)
        token_info = response.json()

        session['access_token'] = token_info['access_token']
        session['refresh_token'] = token_info['refresh_token']
        session['expires_at'] = datetime.now().timestamp() + token_info['expires_in']
        return render_template("chat.html")

@app.route("/refresh-token")
def refresh_token():
    """Refresh Token Logic"""
    if 'refresh_token' not in session:
        return redirect('login')
    if datetime.now().timestamp() > session['expires_at']:
        req_body = {
            'grant_type': 'refresh_token',
            'refresh_token': session['refesh_token'],
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        } 
        response = requests.post(TOKEN_URL, data=req_body)
        new_token_info = response.json()

        session['access_token'] = new_token_info['access_token']
        session['expires_at'] = datetime.now().timestamp() + new_token_info['expires_in']
        return render_template("chat.html")

@app.route("/get", methods=["GET", "POST"])
def chat():
    """Chatbot logic"""
    msg = request.form["msg"]
    input = msg # Unedited prompt
    valid = check_if_request_valid(input)
    if valid.lower() == 'yes':
        revised_prompt = prompt_engineer(input)
        json_completed_prompt = get_completion(revised_prompt) # Json data that we will make our request with
        make_playlist_request(json_completed_prompt) # Make playlist request
        return json_completed_prompt
    else:
        return "Sorry I only accept Music requests!"

def check_if_request_valid(input):
    """Checks if message is a musical playlist request"""
    prompt_check = f"Does this prompt have anything to do with asking for music recommendations? If it does, simply say 'yes', if it doesn't, simply say 'no' - Prompt:'{input}'"
    response = get_completion(prompt_check)
    return response

def get_completion(prompt, model="gpt-3.5-turbo"):
    """ChatGPT API Helper Method"""
    messages = [{"role": "user", "content": prompt}]
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0, # this is the degree of randomness of the model's output
    )
    return response.choices[0].message.content

def prompt_engineer(input):
    """Makes the prompt into a song recommendation format so we can process it"""
    prompt = input + """. Make sure this playlist is in json format and 'artist' and 'song' are the keys. Limit this playlist to 10 songs please. 
    Ex. {'playlist':[{'artist':'Frank Ocean', 'song': 'Thinking Bout You'},{'artist': 'Daniel Caesar', 'song': 'Japanese Denim'}]}"""
    return prompt

def get_user_id(headers):
    """Gets the user id of the user's spotify account"""
    response = requests.get(API_BASE_URL + 'me', headers=headers)
    spotify_id = response.json()['id']
    return spotify_id

def create_playlist(id, headers):
    """Creates Playlist"""
    request_body = json.dumps({
      "name": "TEST-GPT",
      "description":"Testing MY API HEHE",
      "public": False
    })
    response_playlist = requests.post(API_BASE_URL + f"users/{id}/playlists", data=request_body, headers=headers)
    return response_playlist

def get_track_id(search_query, headers):
    """Gets the id of a music track"""
    track_info = requests.get(API_BASE_URL + "search", headers=headers, params={'q': {search_query}, "type": "track"})
    track_info_json = track_info.json()
    id = track_info_json['tracks']['items'][0]['id']
    final_id = "spotify:track:" + id
    return final_id

def add_tracks_to_playlist(playlist_id, list_of_track_ids, headers):
    """Adds a list of tracks to a playlist"""
    request_body = json.dumps({
      "uris": list_of_track_ids
    })
    response = requests.post(API_BASE_URL + f"playlists/{playlist_id}/tracks", data=request_body, headers=headers)
    return response

def make_playlist_request(gpt_response):
    """Main Method for app"""
    if 'access_token' not in session:
        return redirect('/login')
    
    if datetime.now().timestamp() > session['expires_at']:
        return redirect('/refresh-token')
    
    headers = {
        'Authorization': f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }

    new_dict = ast.literal_eval(gpt_response)

    # Get User ID
    user_id = get_user_id(headers)

    # Create Playlist
    playlist_obj = create_playlist(user_id, headers)

    # Get Playlist ID
    response_playlist_id = playlist_obj.json()['id']

    song_ids = []
    for i in range(len(new_dict['playlist'])):
        search_query = new_dict['playlist'][i]['song'] + " " + new_dict['playlist'][i]['artist']
        track_id = get_track_id(search_query, headers)
        song_ids.append(track_id)

    response = add_tracks_to_playlist(response_playlist_id, song_ids, headers)
    return response

if __name__ == '__main__':
    app.run()
