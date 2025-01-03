from datetime import datetime
import time
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import urllib.parse
import requests
import openai
from openai import OpenAI
import ast
import json
import os

# as a shortcut we name out flask app "app.py" that way when issuing the run flask command we dont have to specify an app location with --app

my_api_key = os.environ.get('OPENAI_API_KEY') # My secret key stored as an environment variable on my PC
openai.api_key = my_api_key # not sure what this line is doing TODO can try removing

client = OpenAI(
    api_key=my_api_key
)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# OAuth-based authentication flow
CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID') # Spotify Client ID & Secret found in Spotify Dashboard https://developer.spotify.com/dashboard
CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET') 

# Sedrick deployed his app quickly using Render, a hosting service
REDIRECT_URI = 'http://127.0.0.1:5000/callback' # Use Your domain name (where app is deployed) and add "/callback" on the end
# REDIRECT_URI is the URL to which the user is redirected after successful authentication
# When you authenticate with a third party service like spotify , 
# that service will redirect the user back to your app after the authentication process is complete

AUTH_ENDPOINT_URI = 'https://accounts.spotify.com/authorize' # AUTH_URL
TOKEN_ENDPOINT_URI = 'https://accounts.spotify.com/api/token'  # Token URL
API_BASE_URL = 'https://api.spotify.com/v1/' # Base Address of the Spotify Web API.  https://api.spotify.com. why is v1 included
PLAYLIST_BASE_URL = 'https://open.spotify.com/playlist/'

@app.route("/")
def index():
    """Landing Page for Spotify Authentication for the Spotify-GPT application.""" # Docstrings
    return render_template("index.html")  #html is our default response type in FLASK


@app.route("/login") # the route() decorator binds a function to a URL
def login():
    """ Method for requesting Spotify User Authorization by sending a GET request to the authorize endpoint
        - Redirects to Official Spotify Login Page
        - Scope header:
        ---- playlist-modify-private allows for creating a private playlist
    """
    # the user doing authentication is asked to authorize access to data sets /features defined in the scopes listed space delimited
    scope = "user-library-read playlist-modify-public playlist-modify-private user-top-read"
    auth_headers = {  # these are query string arguments which become part of the URL.. maybe they become headers after that like
    "client_id": CLIENT_ID,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": scope,
    "show_dialog": True,
    #"state": .... security param strongly recommended if moving to public..
    }
    # urllib.parse.urlencode() converts a dict of auth_headers into a query string for example 'client_id=123&response_type=code'
    auth_url = f"{AUTH_ENDPOINT_URI}?{urllib.parse.urlencode(auth_headers)}"
    return redirect(auth_url) 


# AFTER successful completetion of spotify authentication (third party auth)
# callback endpoint for handling this redirect and processing any token or user info sent by the spotify (or whatever third party service)
@app.route("/callback") 
def callback():
    """ Grants user access token info and redirects to Spotify-GPT App
        - Includes process of requesting an access token which remains valid for 1 hour.
        - Sets Session Variables including...
        ---- access_token, used as header in API Calls to access resources (artists/albums/tracks) or user's data (profile/playlists).
        ---- refresh_token, access_token on valid for 1 hour...
        ---- expires_at
        - 
    """
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
        response = requests.post(TOKEN_ENDPOINT_URI, data=req_body)
        token_info = response.json()

        session['access_token'] = token_info['access_token']
        session['refresh_token'] = token_info['refresh_token']
        session['expires_at'] = datetime.now().timestamp() + token_info['expires_in']
        return render_template("chat.html") # flask will look for templates in the templates folder 
                                            # TODO not sure what the autoscroll function in chat.html is doing


@app.route("/refresh-token") # common practice to use dashes in route names
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
        response = requests.post(TOKEN_ENDPOINT_URI, data=req_body)
        new_token_info = response.json()

        session['access_token'] = new_token_info['access_token'] 
        session['expires_at'] = datetime.now().timestamp() + new_token_info['expires_in']
        return render_template("chat.html")


