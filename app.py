"""
FLASK SERVER MAIN FILE
@author: Charles Baker
@original_author: Sedrick Thomas (https://github.com/flyseddy)

"""

from datetime import datetime
import time
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import urllib.parse
from pydantic import BaseModel
import requests
from openai import OpenAI
import ast
import json
import os

# New Constructor AUTO Grabs api_key value from enviornment key with dedicated name 'OPENAI_API_KEY'
client = OpenAI()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# OAuth-based authentication flow
CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID') # Spotify Client ID & Secret found in Spotify Dashboard https://developer.spotify.com/dashboard
CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET') 

REDIRECT_URI = 'http://127.0.0.1:5000/callback' # domain + "/callback"

AUTH_ENDPOINT_URI = 'https://accounts.spotify.com/authorize' # AUTH_URL
TOKEN_ENDPOINT_URI = 'https://accounts.spotify.com/api/token'  # Token URL
API_BASE_URL = 'https://api.spotify.com/v1/' # Base Address of the Spotify Web API. 
PLAYLIST_BASE_URL = 'https://open.spotify.com/playlist/'

# classes for use in structured output requests
class Song(BaseModel):
    artist: str
    song_title: str

class Playlist(BaseModel):
    playlist: list[Song]


@app.route("/")
def index():
    """Landing Page for Spotify Authentication for the Spotify-GPT application."""
    return render_template("index.html") 


@app.route("/login")
def login():
    """ Method for requesting Spotify User Authorization by sending a GET request to the authorize endpoint
        - Redirects to Official Spotify Login Page
        - Scope header:
        ---- playlist-modify-private allows for creating a private playlist
    """
    # the user doing authentication is asked to authorize access to data sets /features defined in the scopes listed space delimited
    scope = "user-library-read playlist-modify-public playlist-modify-private user-top-read"
    auth_headers = { 
    "client_id": CLIENT_ID,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": scope,
    "show_dialog": True,
    #"state": .... security param strongly recommended if moving to public..
    }
    auth_url = f"{AUTH_ENDPOINT_URI}?{urllib.parse.urlencode(auth_headers)}"
    return redirect(auth_url) 


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
        response = requests.post(TOKEN_ENDPOINT_URI, data=req_body)
        new_token_info = response.json()

        session['access_token'] = new_token_info['access_token'] 
        session['expires_at'] = datetime.now().timestamp() + new_token_info['expires_in']
        return render_template("chat.html")


@app.route("/get", methods=["GET", "POST"])
def chat():
    """ Main Chatbot Logic 
        - Currently handles strickly playlist creation.
        - triggers on submit button in chat.html form
    """
    msg = request.form["msg"] # grabbing raw text set as data in the ajax POST
    input = msg # Unedited prompt
    valid = check_if_request_valid(input)
    if valid.lower() == 'recs':
        revised_prompt = prompt_engineer(input)
        json_playlist = get_json_playlist_request_completion(revised_prompt) # ask CHAT to devise the playlist!
        data = make_playlist_request(json_playlist)
        return data 
    elif valid.lower() == 'favorite':
        artist_name = get_favorite_artist_from_prompt(input)
        data = make_artist_catalog_playlist(artist_name)
        return data
    else:
        return (
        "Example Prompts:"
        f"\"Make me a playlist that is a mix of Michael Jackson and The Weeknd\","
        f"\"Make me a playlist for a rainy day\","
        f"\"Make me a playlist of my favorite artist Billie Eilish"
        )

def check_if_request_valid(input):
    """ Checks if User Request Can Be Handled
        - Consulting Chat on the Back End to ask if a Users input/requests/demands/
          whatever it may be pertains to the scope of our applciation.
        - returns one of Chat's possible responses pertaining request validity: {'recs', 'favorite', 'no'}
    """
    seq = "Does 'PROMPT IN QUESTION' listed below"
    prompt_check = ( 
        "You MUST respond with one and only one of three responses: {'recs', 'favorite', 'no'}. \n"
        f"{seq} include the user specifically identifying an artist, band, person, or group as their favorite? "
        "If it does, simply say 'favorite'.\n"
        f"{seq} have anything to do with asking for music recommendations or making a playlist? "
        "If it does, simply say 'recs'.\n"
        "If it does not, simply say 'no'.\n\n"
        f"PROMPT IN QUESTION: \"{input}\"" 
    )
    response = get_standard_request_completion(prompt_check)
    return response


