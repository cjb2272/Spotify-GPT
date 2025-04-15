# Spotify-GPT 🎧
Use ChatGPT Chat Completions API & the Spotify API to automate playlist creation based on the users request!
![](https://github.com/flyseddy/Spotify-GPT/blob/main/screenshots/chancePlaylistRequest.png?raw=true)

## Overview:

As of right now, the application currently creates playlists in 2 possible manners. 
1. o4-mini will do it's best to come up with a playlist based on the users criteria, and then we query spotify for those tracks, resulting in a 10 song playlist.
   - i.e. "make me a playlist for a sunny spring day, and be sure to include some soft indie rock!"
2. if the user specifically requests a playlist of a favorite artist of theirs, we filter and query spotify on that artist only, resulting in a max 100 song playlist.
   - i.e. "make me a playlist of my favorite artist Billie Eilish"

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install required packages.

```bash
pip install -r requirements.txt
```

## Secret and API Keys
Use Spotify Developer Dashboard and OpenAI Developer Settings to access secret keys

[Spotify Dashboard](https://developer.spotify.com/dashboard)

[OpenAI Dashboard](https://platform.openai.com/api-keys)

```python
api_key = os.environ.get('OPENAI_APIKEY') 

CLIENT_ID = os.environ.get('CLIENT_ID') # Spotify Client Id 

CLIENT_SECRET = os.environ.get('CLIENT_SECRET') # Spotify Client Secret

```
## Run App

```python
flask run
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.



## License

[MIT](https://choosealicense.com/licenses/mit/)