@app.route("/get", methods=["GET", "POST"]) # by default, a route only answers to get requests - methods param used
def chat():
    """ Main Chatbot Logic 
        - Currently handles strickly playlist creation.
        - triggers on submit button in chat.html form
    """
    msg = request.form["msg"] # should be grabbing that raw text we set as the data in the ajax POST
    input = msg # Unedited prompt
    valid = check_if_request_valid(input)
    if valid.lower() == 'recs':
        revised_prompt = prompt_engineer(input)
        # json_completed_prompt will be set to the playlist chatGPT comes up with!
        json_completed_prompt = get_completion(revised_prompt) # consult chat for response in json format
        data = make_playlist_request(json_completed_prompt)
        return data 
    else:
        return "Example Prompts: Make me a playlist that is a mix of Michael Jackson and The Weeknd?, Make me a playlist for a rainy day?"
    # "Example Prompts: Make me a playlist that is a mix of Michael Jackson and The Weeknd?, What are my top songs?, Make me a playlist for a rainy day?"
    """
    elif valid.lower() == 'tracks':
        tracks = get_top_tracks()
        revised_prompt = prompt_engineer(tracks) # Make the top tracks into a playlist
        json_completed_prompt = get_completion(revised_prompt) # Json data that we will make our request with
        data = make_playlist_request(json_completed_prompt)
        return tracks
    """


def check_if_request_valid(input):
    """ Checks if message is a musical playlist request.
        - Consulting Chat on the Back End to ask if a Users input/requests/demands/
          whatever it may be pertains to the scope of our applciation.
        - returns one of Chat's possible responses pertaining request validity: {"recs", "no"}
    """
    #prompt_check = f"Does this prompt have anything to do with asking for music recommendations or making a playlist? If it does, simply say 'recs'. If it has anything to do with asking for top songs or tracks (Ex. What are my top tracks? What are my top songs?), simply say 'tracks'. If it is neither, simply say 'no' - Prompt:'{input}'"
    prompt_check = ( 
        "Does this prompt have anything to do with asking for music recommendations or making a playlist? "
        "If it does, simply say 'recs'. "
        f"If it does not, simply say 'no' - Prompt:'{input}'"
    )
    response = get_completion(prompt_check)
    return response


# hardcode the model we intend to use
def get_completion(prompt, model="gpt-4o-mini"): 
    """  ChatGPT API Helper Method
         - takes a given prompt and returns the response
    """
    messages = [{"role": "user", "content": prompt}]
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0, # this is the degree of randomness of the model's output
        #store=True, # do we need this / what is it for
    )
    return response.choices[0].message.content


def prompt_engineer(input):
    """ Prompt engineer behavior, taking users input and adding increased specificity:
        - Makes the prompt into a song recommendation format so we can process it
        - Alters prompt to ask for a response in json format with provided example
    """
    prompt = input + """. Make sure this playlist is in json format and 'artist' and 'song' are the keys. Limit this playlist to 10 songs please. 
    Ex. {'playlist':[{'artist':'Frank Ocean', 'song': 'Thinking Bout You'},{'artist': 'Daniel Caesar', 'song': 'Japanese Denim'}]}"""
    return prompt


def get_user_id(headers):
    """ Get user's spotifty username ('Spotify user ID') ex. charlie7977
        - GET request for the 'Spotify user ID' pertaining to a user's spotify account
    """
    response = requests.get(API_BASE_URL + 'me', headers=headers)
    spotify_id = response.json()['id']
    return spotify_id


def create_playlist(id, headers):
    """ Creates Empty Playlist
        - name, desc, and public/private specified
        - sends POST request to the API to create playlist
    """
    request_body = json.dumps({
      "name": "TEST-PLAYLIST",
      "description":"Playlist generated by ChatGPT according to your specific playlist creation request!",
      "public": False   # defaults to True unless specified
    })
    response_playlist = requests.post(API_BASE_URL + f"users/{id}/playlists", data=request_body, headers=headers)
    return response_playlist


