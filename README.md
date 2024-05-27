# Qualitative data summary

# To run

## Setup

Ensure environment is setup successfully:

```
$> python -m venv venv
$> source venv/bin/activate
$> pip install --requirement requirements.txt
```

If you are unable to install psycho, you may need:

```
$> sudo apt-get install libpq-dev
```

then try the environment setup again.

## Configuration

Create a JSON with the following structure:

```json
{
  "open_ai": {
    "api_key": "...",
    "model": "..."
  },
  "dalgo": {
    "host": "..",
    "dbname": "...",
    "user": "...",
    "password": "..."
  },
  "gradio": {
    "auth": [
      "...",
      "..."
    ],
    "server_name": "..."
  }
}
```

Each sub-dictionary is directly passed to a corresponding API. Each
top-level key should exist, but case of `open_ai` and `gradio` empty
dictionaries can suffice if defaults in the code are sufficient.

## Exectution

```bash
$> QS_CONFIG=/path/to/config.json gradio app.py
```
