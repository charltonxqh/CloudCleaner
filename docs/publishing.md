# Publishing CloudCleaner to PyPI

The package is **`cloudcleaner-agent`**, live at
<https://pypi.org/project/cloudcleaner-agent/>. The command it installs is
`cloudcleaner`.

`cloudcleaner` itself was rejected: PyPI normalises hyphens, underscores and
case, so it collided with the existing `cloud-cleaner`. A 404 on
`pypi.org/pypi/<name>/json` only means nobody has registered that exact string
— the similarity check runs at upload time, so check for hyphenated and
underscored variants too before settling on a name.

## What ships

| Install | Pulls in | For |
|---|---|---|
| `pip install cloudcleaner` | the agent, AWS, GitHub, Groq, SQLite | the CLI |
| `pip install 'cloudcleaner[server]'` | the above plus FastAPI, uvicorn, CopilotKit, AG-UI | the HTTP API and the web frontend |
| `pip install 'cloudcleaner[all]'` | everything, including OpenAI, Anthropic and LangSmith | development |

Splitting these matters: a CLI user has no reason to install a web server.
The core install is 58 packages, `[server]` is 69.

## One-time setup

1. **Create accounts.** [pypi.org](https://pypi.org/account/register/) and, for
   rehearsal, [test.pypi.org](https://test.pypi.org/account/register/). They are
   separate registrations.
2. **Turn on 2FA.** PyPI requires it before you can upload.
3. **Create an API token** at Account settings → API tokens. Scope it to "Entire
   account" for the first upload — you cannot scope a token to a project that
   does not exist yet. Copy it now; it is shown once.
4. **Store it** in `~/.pypirc`:

   ```ini
   [distutils]
   index-servers = pypi testpypi

   [pypi]
   username = __token__
   password = pypi-AgEIcHlwaS5vcmc...

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-AgENdGVzdC5weXBpLm9yZw...
   ```

   Then `chmod 600 ~/.pypirc`. Never commit it.

## Publishing

```bash
cd agent

# 1. build — always from a clean dist/
rm -rf dist && uv build

# 2. rehearse on TestPyPI first
uv publish --index testpypi

# 3. check the rehearsal actually installs
uv venv /tmp/cc-check --python 3.12
uv pip install --python /tmp/cc-check/bin/python \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  cloudcleaner
/tmp/cc-check/bin/cloudcleaner --help

# 4. the real thing
uv publish
```

`uv publish` reads `UV_PUBLISH_TOKEN` from the environment, so a token never has
to be written to disk:

```bash
UV_PUBLISH_TOKEN='pypi-...' uv publish
```

The `--extra-index-url` in step 3 is needed because TestPyPI does not mirror
the real package index, so the dependencies have to come from PyPI.

## After publishing

```bash
pip install cloudcleaner
cloudcleaner doctor
CLOUDCLEANER_PROVIDER=fixture cloudcleaner scan
```

## Things that will bite you

**A version can never be reused.** Upload `0.1.0` once and that number is burned
on PyPI forever, even if you delete the release. Bump `version` in
`agent/pyproject.toml` for every upload — including fixing a typo in the README.

**The README is the project page.** `readme = "README.md"` in pyproject points at
`agent/README.md`, which is currently the CopilotKit starter's file. Replace it
before publishing or that is what visitors see.

**Check the wheel actually contains what you think:**

```bash
python3 -m zipfile -l dist/cloudcleaner-0.1.0-py3-none-any.whl | head -30
```

Only `cloudcleaner*` is packaged. `scripts/`, `tests/` and `main.py` are not, so
anything a user needs must live inside the package — that is why the FastAPI app
moved to `cloudcleaner/server.py`.

**Data goes to the user's home.** An installed copy writes to `~/.cloudcleaner/`
rather than beside the code, because `site-packages` is not writable in a lot of
environments. `CLOUDCLEANER_DATA_DIR` overrides it.