# https://developer.spotify.com/documentation/web-api/reference/search
def get_track_id(search_query, headers):
    """ Peforms a query search to get a track and pull its 'Spotify URI'
        - Search for item with query string q in GET
        - Search filtered with type 'track' to limit search scope to only tracks matching search_query
    """
    track_info = requests.get(API_BASE_URL + "search", headers=headers, params={'q': {search_query}, "type": "track"})
    track_info_json = track_info.json()
    spotify_uri = track_info_json['tracks']['items'][0]['uri'] # could replace uri with id to grab only id
    #final_id = "spotify:track:" + id   # instead of doing this, we can just grab the 'Spotify URI' instead!
                                        # URI example: spotify:track:6rqhFgbbKwnb9MLmUQDhG6
    return spotify_uri #final_id


# https://developer.spotify.com/documentation/web-api/reference/add-tracks-to-playlist
def add_tracks_to_playlist(playlist_id, list_of_track_ids, headers):
    """ Adds a list of tracks to a playlist
        - A maximum of 100 items can be added in one request  TODO Ability to handle this alongside limit/offset 
    """
    request_body = json.dumps({
      "uris": list_of_track_ids
    })
    response = requests.post(API_BASE_URL + f"playlists/{playlist_id}/tracks", data=request_body, headers=headers)
    return response


def get_playlist_image(playlist_id, headers):
    """
    """
    time.sleep(2)
    response = requests.get(API_BASE_URL + f"playlists/{playlist_id}/images", headers=headers)
    image = response.json()[0]['url']
    return image


def make_playlist_request(gpt_response):
    """ Main Method for Playlist Creation Functionality 
        - @param gpt_response, the json formatted playlist CHAT devised
        - loops through tracks in playlist, appending corresponding track id's to []
    """
    if 'access_token' not in session:
        return redirect('/login')
    
    if datetime.now().timestamp() > session['expires_at']:
        return redirect('/refresh-token')
    
    headers = {
        'Authorization': f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }

    new_dict = ast.literal_eval(gpt_response) # TODO Rename new_dict  

    user_id = get_user_id(headers) # Get user's spotifty username ('Spotify user ID') ex. charlie7977

    playlist_obj = create_playlist(user_id, headers) # Create Playlist and retrieve object. 

    # Get Playlist ID (instance of a 'Spotify ID')
    response_playlist_id = playlist_obj.json()['id'] # Grabbing the "Spotify ID associated with this playlist"


    song_ids = []
    for i in range(len(new_dict['playlist'])):
        search_query = new_dict['playlist'][i]['song'] + " " + new_dict['playlist'][i]['artist'] # "Thinking Bout You Frank Ocean"
        track_id = get_track_id(search_query, headers)
        song_ids.append(track_id)

    add_tracks_to_playlist(response_playlist_id, song_ids, headers)

    # Get playlist image
    response_playlist_image = get_playlist_image(response_playlist_id, headers)

    playlist_url = PLAYLIST_BASE_URL + response_playlist_id

    return {"url": playlist_url, "image": response_playlist_image} 


'''
def get_top_tracks():
    list_of_tracks = []
    if 'access_token' not in session:
        return redirect('/login')
    
    if datetime.now().timestamp() > session['expires_at']:
        return redirect('/refresh-token')
    
    headers = {
        'Authorization': f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }

    response = requests.get(API_BASE_URL + "me/top/tracks", headers=headers, params={'time_range': 'medium_term', "limit": 10})
    top_tracks_json = response.json()

    str_tracks = ""
    song_count = 1
    for i in range(len(top_tracks_json['items'])):
        artist = top_tracks_json['items'][i]['artists'][0]['name']
        song =  top_tracks_json['items'][i]['name']
        str_tracks += str(song_count) + ". " + song + " - " + artist + ", "
        song_count += 1
    return str_tracks
'''

if __name__ == '__main__':
    app.run() #debug=True can be placed as param
