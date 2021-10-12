# -*- coding: utf-8 -*-

import datetime
import hashlib
import ipaddress
import secrets
import string

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from nacl.exceptions import CryptoError
from nacl.pwhash import argon2id
from nacl.secret import SecretBox
from nacl.utils import random
from PyQt5.QtCore import QObject, pyqtSignal

from gridsync.util import b58decode, b58encode


def randstr(length: int = 32, alphabet: str = "") -> str:
    if not alphabet:
        alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for i in range(length))


def trunchash(s: str, length: int = 7) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:length]


def create_certificate(pemfile: str, hostname: str, ip_address: str) -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name(
        [x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, hostname)]
    )
    san = x509.SubjectAlternativeName(
        [
            x509.DNSName(hostname),
            x509.DNSName(ip_address),
            x509.IPAddress(ipaddress.ip_address(ip_address)),
        ]
    )
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 100))
        .add_extension(san, False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), False)
        .sign(key, hashes.SHA256())
    )
    with open(pemfile, "wb") as f:
        f.write(
            cert.public_bytes(serialization.Encoding.PEM)
            + key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    return cert.fingerprint(hashes.SHA256())


def get_certificate_digest(pemfile: str) -> bytes:
    with open(pemfile, encoding="utf-8") as f:
        cert = x509.load_pem_x509_certificate(f.read().encode())
    digest = cert.fingerprint(hashes.SHA256())
    return digest


def get_certificate_public_bytes(pemfile: str) -> bytes:
    with open(pemfile, encoding="utf-8") as f:
        cert = x509.load_pem_x509_certificate(f.read().encode())
    public_bytes = cert.public_bytes(serialization.Encoding.PEM)
    return public_bytes


class VersionError(CryptoError):
    pass


def encrypt(message: bytes, password: bytes) -> str:
    version = b"1"
    salt = random(argon2id.SALTBYTES)  # 16
    key = argon2id.kdf(
        SecretBox.KEY_SIZE,  # 32
        password,
        salt,
        opslimit=argon2id.OPSLIMIT_SENSITIVE,  # 4
        memlimit=argon2id.MEMLIMIT_SENSITIVE,  # 1073741824
    )
    box = SecretBox(key)
    encrypted = box.encrypt(message)
    return version + b58encode(salt + encrypted).encode()


def decrypt(ciphertext: bytes, password: bytes) -> str:
    version = ciphertext[:1]
    ciphertext = b58decode(ciphertext[1:].decode())
    if version == b"1":
        salt = ciphertext[: argon2id.SALTBYTES]  # 16
        encrypted = ciphertext[argon2id.SALTBYTES :]
        key = argon2id.kdf(
            SecretBox.KEY_SIZE,  # 32
            password,
            salt,
            opslimit=argon2id.OPSLIMIT_SENSITIVE,  # 4
            memlimit=argon2id.MEMLIMIT_SENSITIVE,  # 1073741824
        )
    else:
        raise VersionError(
            "Invalid version byte; received {!r}".format(version)
        )
    box = SecretBox(key)
    plaintext = box.decrypt(encrypted)
    return plaintext


class Crypter(QObject):

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, data: bytes, password: bytes) -> None:
        super().__init__()
        self.data = data
        self.password = password

    def encrypt(self) -> None:
        try:
            self.succeeded.emit(encrypt(self.data, self.password))
        except Exception as err:  # pylint: disable=broad-except
            self.failed.emit(str(err))

    def decrypt(self) -> None:
        try:
            self.succeeded.emit(decrypt(self.data, self.password))
        except Exception as err:  # pylint: disable=broad-except
            self.failed.emit(str(err))
