from adapters.security.cipher import SecretCipher
from interactors.cli.gen_secret_key import generate_secret_key


def test_generates_a_key_the_cipher_can_use():
    key = generate_secret_key()
    cipher = SecretCipher(key)  # must be a valid Fernet key
    assert cipher.decrypt(cipher.encrypt("hello")) == "hello"


def test_keys_are_unique():
    assert generate_secret_key() != generate_secret_key()
