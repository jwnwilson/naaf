"""Generate a Fernet key for ``naaf_secret_key`` (secrets encryption at rest).

    uv run python -m interactors.cli.gen_secret_key   # or: make secret-key

Set the printed value as ``naaf_secret_key`` in the server environment. Losing
it makes previously stored secrets undecryptable (re-enter them in the UI).
"""

from cryptography.fernet import Fernet


def generate_secret_key() -> str:
    return Fernet.generate_key().decode()


def main() -> None:
    print(generate_secret_key())


if __name__ == "__main__":
    main()