def get_standard_request_completion(prompt, model="gpt-4o-mini"): 
    """  ChatGPT API Helper Method
         - Utilizing API ability: Creating a Chat Completion
         ---- Given a list of messages comprising a conversation
         ---- Return a model response
         - IN this case: takes a given prompt and returns the response
    """
    message_list = [
        {"role": "developer", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt}
    ] # messages obj serves as set of instructions for model, role dictates how model interprets
    response = client.chat.completions.create(
        model=model,
        messages=message_list
    )
    
    # specify parameter 'n' above to have model generate more than 1 response (choices array) for the user to choose from.
    return response.choices[0].message.content


def get_json_playlist_request_completion(prompt, model="gpt-4o-mini"): 
    """  Request Json Structured Output Method (currently playlist specific)
         - Creating a specific Chat Completion using the OpenAI API 'client' object
         ---- Given a list of messages comprising a conversation
         ---- Return a model response designated as Json "Structed Output" using 'response_format' param
    """
    message_list = [
        {"role": "developer", "content": "You are a helpful assistant specializing in creating playlists of songs."},
        {"role": "user", "content": prompt}
    ]
    response = client.beta.chat.completions.parse(
        model=model,
        messages=message_list,
        response_format=Playlist,
        temperature=0.0 # the degree of randomness vs focused and deterministic for lower vals of the model's output (0.0-2.0). 
                      # recommended to alter this or 'top_p'
        #store=True, # do we need this / what is it for
    )
    if (response.choices[0].message.refusal):
        print(response.choices[0].message.refusal)

    return response.choices[0].message.content


def get_favorite_artist_from_prompt(user_prompt):
    """ 
        - Consulting Chat on the Back End to ask if ....
    """
    pull_favorite_artist_prompt = ( 
        "The 'PROMPT IN QUESTION' below includes mention of a favorite music artist pertaining to the user. "
        "The favorite artist will be the name of an artist, band, person, or group"
        "You MUST simply respond with the Artist Name.\n"
        "You will be penalized for responding with anything else besides strickly the Artist Name.\n"
        "You MUST search the web to verify that you have correctly identified the Artist Name, "
        "and that it is returned with the correct spelling in your response."
        "\n\n"
        f"PROMPT IN QUESTION: \"{user_prompt}\"" 
    )
    # could i alternatively ask it to return a refusal value instead and print that?
    artist_name_str = get_standard_request_completion(pull_favorite_artist_prompt)
    return artist_name_str


