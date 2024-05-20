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

## Exectution

First, fill `config.ini` with your Open AI and database
credentials. Then:

```bash
$> QS_CONFIG=config.ini gradio app.py
```
