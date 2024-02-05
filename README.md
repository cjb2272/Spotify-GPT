# Spotify-GPT 🎧
Use ChatGPT API and Spotify API to automate music recommendations and playlist creation
![](https://github.com/flyseddy/Spotify-GPT/blob/main/screenshots/MusicRequest.png?raw=true)

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