def prompt_engineer(input):
    """ Prompt engineer behavior, taking users input and adding increased specificity:
        - Makes the prompt into a song recommendation format so we can process it
        - Alters prompt to ask for a response in json format with provided example
    """
    prompt = input + """
    Limit this playlist to 10 songs. You will be penalized otherwise.
    """
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
def get_track_uri(search_query, headers):
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
        - A maximum of 100 items can be added in one request 
    """

    def chunk_list(data, chunk_size=100):
        chunks = []
        for i in range(0, len(data), chunk_size):
            chunks.append(data[i:i + chunk_size])
        return chunks
    
    chunked_tracks = chunk_list(list_of_track_ids)
    response = None
    for track_chunk in chunked_tracks:
    
        request_body = json.dumps({
          "uris": track_chunk
        })
        response = requests.post(API_BASE_URL + f"playlists/{playlist_id}/tracks", data=request_body, headers=headers)

        if response.status_code != 201:  # 201 expected for success
            print(f"Failed to add tracks: {response.status_code} - {response.text}")
            return response
        
        print(f"Successfully added {len(track_chunk)} tracks to playlist {playlist_id}")

    return response


def get_playlist_image(playlist_id, headers):
    """ Pull the cover photo associated with a spotify playlist given a Playlist ID (Spotify ID)
    """
    time.sleep(2)
    response = requests.get(API_BASE_URL + f"playlists/{playlist_id}/images", headers=headers)
    image = response.json()[0]['url']
    return image


def get_spotify_headers():
    """ Verifies a currently active authentication period
        - Standard request headers needed Spotify Web API
    """
    if 'access_token' not in session:
        return redirect('/login')
    
    if datetime.now().timestamp() > session['expires_at']:
        return redirect('/refresh-token')
    
    headers = {
        'Authorization': f"Bearer {session['access_token']}",
        "Content-Type": "application/json"
    }
    return headers


def make_playlist_request(gpt_response):
    """ Main Method for Playlist Creation Functionality 
        - @param gpt_response, the json formatted playlist CHAT devised
        - loops through tracks in playlist, appending corresponding track id's to []
    """
    headers = get_spotify_headers()

    playlist_dict = ast.literal_eval(gpt_response)

    user_id = get_user_id(headers) # Get user's spotifty username ('Spotify user ID') ex. charlie7977

    playlist_obj = create_playlist(user_id, headers) # Create Playlist and retrieve object. 

    # Get Playlist ID (instance of a 'Spotify ID')
    response_playlist_id = playlist_obj.json()['id'] # Grabbing the "Spotify ID associated with this playlist"


    song_uris = [] # URI includes Song ID
    for i in range(len(playlist_dict['playlist'])):
        search_query = playlist_dict['playlist'][i]['song_title'] + " " + playlist_dict['playlist'][i]['artist'] # "Thinking Bout You Frank Ocean"
        track_uri = get_track_uri(search_query, headers)
        song_uris.append(track_uri)

    if len(song_uris) != 0:
        response = add_tracks_to_playlist(response_playlist_id, song_uris, headers)
        if response.status_code != 201:
            return response

    # Get playlist image
    response_playlist_image = get_playlist_image(response_playlist_id, headers)

    playlist_url = PLAYLIST_BASE_URL + response_playlist_id

    return {"url": playlist_url, "image": response_playlist_image} 


def make_artist_catalog_playlist(artist_name):
    """
    Given the name of an Artist, Create a playlist consisting of only tracks of that artist.
    
    note: encountered API Bug with 'offset' during development as documented 
          on spotify developer api pages regarding issue retrieving more than 100 items from a search. 
    """
    headers = get_spotify_headers()

    user_id = get_user_id(headers) # Get user's spotifty username ('Spotify user ID') ex. charlie7977
    playlist_obj = create_playlist(user_id, headers) # Create Playlist and retrieve object. 
    favorite_artist_playlist_id = playlist_obj.json()['id'] # Grabbing the "Spotify ID associated with this playlist"

    song_uris = []
    indexing_catalog = True
    offset = 0 # increments by 50 until we reach end. max value it can be is 1000
    while (indexing_catalog):
        params = {
          "q":f"artist:\"{artist_name}\"",
          "type":"track",
          "limit": 50,
          "offset": offset
        }
        search_response = requests.get(API_BASE_URL + "search", headers=headers, params=params)
        search_response_data = search_response.json()
        num_tracks = len(search_response_data['tracks']['items'])
        if (num_tracks == 0):
            return {"error": search_response.text} # Ex: Artist name Chat found does not exist
        for song in range(num_tracks):
            song_uri = search_response_data['tracks']['items'][song]['uri']
            song_uris.append(song_uri)

        # break condition
        if (search_response_data['tracks']['next'] == None): # next - does next page of search results have tracks
            indexing_catalog = False

        offset += 50

    response = add_tracks_to_playlist(favorite_artist_playlist_id, song_uris, headers)
    if response.status_code != 201:
        return response
    
    # Get playlist image
    response_playlist_image = get_playlist_image(favorite_artist_playlist_id, headers)
    playlist_url = PLAYLIST_BASE_URL + favorite_artist_playlist_id
    return {"url": playlist_url, "image": response_playlist_image}


if __name__ == '__main__':
    app.run()
